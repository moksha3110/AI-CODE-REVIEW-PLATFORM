import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.routes import health
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler, unhandled_exception_handler
from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.middleware.request_context import RequestContextMiddleware
from app.services.outbox_relay import run_outbox_relay
from app.services.rabbitmq_consumer import run_consumer
from app.services.rabbitmq_publisher import RabbitMQPublisher

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("service_starting", env=settings.env)

    publisher = RabbitMQPublisher()
    await publisher.connect()
    relay_task = asyncio.create_task(run_outbox_relay(AsyncSessionLocal, publisher))
    consumer_task = asyncio.create_task(run_consumer(AsyncSessionLocal))

    yield

    consumer_task.cancel()
    relay_task.cancel()
    await publisher.close()
    logger.info("service_stopping")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Analysis Service",
        description=(
            "Consumes push events, clones the changed files, and runs them "
            "through Claude to produce structured code reviews for the "
            "Review Service to persist."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health.router, prefix="/api/v1")

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    return app


app = create_app()
