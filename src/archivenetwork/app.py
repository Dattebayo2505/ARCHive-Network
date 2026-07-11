from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .web.registry import WorkspaceRegistry


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # When the browser aborts a video Range stream mid-flight (it already has
    # the frame it wanted), Windows' Proactor loop raises ConnectionResetError
    # inside its own connection_lost callback — outside any request handler, so
    # only the loop's exception handler sees it. Swallow that one error;
    # forward everything else to the previous/default handler.
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()

    def _quiet_reset(loop, context):
        if isinstance(context.get("exception"), ConnectionResetError):
            return
        (previous or loop.default_exception_handler)(context)

    loop.set_exception_handler(_quiet_reset)
    try:
        yield
    finally:
        loop.set_exception_handler(previous)


def create_app() -> FastAPI:
    app = FastAPI(title="ARCHive Network", lifespan=_lifespan)
    app.state.session = None
    app.state.registry = WorkspaceRegistry(settings.workspace_dir / "workspaces.json")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    from .web.routes_build import router as build_router
    from .web.routes_gallery import router as gallery_router
    from .web.routes_ingest import router as ingest_router
    from .web.routes_video import router as video_router
    from .web.routes_workspaces import router as workspaces_router

    app.include_router(ingest_router)
    app.include_router(workspaces_router)
    app.include_router(gallery_router)
    app.include_router(video_router)
    app.include_router(build_router)
    return app
