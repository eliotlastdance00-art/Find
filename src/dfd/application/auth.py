"""Authentication use cases."""

from __future__ import annotations

import re

from dfd.domain import errors
from dfd.domain.entities import Role, User
from dfd.domain.ports import AttemptLimiter, PasswordHasher, TokenService, UserRepository

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
        limiter: AttemptLimiter,
        allow_registration: bool,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        self._limiter = limiter
        self._allow_registration = allow_registration

    def register(self, username: str, password: str) -> tuple[User, str]:
        """Create an account. The very first account becomes the administrator."""
        username = username.strip()
        first_user = self._users.count() == 0
        if not first_user and not self._allow_registration:
            raise errors.RegistrationClosed()
        user = self.create_user(username, password, Role.ADMIN if first_user else Role.USER)
        return user, self._tokens.issue(user)

    def create_user(self, username: str, password: str, role: Role) -> User:
        if not USERNAME_PATTERN.fullmatch(username):
            raise errors.InvalidUsername()
        if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
            raise errors.WeakPassword()
        if self._users.get_by_username(username) is not None:
            raise errors.UsernameTaken()
        return self._users.add(username, self._hasher.hash(password), role)

    def ensure_admin(self, username: str, password: str) -> None:
        """Idempotently create the administrator configured through the environment."""
        if username and password and self._users.get_by_username(username) is None:
            self.create_user(username, password, Role.ADMIN)

    def login(self, username: str, password: str, client: str) -> tuple[User, str]:
        username = username.strip()
        key = f"{client}|{username.lower()}"
        self._limiter.check(key)
        user = self._users.get_by_username(username)
        # Hash even for unknown users so response time does not reveal which names exist.
        stored = user.password_hash if user else self._hasher.hash("dummy-password")
        if not self._hasher.verify(password, stored) or user is None:
            self._limiter.failure(key)
            raise errors.InvalidCredentials()
        self._limiter.reset(key)
        return user, self._tokens.issue(user)

    def authenticate(self, token: str | None) -> User:
        return self._load(self._tokens.verify(token) if token else None)

    def authenticate_media(self, token: str | None, scan_id: str) -> User:
        """Resolve the user behind a media token that is valid for ``scan_id`` only."""
        return self._load(self._tokens.verify_media(token, scan_id) if token else None)

    def media_token(self, user: User, scan_id: str) -> str:
        return self._tokens.issue_media(user.id, scan_id)

    def _load(self, user_id: int | None) -> User:
        user = self._users.get(user_id) if user_id is not None else None
        if user is None:
            raise errors.NotAuthenticated()
        return user
