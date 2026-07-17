from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def liveness():
    """k8s liveness probe - process is up."""
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(db: AsyncSession = Depends(get_db)):
    """k8s readiness probe - dependencies (DB) are reachable."""
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}
