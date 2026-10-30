"""Strict administrative input and public-only account output contracts."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictStr, field_validator
from app.password_policy import NewPassword
from app.schemas.catalogue import Selection, PATTERN_HELP
from app.datetimes import CalendarDate, DateBound, date_filter_fields
from app.ordering import UserOrder, Direction
from app.pagination import integer_query
from pydantic import BeforeValidator

Role = Literal["administrator", "supervisor", "standard"]
QueryID = Annotated[int, Field(gt=0, le=9223372036854775807), BeforeValidator(integer_query)]


class UserCreate(BaseModel):
    """Account input; SecretStr prevents accidental representation of passwords."""

    model_config = ConfigDict(extra="forbid")
    username: StrictStr
    password: NewPassword
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
    new_password: NewPassword


class PasswordReset(BaseModel):
    """Administrator replacement using the shared new-password policy."""

    model_config = ConfigDict(extra="forbid")
    new_password: NewPassword


class PublicUser(BaseModel):
    """Public account metadata, intentionally excluding password/hash/scopes."""

    id: int
    username: str
    role: Role
    is_active: bool
    created_at: datetime


class UserQuery(Selection):
    """Public filters combined with AND; secrets are never queryable."""
    id: QueryID | None = Field(default=None, description='Exact account ID.', examples=[1])
    username: str | None = Field(default=None, description='Exact case-sensitive username.', examples=['admin'])
    username_pattern: str | None = Field(default=None, description=PATTERN_HELP, examples=['%admin%'])
    role: Role | None = Field(default=None, description='Exact current role.', examples=['standard'])
    is_active: bool | None = Field(default=None, description='Exact active status, including false.', examples=[True, False])
    created_at_date: CalendarDate | None = date_filter_fields('created_at')['created_at_date'][1]
    created_at_from: DateBound | None = date_filter_fields('created_at')['created_at_from'][1]
    created_at_to: DateBound | None = date_filter_fields('created_at')['created_at_to'][1]
    page: Annotated[int, Field(ge=1), BeforeValidator(integer_query)] = Field(default=1, description='One-based page.', examples=[1, 2])
    page_size: Annotated[int, Field(ge=10, le=50), BeforeValidator(integer_query)] = Field(default=50, description='10–50 records per page.', examples=[50, 10])
    order_by: UserOrder = Field(default='id', description='Public scalar fields only; ID ascending breaks ties.', examples=['id', 'username'])
    order_direction: Direction = Field(default='asc', description='NULLS LAST in both directions.', examples=['asc', 'desc'])
