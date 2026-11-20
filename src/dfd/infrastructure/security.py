"""Password hashing (Argon2id), signed session tokens (JWT) and login throttling."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import Argon2Error, InvalidHashError

from dfd.domain import errors
from dfd.domain.entities import User

_ALGORITHM = "HS256"
_MEDIA_TTL = timedelta(minutes=60)


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._hasher = _Argon2()

    def hash(self, password: str) -> str:
        return str(self._hasher.hash(password))

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return bool(self._hasher.verify(password_hash, password))
        except (Argon2Error, InvalidHashError):
            return False


class JwtTokenService:
    def __init__(self, secret: str, ttl_hours: int) -> None:
        if len(secret) < 32:
            raise ValueError("DFD_SECRET_KEY must be at least 32 characters")
        self._secret = secret
        self._ttl = timedelta(hours=ttl_hours)

    @property
    def ttl_seconds(self) -> int:
        return int(self._ttl.total_seconds())

    def issue(self, user: User) -> str:
        now = datetime.now(UTC)
        payload = {"sub": str(user.id), "iat": now, "exp": now + self._ttl, "scope": "session"}
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def verify(self, token: str) -> int | None:
        payload = self._decode(token)
        if payload is None or payload.get("scope") != "session":
            return None
        return int(payload["sub"])

    def issue_media(self, user_id: int, scan_id: str) -> str:
        """Short-lived token that only unlocks the files of one scan.

        Browsers cannot attach an Authorization header to <img>, <video> or download links,
        so those URLs carry this narrowly scoped token instead of the session token.
        """
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": now + _MEDIA_TTL,
            "scope": "media",
            "scan": scan_id,
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def verify_media(self, token: str, scan_id: str) -> int | None:
        payload = self._decode(token)
        if payload is None or payload.get("scope") != "media" or payload.get("scan") != scan_id:
            return None
        return int(payload["sub"])

    def _decode(self, token: str) -> dict[str, Any] | None:
        try:
            payload: dict[str, Any] = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
            int(payload["sub"])
        except (jwt.PyJWTError, KeyError, ValueError, TypeError):
            return None
        return payload


class SlidingWindowLimiter:
    """Blocks a key after ``max_failures`` failed attempts within ``window_s`` seconds."""

    def __init__(self, max_failures: int = 8, window_s: float = 300.0) -> None:
        self._max = max_failures
        self._window = window_s
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        cutoff = time.monotonic() - self._window
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def check(self, key: str) -> None:
        with self._lock:
            if len(self._recent(key)) >= self._max:
                raise errors.TooManyAttempts()

    def failure(self, key: str) -> None:
        with self._lock:
            self._recent(key)
            self._failures.setdefault(key, []).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
