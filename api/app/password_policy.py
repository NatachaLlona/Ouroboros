"""Shared policy for newly set credentials; existing hashes remain valid."""
from typing import Annotated
from pydantic import Field, SecretStr

MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 1024
PASSWORD_HELP = ('15–1024 Unicode characters, including spaces. Passphrases and password-manager paste '
                 'are supported; no composition rules or silent truncation. Existing passwords remain valid.')
NewPassword = Annotated[SecretStr, Field(strict=True, min_length=MIN_PASSWORD_LENGTH,
    max_length=MAX_PASSWORD_LENGTH, description=PASSWORD_HELP)]


def validate_new_password(value):
    """Validate terminal enrollment without normalizing or truncating secrets."""
    if not isinstance(value, str) or not MIN_PASSWORD_LENGTH <= len(value) <= MAX_PASSWORD_LENGTH:
        raise ValueError(PASSWORD_HELP)
    return value
