"""Database-backed API accounts; never use PostgreSQL role credentials here."""
from dataclasses import dataclass, field
from argon2 import extract_parameters
from argon2.low_level import Type
from app.config import PROJECT_ROOT
from app.database import DatabaseError

TEST_SCOPES = ("test:read", "test:write")


class UserManagementError(Exception):
    """Expose only application-owned safe user-management guidance."""

    def __init__(self, status, detail):
        self.status = status
        super().__init__(detail)


def public_user(row):
    """Map a public-only SQL projection without exposing credentials."""
    return dict(zip(("id", "username", "role", "is_active", "created_at"), row))


@dataclass(frozen=True)
class APIUser:
    """Internal authentication account; never serialize this credential record."""
    id: int
    username: str
    password_hash: str = field(repr=False)
    is_active: bool
    scopes: tuple[str, ...]
    role: str = "standard"
    credential_version: int = 1


def as_user(row):
    """Map the internal authentication projection, or an absent row."""
    return APIUser(row[0], row[1], row[2], row[3], tuple(row[4]), row[5], row[6]) if row else None


def validate_hash(value):
    """Reject non-Argon2id hashes without exposing the rejected hash.

    Raises:
        DatabaseError: If the stored/imported hash is not valid Argon2id.
    """
    try:
        if extract_parameters(value).type != Type.ID:
            raise ValueError
    except (ValueError, TypeError):
        raise DatabaseError("API password hash must be valid Argon2id") from None


def query(name):
    return (PROJECT_ROOT / "sql/queries" / name).read_text(encoding="utf-8")


