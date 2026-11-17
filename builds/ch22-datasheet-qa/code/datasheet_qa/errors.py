"""Custom exception types and error formatting for Datasheet Q&A Tool."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base exception for all application-level errors.

    Carries a user-facing message separate from the internal detail.
    """

    def __init__(self, user_message: str, detail: str | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


class PdfIngestionError(AppError):
    """Raised when a PDF cannot be read or extracted."""


class MissingApiKeyError(AppError):
    """Raised when the Anthropic API key is not configured."""


class LlmApiError(AppError):
    """Raised when the Anthropic API call fails."""


class ChromaError(AppError):
    """Raised when Chroma database operations fail."""


def error_response(error: AppError) -> dict[str, Any]:
    """Return a JSON-serialisable dict for an AppError."""
    resp: dict[str, Any] = {"status": "error", "message": error.user_message}
    if error.detail:
        resp["detail"] = error.detail
    return resp