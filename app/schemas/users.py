"""Strict administrative input and public-only account output contracts."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictStr, field_validator

Role = Literal["administrator", "standard"]


class UserCreate(BaseModel):
    """Account input; SecretStr prevents accidental representation of passwords."""

    model_config = ConfigDict(extra="forbid")
    username: StrictStr
    password: Annotated[SecretStr, Field(strict=True, min_length=1)]
    role: Role = "standard"

    @field_validator("username")
    @classmethod
    def valid_username(cls, value):
        """Reject empty/control-only names without silently changing identity."""
        if not value.strip() or any(not char.isprintable() for char in value):
            raise ValueError("Invalid username")
        return value


class RoleUpdate(BaseModel):
    """Replace the complete fixed role, rejecting unknown fields."""

    model_config = ConfigDict(extra="forbid")
    role: Role


class PasswordChange(BaseModel):
    """Self-service confirmation; credentials must never enter logs or reprs."""

    model_config = ConfigDict(extra="forbid")
    current_password: Annotated[SecretStr, Field(strict=True, min_length=1)]
    new_password: Annotated[SecretStr, Field(strict=True, min_length=1)]


class PasswordReset(BaseModel):
    """Administrator replacement using the same strict, nonempty password policy."""

    model_config = ConfigDict(extra="forbid")
    new_password: Annotated[SecretStr, Field(strict=True, min_length=1)]


class PublicUser(BaseModel):
    """Public account metadata, intentionally excluding password/hash/scopes."""

    id: int
    username: str
    role: Role
    is_active: bool
    created_at: datetime
