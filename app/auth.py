"""Argon2id verification, signed JWTs, and OAuth2 scope enforcement."""
import secrets
from datetime import datetime, timezone
from app.logger import log_event
from typing import Annotated

import jwt
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer, SecurityScopes

from app.api_credentials import PASSWORD_HASHER

SCOPES = {"test:read": "Read test entries", "test:write": "Create test entries",
          "users:manage": "Administer API users (administrator only)"}
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token", scopes=SCOPES, auto_error=False)


class AuthService:
    """Verify accounts and issue database-bound tokens with current authorization.

    Args:
        config: Issuer, audience and token lifetime settings.
        secret: Protected persistent HMAC signing key.
        users: Account repository queried on every protected request.
    """
    def __init__(self, config, secret, users):
        self.config = dict(config)
        self.secret = secret
        self.users = users
        self.realm = users.realm()
        self._dummy_hash = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))

    def verify_password(self, username, password):
        """Check Argon2id and current active state without logging credentials.

        Args:
            username: Exact API account name, unrelated to PostgreSQL roles.
            password: Plaintext credential used only for hash verification.

        Returns:
            The active account on success, otherwise None.
        """
        log_event("DEBUG", "API credential verification started", component="auth")
        user = self.users.get_by_username(username)
        try:
            valid = PASSWORD_HASHER.verify(user.password_hash if user else self._dummy_hash, password)
        except (VerificationError, InvalidHashError):
            valid = False
        log_event("DEBUG", "Password hash verification completed", component="auth")
        return user if valid and user is not None and user.is_active else None

    def issue(self, user, requested_scopes):
        """Issue a signed token without granting unavailable requested scopes.

        Args:
            user: Freshly authenticated active database account.
            requested_scopes: Optional explicit OAuth2 scope names.

        Returns:
            Bearer token, type and configured expiration duration.

        Raises:
            HTTPException: 403 if requested scopes exceed allowed permissions.
        """
        allowed = set(SCOPES) if user.role == "administrator" else set(user.scopes).intersection(("test:read", "test:write"))
        scopes = sorted(set(requested_scopes) if requested_scopes else allowed)
        if not set(scopes).issubset(allowed):
            raise HTTPException(403, "Requested permissions are not available", headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'})
        issued = int(datetime.now(timezone.utc).timestamp())
        token = jwt.encode({"sub": str(user.id), "ver": 2, "db": self.realm, "iat": issued,
                            "credential_version": user.credential_version,
                            "exp": issued + self.config["token_ttl_seconds"],
                            "iss": self.config["issuer"], "aud": self.config["audience"],
                            "scopes": scopes}, self.secret, algorithm="HS256")
        return {"access_token": token, "token_type": "bearer", "expires_in": self.config["token_ttl_seconds"]}

    def decode(self, token):
        """Validate JWT claims and reload current account authorization.

        Args:
            token: Untrusted Bearer token, never logged.

        Returns:
            Verified claims with the current database role and test permissions.

        Raises:
            HTTPException: 401 for invalid tokens or absent/inactive accounts.
        """
        log_event("DEBUG", "Access token validation started", component="auth")
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"],
                                 issuer=self.config["issuer"], audience=self.config["audience"],
                                 options={"require": ["sub", "iat", "exp", "iss", "aud", "scopes", "ver", "db", "credential_version"]})
            scopes = payload["scopes"]
            subject = payload["sub"]
            if (not isinstance(subject, str) or not subject.isascii() or not subject.isdecimal()
                    or not 1 <= int(subject) <= 9223372036854775807 or payload["ver"] != 2 or payload["db"] != self.realm
                    or not isinstance(scopes, list)
                    or any(not isinstance(scope, str) or scope not in SCOPES for scope in scopes)
                    or type(payload["iat"]) is not int or type(payload["exp"]) is not int
                    or payload["exp"] <= payload["iat"]):
                raise ValueError
            user = self.users.get_by_id(int(subject))
            if (user is None or not user.is_active
                    or type(payload["credential_version"]) is not int
                    or payload["credential_version"] < 1
                    or payload["credential_version"] != user.credential_version):
                raise ValueError
            # Authorization uses the current database role, never a role frozen in a JWT.
            payload["role"] = user.role
            payload["scopes"] = sorted(set(scopes).intersection(user.scopes).intersection(("test:read", "test:write")))
            log_event("DEBUG", "Access token validation completed", component="auth")
            return payload
        except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
            raise HTTPException(401, "Invalid or expired access token",
                                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'}) from None

    def close(self):
        """Release the service's in-memory signing-key reference."""
        self.secret = None


def require_scopes(security_scopes: SecurityScopes, request: Request,
                   token: Annotated[str | None, Depends(oauth2_scheme)]):
    """Authorize every protected endpoint using current role and permissions.

    Args:
        security_scopes: Permissions declared by the endpoint through Security.
        request: Request carrying the shared authentication service.
        token: Optional Bearer token extracted by the OAuth2 dependency.

    Returns:
        Verified claims for an active administrator or permitted standard user.

    Raises:
        HTTPException: 401 for invalid/missing authentication; 403 for denial.

    Administrator access deliberately bypasses enumeration of endpoint scopes,
    allowing future shared-authorization APIs without a static all-scopes grant.
    """
    if token is None:
        raise HTTPException(401, "Bearer authentication required", headers={"WWW-Authenticate": "Bearer"})
    payload = request.app.state.auth.decode(token)
    if payload["role"] != "administrator" and not set(security_scopes.scopes).issubset(payload["scopes"]):
        required = " ".join(security_scopes.scopes)
        raise HTTPException(403, "Insufficient permissions", headers={
            "WWW-Authenticate": f'Bearer error="insufficient_scope", scope="{required}"'})
    return payload
