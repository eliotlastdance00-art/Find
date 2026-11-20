from __future__ import annotations

from datetime import UTC, datetime

import jwt
import pytest

from dfd.domain import errors
from dfd.domain.entities import Role, User
from dfd.infrastructure.security import (
    Argon2PasswordHasher,
    JwtTokenService,
    SlidingWindowLimiter,
)

SECRET = "0123456789abcdef0123456789abcdef"
USER = User(7, "eliot", "hash", Role.USER, datetime.now(UTC))


def test_password_hash_roundtrip() -> None:
    hasher = Argon2PasswordHasher()
    digest = hasher.hash("correct-horse")
    assert digest.startswith("$argon2id$")
    assert "correct-horse" not in digest
    assert hasher.verify("correct-horse", digest)
    assert not hasher.verify("wrong", digest)
    assert not hasher.verify("correct-horse", "not-a-hash")


def test_password_hashes_are_salted() -> None:
    hasher = Argon2PasswordHasher()
    assert hasher.hash("same") != hasher.hash("same")


def test_session_token_roundtrip() -> None:
    tokens = JwtTokenService(SECRET, 1)
    assert tokens.verify(tokens.issue(USER)) == 7
    assert tokens.ttl_seconds == 3600


def test_token_rejects_garbage_wrong_key_and_expiry() -> None:
    tokens = JwtTokenService(SECRET, 1)
    assert tokens.verify("garbage") is None
    assert tokens.verify("") is None
    assert JwtTokenService("another-secret-another-secret-00", 1).verify(tokens.issue(USER)) is None
    expired = jwt.encode({"sub": "7", "scope": "session", "exp": 1}, SECRET, algorithm="HS256")
    assert tokens.verify(expired) is None


def test_token_rejects_unsigned_tokens() -> None:
    tokens = JwtTokenService(SECRET, 1)
    unsigned = jwt.encode({"sub": "7", "scope": "session"}, "", algorithm="none")
    assert tokens.verify(unsigned) is None


def test_media_token_is_bound_to_scope_and_scan() -> None:
    tokens = JwtTokenService(SECRET, 1)
    media = tokens.issue_media(7, "scan-a")
    assert tokens.verify_media(media, "scan-a") == 7
    assert tokens.verify_media(media, "scan-b") is None
    assert tokens.verify(media) is None  # a media token is not a session
    assert tokens.verify_media(tokens.issue(USER), "scan-a") is None


def test_limiter_blocks_after_repeated_failures_and_resets() -> None:
    limiter = SlidingWindowLimiter(max_failures=3, window_s=60)
    for _ in range(3):
        limiter.check("ip")
        limiter.failure("ip")
    with pytest.raises(errors.TooManyAttempts):
        limiter.check("ip")
    limiter.check("other-ip")
    limiter.reset("ip")
    limiter.check("ip")
