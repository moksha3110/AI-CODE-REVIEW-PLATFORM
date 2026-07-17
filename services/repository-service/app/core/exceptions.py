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


class InvalidWebhookSignatureError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "invalid_webhook_signature"


class InstallationNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "installation_not_found"


class RepositoryNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "repository_not_found"


class GitHubAPIError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "github_api_error"


class InternalAuthError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "internal_auth_error"


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