class APIUserStore:
    """Persist API accounts and serialize administrator membership changes.

    Args:
        database: Connection provider whose context commits or rolls back.

    All application paths that change administrator membership share a
    transaction advisory lock. Direct master SQL must uphold the same invariant.
    """
    def __init__(self, database):
        self.database = database

    def realm(self):
        """Return the selected database name used to bind token subjects."""
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            return cursor.fetchone()[0]

    def get_by_username(self, username):
        """Read a current authentication account by exact username, or None."""
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(query("find_api_user_by_name.sql"), (username,))
            return as_user(cursor.fetchone())

    def get_by_id(self, user_id):
        """Read current role/state/scopes using the immutable token subject."""
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(query("find_api_user_by_id.sql"), (user_id,))
            return as_user(cursor.fetchone())

    def count(self):
        """Count accounts for master-authenticated first-administrator recovery."""
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM public.api_users")
            return cursor.fetchone()[0]

    def create(self, username, password_hash, scopes=TEST_SCOPES, role="standard"):
        """Insert an internal account without replacement; API writes use create_managed.

        Args:
            username: Unique account identity.
            password_hash: Existing Argon2id hash, never a plaintext password.
            scopes: Explicit stored test permissions.
            role: Fixed account role, standard unless explicitly supplied.

        Returns:
            The internal account after commit.

        Raises:
            DatabaseError: On duplicate username or invalid hash.
        """
        validate_hash(password_hash)
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(query("insert_api_user.sql"), (username, password_hash, list(scopes), role))
            user = as_user(cursor.fetchone())
            if user is None:
                raise DatabaseError("API username already exists; choose another username")
        return user

    def import_legacy(self, username, password_hash):
        """Commit a matching legacy import without changing existing credentials.

        Args:
            username: Legacy configured identity.
            password_hash: Exact legacy Argon2id hash to preserve.

        Returns:
            The committed account; new imports are standard, never auto-promoted.

        Raises:
            DatabaseError: On a conflicting hash, active state or scope set.
        """
        validate_hash(password_hash)
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(query("insert_api_user.sql"), (username, password_hash, list(TEST_SCOPES), "standard"))
            user = as_user(cursor.fetchone())
            if user is None:
                cursor.execute("SELECT id, username, password_hash, is_active, scopes, role, credential_version FROM public.api_users WHERE username = %s FOR UPDATE", (username,))
                user = as_user(cursor.fetchone())
                if (user is None or user.password_hash != password_hash or not user.is_active
                        or set(user.scopes) != set(TEST_SCOPES)):
                    raise DatabaseError("Legacy API user conflicts with an existing database account; configuration was preserved. Resolve the account conflict explicitly; no password or permissions were overwritten")
        # The provider's context has committed before the caller may erase local fields.
        return user

    def has_administrator(self):
        """Return whether the database has an active administrator."""
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM public.api_users WHERE role='administrator' AND is_active)")
            return cursor.fetchone()[0]

    def _lock_membership(self, cursor, actor_id=None, credential_version=None):
        """Serialize membership changes and recheck the acting administrator.

        Args:
            cursor: Cursor in the caller's transaction.
            actor_id: API actor ID, or None for master-validated terminal recovery.
            credential_version: Optional token version rechecked for API writes.

        Raises:
            UserManagementError: If the actor lost active administrator access.
        """
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (719230818,))
        if actor_id is not None:
            cursor.execute("SELECT role, is_active FROM public.api_users WHERE id=%s FOR UPDATE", (actor_id,))
            if cursor.fetchone() != ("administrator", True):
                raise UserManagementError(403, "Active administrator access required")
            if credential_version is not None:
                cursor.execute("SELECT credential_version FROM public.api_users WHERE id=%s", (actor_id,))
                if cursor.fetchone()[0] != credential_version:
                    raise UserManagementError(401, "Invalid or expired access token")

    def bootstrap_administrator(self, username, password_hash=None):
        """Explicitly promote an active account or create the first administrator.

        Args:
            username: Explicit terminal selection after master authentication.
            password_hash: Argon2id hash for a new account; None promotes an existing one.

        Returns:
            The persisted administrator account.

        Raises:
            UserManagementError: If recovery is no longer needed or selection is invalid.

        The transaction lock makes competing bootstrap attempts mutually exclusive.
        Existing hashes, scopes, IDs and other accounts are never replaced.
        """
        if password_hash is not None:
            validate_hash(password_hash)
        with self.database.connection() as connection, connection.cursor() as cursor:
            self._lock_membership(cursor)
            cursor.execute("SELECT count(*) FROM public.api_users WHERE role='administrator' AND is_active")
            if cursor.fetchone()[0]:
                raise UserManagementError(409, "An active administrator already exists; use the administrative API")
            if password_hash is None:
                cursor.execute("UPDATE public.api_users SET role='administrator' WHERE username=%s AND is_active RETURNING id, username, password_hash, is_active, scopes, role, credential_version", (username,))
            else:
                cursor.execute(query("insert_api_user.sql"), (username, password_hash, list(TEST_SCOPES), "administrator"))
            user = as_user(cursor.fetchone())
            if user is None:
                raise UserManagementError(409, "Choose an existing active user to promote, or a unique username for a new administrator")
        return user

    def page(self, page=1, page_size=50, order_by='id', order_direction='asc'):
        """Return public accounts and count from one SQL statement snapshot.

        Args:
            page: Validated one-based page number.
            page_size: Validated page size between 10 and 50.
            order_by: Whitelisted public scalar field; default id.
            order_direction: asc or desc, with NULLS LAST.

        Returns:
            A collection envelope excluding all password/hash columns.
        """
        from app.collection_queries import select_page
        with self.database.connection() as connection:
            return select_page(connection, 'api_users', ('id', 'username', 'role', 'is_active', 'created_at'),
                'id', [], page, page_size, order_by, order_direction)

    def create_managed(self, actor_id, username, password_hash, role, credential_version=None):
        """Create an account atomically after rechecking the API actor.

        Args:
            actor_id: Responsible administrator ID.
            username: Validated unique account name.
            password_hash: Argon2id hash; plaintext must never reach this layer.
            role: Validated standard, supervisor or administrator role.
            credential_version: API token version, rechecked under the actor lock.

        Returns:
            Public persisted account fields.

        Raises:
            UserManagementError: On duplicate username or revoked authorization.
        """
        validate_hash(password_hash)
        with self.database.connection() as connection, connection.cursor() as cursor:
            self._lock_membership(cursor, actor_id, credential_version)
            cursor.execute(query("create_managed_user.sql"), (username, password_hash, list(TEST_SCOPES), role))
            row = cursor.fetchone()
            if row is None:
                raise UserManagementError(409, "Username already exists")
        return public_user(row)

    def change_role(self, actor_id, user_id, role, credential_version=None):
        """Replace a role while protecting the last active administrator.

        Args:
            actor_id: Responsible administrator ID, rechecked inside the lock.
            user_id: Target immutable account ID.
            role: New validated role.
            credential_version: API token version, rechecked under the actor lock.

        Returns:
            Tuple of public account fields and previous role, after commit.

        Raises:
            UserManagementError: On missing target (404), revoked access (403),
                or last active administrator demotion (409).

        The shared transaction lock serializes concurrent cross/self demotions.
        """
        with self.database.connection() as connection, connection.cursor() as cursor:
            self._lock_membership(cursor, actor_id, credential_version)
            cursor.execute("SELECT role, is_active FROM public.api_users WHERE id=%s FOR UPDATE", (user_id,))
            old = cursor.fetchone()
            if old is None:
                raise UserManagementError(404, "User not found")
            if old == ("administrator", True) and role != "administrator":
                cursor.execute("SELECT count(*) FROM public.api_users WHERE role='administrator' AND is_active")
                if cursor.fetchone()[0] <= 1:
                    raise UserManagementError(409, "Cannot demote the last active administrator")
            cursor.execute("UPDATE public.api_users SET role=%s WHERE id=%s RETURNING id, username, role, is_active, created_at", (role, user_id))
            result = public_user(cursor.fetchone())
        return result, old[0]

    def reset_password(self, actor_id, credential_version, user_id, password_hash):
        """Commit another account's hash/version under the administration lock.

        Args:
            actor_id: Current administrator's immutable subject.
            credential_version: Actor token version, rechecked under the row lock.
            user_id: Target account; self-targeting is rejected with 400.
            password_hash: Valid Argon2id hash; plaintext never enters SQL.

        Raises:
            UserManagementError: 401 for revoked actor credentials, 403 for a
                demoted/inactive actor, 404 for an absent target, or 400 for self.

        The shared advisory lock serializes role changes and resets. Actor and
        target row locks prevent an intervening self-service password change
        from authorizing a stale actor. Hash and version commit together; only
        the target's existing tokens are revoked. Inactive targets stay inactive.
        """
        validate_hash(password_hash)
        with self.database.connection() as connection, connection.cursor() as cursor:
            self._lock_membership(cursor, actor_id)
            cursor.execute("SELECT credential_version FROM public.api_users WHERE id=%s", (actor_id,))
            if cursor.fetchone()[0] != credential_version:
                raise UserManagementError(401, "Invalid or expired access token")
            if actor_id == user_id:
                raise UserManagementError(400, "Use /users/me/password to change your own password")
            cursor.execute(query("lock_api_user_credentials.sql"), (user_id,))
            if cursor.fetchone() is None:
                raise UserManagementError(404, "User not found")
            cursor.execute(query("change_api_user_password.sql"), (password_hash, user_id))

    def change_password(self, user_id, credential_version, current_password, new_password):
        """Confirm and replace the caller's password under an account row lock.

        Args:
            user_id: Immutable subject from a validated token, never request JSON.
            credential_version: Version in that token, rechecked after locking.
            current_password: Confirmation used only for Argon2id verification.
            new_password: New plaintext credential, hashed before persistence.

        Raises:
            UserManagementError: 401 for revoked/inactive authentication, or 400
                for incorrect confirmation or an unchanged password.

        The connection context commits hash/version together. Competing changes
        using the same version cannot both succeed; no other account/key changes.
        """
        import secrets
        from argon2.exceptions import VerificationError, InvalidHashError
        from app.api_credentials import PASSWORD_HASHER

        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(query("lock_api_user_credentials.sql"), (user_id,))
            row = cursor.fetchone()
            if row is None or not row[1] or row[2] != credential_version:
                raise UserManagementError(401, "Invalid or expired access token")
            try:
                valid = PASSWORD_HASHER.verify(row[0], current_password)
            except (VerificationError, InvalidHashError):
                valid = False
            if not valid:
                raise UserManagementError(400, "Current password is incorrect")
            if secrets.compare_digest(current_password.encode("utf-8"), new_password.encode("utf-8")):
                raise UserManagementError(400, "New password must differ from the current password")
            hashed = PASSWORD_HASHER.hash(new_password)
            cursor.execute(query("change_api_user_password.sql"), (hashed, user_id))
