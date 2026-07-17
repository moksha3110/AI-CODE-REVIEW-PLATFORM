from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.routes import auth, health
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler, unhandled_exception_handler
from app.core.logging import configure_logging, get_logger
from app.middleware.request_context import RequestContextMiddleware

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("service_starting", env=get_settings().env)
    yield
    logger.info("service_stopping")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Auth Service",
        description="Handles GitHub OAuth login and JWT issuance for the AI Code Review Platform.",
        version="1.0.0",
        lifespan=lifespan,
        # Swagger/OpenAPI is generated automatically at /docs and /openapi.json
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")

    # Exposes /metrics for Prometheus scraping - request rate, error rate,
    # duration histograms per route, with essentially no code on our part.
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    return app


app = create_app()
