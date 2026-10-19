"""In-memory account repository used only by unit tests."""
from app.api_users import APIUser, TEST_SCOPES
from app.database import DatabaseError
from dataclasses import replace


class MemoryAPIUsers:
    def __init__(self):
        self.users = {}

    def realm(self):
        return "unit_test"

    def get_by_username(self, username):
        return next((user for user in self.users.values() if user.username == username), None)

    def get_by_id(self, user_id):
        return self.users.get(user_id)

    def count(self):
        return len(self.users)

    def create(self, username, password_hash, scopes=TEST_SCOPES, role="standard"):
        if self.get_by_username(username):
            raise DatabaseError("API username already exists")
        user = APIUser(len(self.users)+1, username, password_hash, True, tuple(scopes), role)
        self.users[user.id] = user
        return user

    def import_legacy(self, username, password_hash):
        user = self.get_by_username(username)
        if user:
            if user.password_hash != password_hash or set(user.scopes) != set(TEST_SCOPES) or not user.is_active:
                raise DatabaseError("Legacy account conflict")
            return user
        return self.create(username, password_hash)

    def has_administrator(self):
        return any(user.role == "administrator" and user.is_active for user in self.users.values())

    def bootstrap_administrator(self, username, password_hash=None):
        if self.has_administrator():
            raise DatabaseError("An administrator already exists")
        if password_hash is not None:
            return self.create(username, password_hash, role="administrator")
        user = self.get_by_username(username)
        if user is None or not user.is_active:
            raise DatabaseError("Choose an existing active account")
        user = replace(user, role="administrator")
        self.users[user.id] = user
        return user
