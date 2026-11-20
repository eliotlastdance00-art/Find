"""Domain errors. Each carries a stable machine-readable code that the UI translates."""

from __future__ import annotations


class DomainError(Exception):
    code = "error"
    http_status = 400

    def __init__(self, message: str | None = None, **params: object) -> None:
        super().__init__(message or self.code)
        self.params = params


class ValidationError(DomainError):
    code = "validation_error"
    http_status = 422


class InvalidCredentials(DomainError):
    code = "invalid_credentials"
    http_status = 401


class NotAuthenticated(DomainError):
    code = "not_authenticated"
    http_status = 401


class Forbidden(DomainError):
    code = "forbidden"
    http_status = 403


class RegistrationClosed(DomainError):
    code = "registration_closed"
    http_status = 403


class UsernameTaken(DomainError):
    code = "username_taken"
    http_status = 409


class WeakPassword(DomainError):
    code = "weak_password"
    http_status = 422


class InvalidUsername(DomainError):
    code = "invalid_username"
    http_status = 422


class TooManyAttempts(DomainError):
    code = "too_many_attempts"
    http_status = 429


class ScanNotFound(DomainError):
    code = "scan_not_found"
    http_status = 404


class ScanStateConflict(DomainError):
    code = "scan_state_conflict"
    http_status = 409


class UnsupportedMedia(DomainError):
    code = "unsupported_media"
    http_status = 415


class FileTooLarge(DomainError):
    code = "file_too_large"
    http_status = 413


class EmptyFile(DomainError):
    code = "empty_file"
    http_status = 422


class MediaTooLong(DomainError):
    code = "media_too_long"
    http_status = 422


class CorruptMedia(DomainError):
    code = "corrupt_media"
    http_status = 422


class ModelUnavailable(DomainError):
    code = "model_unavailable"
    http_status = 503
