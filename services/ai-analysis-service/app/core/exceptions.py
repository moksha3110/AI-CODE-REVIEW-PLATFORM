"""
Every error response across the platform follows the same envelope:

    {"error": {"code": "invalid_credentials", "message": "...", "request_id": "..."}}

so the frontend can handle errors uniformly regardless of which service
produced them. This service's HTTP surface is only /healthz, /readyz, and
/metrics - these classes matter mainly for the consumer's error handling.
"""
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


class InstallationTokenError(AppError):
    """Couldn't get a clone token from Repository Service (network, auth, or 4xx)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "installation_token_error"


class GitCloneError(AppError):
    """git clone/fetch/checkout failed."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "git_clone_error"


class AIProviderError(AppError):
    """The Claude API call failed or returned something we couldn't use."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "ai_provider_error"


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
