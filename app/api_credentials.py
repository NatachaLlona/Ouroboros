"""Terminal API enrollment and one-way migration of legacy local credentials."""
import secrets
from argon2 import PasswordHasher
from argon2.low_level import Type
from app.config import PROJECT_ROOT, save_config
from app.credentials import read_password, write_secret
from app.database import DatabaseError
from app.password_policy import validate_new_password

PASSWORD_HASHER = PasswordHasher(type=Type.ID)


def migrate_legacy_user(config, users, root=PROJECT_ROOT):
    """Commit the exact legacy account before removing sensitive local fields.

    Args:
        config: Loaded configuration, possibly containing legacy auth fields.
        users: Account repository with idempotent import/conflict checks.
        root: Owning workspace for atomic non-secret configuration persistence.

    Raises:
        DatabaseError: If persistence conflicts; original config stays untouched.
    """
    auth = config["auth"]
    username, password_hash = auth.get("username", ""), auth.get("password_hash", "")
    if password_hash:
        users.import_legacy(username, password_hash)
        # Persistence is confirmed before mutating or writing configuration.
        config.setdefault("api_users", {})["last_api_username"] = username
    if "username" in auth or "password_hash" in auth:
        auth.pop("username", None)
        auth.pop("password_hash", None)
        save_config(config, root)


def configure_api_credentials(config, users, root=PROJECT_ROOT):
    """Recover the first administrator after master-authenticated startup.

    Args:
        config: Local non-secret configuration, updated only after persistence.
        users: Database-backed account store.
        root: Workspace owning the configuration.

    Returns:
        None. Existing installations with an active administrator need no input.

    Raises:
        DatabaseError: If terminal selection is invalid.
        UserManagementError: On concurrent recovery or conflicting selection.

    Existing users remain standard until explicitly selected for promotion.
    Once an active administrator exists, enrollment belongs to the API.
    """
    migrate_legacy_user(config, users, root)
    if users.has_administrator():
        save_config(config, root)
        return
    promoting = False
    if users.count():
        print("No active API administrator exists. Existing accounts have not been promoted automatically.")
        choice = input("Promote an existing active user or create a new administrator? [promote/create]: ").strip().lower()
        if choice not in ("promote", "create"):
            raise DatabaseError("Choose promote or create explicitly for administrator recovery")
        promoting = choice == "promote"
    username = input("Existing API username to promote: " if promoting else "New API administrator username: ").strip()
    if not username or any(not char.isprintable() for char in username):
        raise DatabaseError("API username must be non-empty and contain no control characters")
    if promoting:
        users.bootstrap_administrator(username)
        config["api_users"]["last_api_username"] = username
        save_config(config, root)
        return
    if users.get_by_username(username) is not None:
        raise DatabaseError("API username already exists; choose another. Existing users cannot be replaced")
    password = read_password("API administrator password: ")
    try:
        try:
            validate_new_password(password)
        except ValueError as error:
            raise DatabaseError(str(error)) from None
        password_hash = PASSWORD_HASHER.hash(password)
    finally:
        password = None
    users.bootstrap_administrator(username, password_hash)
    config["api_users"]["last_api_username"] = username
    save_config(config, root)


def load_signing_secret(root=PROJECT_ROOT):
    """Read or create the protected persistent signing key outside Git.

    Args:
        root: Workspace owning the restricted secret directory.

    Returns:
        A signing key of at least 32 UTF-8 bytes, reused across restarts.

    Raises:
        DatabaseError: If the secret is unreadable or too short.
    """
    path = write_secret(secrets.token_urlsafe(64), root, filename="jwt_signing_key")
    try:
        secret = path.read_text(encoding="utf-8")
        if len(secret.encode("utf-8")) < 32:
            raise ValueError
        return secret
    except (OSError, UnicodeError, ValueError):
        raise DatabaseError("JWT signing secret is unreadable or too short; restore the protected signing key") from None
