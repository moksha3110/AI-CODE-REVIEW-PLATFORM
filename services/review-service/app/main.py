import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.routes import health, reviews
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler, unhandled_exception_handler
from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.middleware.request_context import RequestContextMiddleware
from app.services.rabbitmq_consumer import run_consumer

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("service_starting", env=settings.env)

    consumer_task = asyncio.create_task(run_consumer(AsyncSessionLocal))

    yield

    consumer_task.cancel()
    logger.info("service_stopping")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Review Service",
        description=(
            "Persists AI-generated code reviews and exposes the REST API "
            "the dashboard uses for repository history and quality trends."
        ),
        version="1.0.0",
        lifespan=lifespan,
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
    app.include_router(reviews.router, prefix="/api/v1")

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    return app


app = create_app()
