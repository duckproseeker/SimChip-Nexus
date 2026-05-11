from __future__ import annotations


class AppError(Exception):
    def __init__(self, message: str, code: str = "APP_ERROR") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="NOT_FOUND")


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="CONFLICT")


class ValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="VALIDATION_ERROR")
