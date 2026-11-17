"""OrgWeave API application factory and lifespan."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from orgweave_shared.logging import configure_logging, get_logger
from orgweave_shared.redis import create_redis

from app.api.router import api_router
from app.core.config import get_settings
from app.core.db import create_engine, create_session_factory
from app.core.errors import register_error_handlers
from app.infrastructure.health.probes import build_probes
from app.infrastructure.storage import create_minio_client, ensure_bucket
from app.ws.v1 import router as ws_router

logger = get_logger("orgweave.api")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    logger.info("api starting", extra={"service": "api"})

    engine = create_engine(settings)
    redis_client = create_redis(settings)
    minio_client = create_minio_client(settings)

    try:
        created = await ensure_bucket(
            minio_client,
            settings.minio_bucket,
            timeout_seconds=settings.health_check_timeout_seconds,
        )
        logger.info(
            "object storage bucket ready" if created else "object storage bucket missing",
            extra={"service": "api"},
        )
    except Exception:
        logger.exception(
            "object storage bootstrap failed; readiness will report it",
            extra={"service": "api"},
        )

    app.state.engine = engine
    app.state.settings = settings
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = redis_client
    app.state.minio = minio_client
    app.state.health_probes = build_probes(
        settings,
        engine=engine,
        redis_client=redis_client,
        minio_client=minio_client,
    )

    try:
        yield
    finally:
        logger.info("api stopping", extra={"service": "api"})
        await redis_client.aclose()
        await engine.dispose()


app = FastAPI(
    title="OrgWeave API",
    description="AI Organization Operating System — Phase 0 infrastructure API",
    version=settings.app_version,
    docs_url="/api/v1/docs",
    redoc_url=None,
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


app.include_router(api_router, prefix="/api/v1")
app.include_router(ws_router)
register_error_handlers(app)
