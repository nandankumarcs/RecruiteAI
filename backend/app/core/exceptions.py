"""
Custom exception classes for RecruiteAI.

All application-specific errors should inherit from RecruiteAIError
so they can be caught and handled uniformly by the exception handlers.
"""

from fastapi import HTTPException, status


class RecruiteAIError(HTTPException):
    """Base exception for all RecruiteAI application errors."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)


class AuthenticationError(RecruiteAIError):
    """Raised when authentication fails (invalid credentials, expired token)."""

    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )


class NotFoundError(RecruiteAIError):
    """Raised when a requested resource is not found."""

    def __init__(self, resource: str = "Resource", detail: str | None = None):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail or f"{resource} not found",
        )


class ConflictError(RecruiteAIError):
    """Raised when a resource already exists (e.g., duplicate email)."""

    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


class ValidationError(RecruiteAIError):
    """Raised when request data fails business logic validation."""

    def __init__(self, detail: str = "Validation error"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class CallInProgressError(RecruiteAIError):
    """Raised when trying to start a call while another is in progress."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another call is currently in progress. Please wait for it to complete.",
        )
