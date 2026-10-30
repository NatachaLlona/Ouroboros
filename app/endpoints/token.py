"""Local controlled-client OAuth2 password grant."""
from app.logger import log_event
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from app.errors import ErrorResponse

router = APIRouter()


class LocalPasswordForm(OAuth2PasswordRequestForm):
    """Document the local grant explicitly without changing password or scope policy."""
    def __init__(
        self,
        username: Annotated[str, Form(description="Required API username stored in api_users; do not use the PostgreSQL master user.")],
        password: Annotated[str, Form(description="Required API password; never the database master password.", json_schema_extra={"format": "password"})],
        grant_type: Annotated[Literal["password"], Form(description="Only password is supported. Leave the default password. Omitted or empty form fields use this default.")] = "password",
        scope: Annotated[str, Form(description="Optional space-separated scopes, for example test:read test:write. Omitted or empty grants only the account's currently allowed scopes.", examples=["test:read test:write"])] = "",
        client_id: Annotated[str | None, Form(description="Not used by this controlled local client. Leave empty; Send empty value is optional.")] = None,
        client_secret: Annotated[str | None, Form(description="Not used by this controlled local client. Leave empty; Send empty value is optional.", json_schema_extra={"format": "password"})] = None,
    ):
        super().__init__(username=username, password=password, grant_type=grant_type,
                         scope=scope, client_id=client_id, client_secret=client_secret)


class TokenResponse(BaseModel):
    """OAuth2 bearer response; never send this object to application logs."""
    access_token: str
    token_type: str
    expires_in: int


@router.post("/token", response_model=TokenResponse, tags=["auth"],
             responses={429: {'model': ErrorResponse, 'description': 'Login attempt limit reached: 10/account or 50/direct client in 300 seconds. Retry after the Retry-After seconds.',
                 'headers': {'Retry-After': {'schema': {'type': 'integer'}, 'description': 'Seconds until retry'}}}},
             description="Local OAuth2 password grant. Prefer Swagger Authorize to store the token globally; Try it out returns a token without automatically authorizing other operations.")
def token(request: Request, response: Response,
          form: Annotated[LocalPasswordForm, Depends()]):
    """Verify active database credentials and issue only permitted OAuth2 scopes.

    Args:
        request: Request carrying the authentication service.
        response: Response receiving no-store cache headers.
        form: Local password grant; credentials must never be logged.

    Returns:
        Signed token metadata for the controlled local client.

    Raises:
        HTTPException: 401 for invalid credentials, 403 for unavailable scopes.
    """
    auth = request.app.state.auth
    retry = request.app.state.login_throttle.admit(form.username, request.client.host if request.client else 'unknown')
    if retry is not None:
        raise HTTPException(429, 'Login attempt limit reached', headers={'Retry-After': str(retry), 'Cache-Control': 'no-store'})
    user = auth.verify_password(form.username, form.password)
    if user is None:
        raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    result = auth.issue(user, form.scopes)
    log_event("INFO", "Access token issued")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return result
