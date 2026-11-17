"""v1 API endpoints."""

from app.api.v1.health import router as health_router
from app.api.v1.meta import router as meta_router

__all__ = ["health_router", "meta_router"]
