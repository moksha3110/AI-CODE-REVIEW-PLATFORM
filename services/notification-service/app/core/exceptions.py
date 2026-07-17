from fastapi import Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "app_error"

    def __init__(self, message: str, code: str | None = None, status_code: int | None = None):
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        super().__init__(message)


class NotificationNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "notification_not_found"


class OwnerLookupError(AppError):
    """Couldn't resolve which user owns a repository via Repository
    Service's internal API (network, auth, or 4xx)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "owner_lookup_error"


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "request_id": request_id}},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "internal_server_error",
                "message": "an unexpected error occurred",
                "request_id": request_id,
            }
        },
    )
