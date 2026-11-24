"""Application exceptions and FastAPI handlers producing a uniform error body.

Error body shape: {"error": {"code": str, "message": str, "details": any?}}
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str = "Internal server error", details=None, headers: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        self.headers = headers


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class ExternalServiceError(AppError):
    status_code = 502
    code = "external_service_error"


class UnprocessableError(AppError):
    status_code = 422
    code = "unprocessable"


class RateLimitError(AppError):
    """Upstream (GitHub) rate limit hit."""
    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str, retry_after: int):
        super().__init__(message, {"retry_after_seconds": retry_after}, {"Retry-After": str(retry_after)})
        self.retry_after = retry_after


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


class GatewayTimeoutError(AppError):
    status_code = 504
    code = "upstream_timeout"


def _body(code: str, message: str, details=None) -> dict:
    err = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(_body("validation_error", "Invalid request data", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = "not_found" if exc.status_code == 404 else "http_error"
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    @app.exception_handler(PoolTimeoutError)
    async def _database_unavailable(_: Request, exc: Exception):
        # Connection lost / refused / pool exhausted. Log only the exception type: its text can include
        # the connection string. The client gets a generic, retryable message.
        logger.error("Database error: %s", type(exc).__name__)
        return JSONResponse(
            _body("database_unavailable", "The database is temporarily unavailable. Please try again shortly."),
            status_code=503, headers={"Retry-After": "5"})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(_body("internal_error", "Internal server error"), status_code=500)
