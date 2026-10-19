"""Administrator-only enrollment, paginated listing and role replacement."""
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, Security

from app.api_credentials import PASSWORD_HASHER
from app.api_users import UserManagementError
from app.auth import require_scopes
from app.logger import log_event
from app.pagination import Page, pagination
from app.schemas.users import PasswordChange, PasswordReset, PublicUser, RoleUpdate, UserCreate

router = APIRouter(tags=["users"])
Administrator = Annotated[dict, Security(require_scopes, scopes=["users:manage"])]


@router.put("/users/me/password", status_code=204, response_class=Response)
def change_own_password(payload: PasswordChange, request: Request,
                        actor: Annotated[dict, Security(require_scopes, scopes=[])]):
    """Change only the active caller's password and revoke that account's tokens.

    Args:
        payload: Secret current/new credentials; the entire body is log-excluded.
        request: Request carrying the account repository.
        actor: Validated subject/version; both profiles can change their password.

    Returns:
        An empty 204 after the atomic hash/version transaction commits.

    Raises:
        UserManagementError: 400 for invalid confirmation/unchanged password,
            or 401 if another change revoked this token before the row lock.
    """
    user_id = int(actor["sub"])
    request.app.state.auth.users.change_password(user_id, actor["credential_version"],
        payload.current_password.get_secret_value(), payload.new_password.get_secret_value())
    log_event("INFO", "API password changed", {"user_id": user_id})
    return Response(status_code=204)


@router.put("/users/{id}/password", status_code=204, response_class=Response,
            responses={400: {"description": "Self-targeting: use /users/me/password"},
                       401: {"description": "Invalid or revoked authentication"},
                       403: {"description": "Active administrator required"},
                       404: {"description": "Target user not found"}})
def reset_user_password(payload: PasswordReset, request: Request, actor: Administrator,
                        id: Annotated[int, Path(gt=0, le=9223372036854775807)]):
    """Reset another user's password and revoke all of that user's old tokens.

    Args:
        payload: Strict nonempty new password; the entire body is log-excluded.
        request: Request carrying the transactional account repository.
        actor: Active administrator, rechecked in the transaction.
        id: Target account ID; self-targeting returns 400 and requires self-service.

    Returns:
        Empty 204 after commit, preserving unrelated accounts and tokens.

    Raises:
        UserManagementError: Safe 400/401/403/404 rejection from the repository.
    """
    actor_id = int(actor["sub"])
    audit = {"administrator_id": actor_id, "user_id": id}
    try:
        request.app.state.auth.users.reset_password(actor_id, actor["credential_version"], id,
            PASSWORD_HASHER.hash(payload.new_password.get_secret_value()))
    except UserManagementError as error:
        log_event("WARNING", "API password reset rejected", {**audit, "outcome": "rejected", "status": error.status})
        raise
    log_event("INFO", "API password reset", {**audit, "outcome": "completed"})
    return Response(status_code=204)


@router.post("/users", status_code=201, response_model=PublicUser)
def create_user(payload: UserCreate, request: Request, actor: Administrator):
    """Hash a new password and commit an account under administrator control.

    Args:
        payload: Validated account fields, with a masked password representation.
        request: Request carrying the configured database-backed account store.
        actor: Current active administrator verified by the shared authorization.

    Returns:
        Public metadata of the persisted account, without credentials.
    """
    hashed = PASSWORD_HASHER.hash(payload.password.get_secret_value())
    user = request.app.state.auth.users.create_managed(int(actor["sub"]), payload.username, hashed, payload.role)
    log_event("INFO", "API user created", {"administrator_id": int(actor["sub"]), "user_id": user["id"],
                                          "previous_role": None, "new_role": user["role"]})
    return user


@router.get("/users", response_model=Page[PublicUser])
def list_users(request: Request, actor: Administrator, paging: Annotated[dict, Depends(pagination)]):
    """List public accounts ordered by ID; only page/page_size are supported.

    Args:
        request: Request carrying the database-backed account repository.
        actor: Current active administrator verified by shared authorization.
        paging: Shared validated one-based page and bounded page size.

    Returns:
        A public-only collection envelope from one database statement snapshot.
    """
    return request.app.state.auth.users.page(**paging)


@router.put("/users/{id}/role", response_model=PublicUser)
def replace_role(payload: RoleUpdate, request: Request, actor: Administrator,
                 id: Annotated[int, Path(gt=0, le=9223372036854775807)]):
    """Replace a role transactionally and audit the committed transition.

    Args:
        payload: Complete replacement role from the fixed role set.
        request: Request carrying the database-backed account repository.
        actor: Administrator revalidated again inside the membership lock.
        id: Positive immutable target account ID.

    Returns:
        Public account metadata after commit.

    Raises:
        UserManagementError: If the transaction rejects a missing target,
            revoked actor or demotion of the last active administrator.
    """
    user, previous = request.app.state.auth.users.change_role(int(actor["sub"]), id, payload.role)
    log_event("INFO", "API user role changed", {"administrator_id": int(actor["sub"]), "user_id": id,
                                               "previous_role": previous, "new_role": user["role"]})
    return user
