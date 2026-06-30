from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Streamlinify")
    app.state.session = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    from .web.routes_build import router as build_router
    from .web.routes_gallery import router as gallery_router
    from .web.routes_ingest import router as ingest_router

    app.include_router(ingest_router)
    app.include_router(gallery_router)
    app.include_router(build_router)
    return app
