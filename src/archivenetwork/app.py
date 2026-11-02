from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .loader import flociversion
from .loader.dockerctl import COMPOSE_FILE
from .web.registry import WorkspaceRegistry

# uvicorn's own logger, so the line prints in the server console with uvicorn's formatting.
_log = logging.getLogger("uvicorn.error")


def _log_floci_version() -> None:
    report = flociversion.report(settings.floci_endpoint_url, COMPOSE_FILE)
    level = logging.INFO if report.status in ("up_to_date", "unknown") else logging.WARNING
    _log.log(level, "floci version check: %s", report.message)


def _start_floci_version_check(app: FastAPI) -> None:
    """Run the check off the event loop: it makes network calls, and startup must not wait."""
    app.state.floci_version_thread = None
    if settings.floci_version_check:
        thread = threading.Thread(target=_log_floci_version, name="floci-version", daemon=True)
        thread.start()
        app.state.floci_version_thread = thread


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # When the browser aborts a video Range stream mid-flight (it already has
    # the frame it wanted), event loops (Windows Proactor, POSIX/Unix selector,
    # kqueue) raise ConnectionResetError, BrokenPipeError, or
    # ConnectionAbortedError inside their connection_lost callbacks — outside
    # any request handler, so only the loop's exception handler sees it.
    # Swallow those errors; forward everything else to the previous/default handler.
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()

    def _quiet_reset(loop, context):
        if isinstance(
            context.get("exception"),
            (ConnectionResetError, BrokenPipeError, ConnectionAbortedError),
        ):
            return
        (previous or loop.default_exception_handler)(context)

    loop.set_exception_handler(_quiet_reset)
    _start_floci_version_check(app)
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
        # Must cover every method the routers serve — a method missing here fails the browser's
        # *preflight* with `400 Disallowed CORS method`, so the route is never reached and the
        # failure looks like a broken endpoint rather than a CORS policy. `DELETE` was the
        # casualty (`DELETE /api/dev/table`). `*` keeps the list from drifting as routes are added;
        # it is not a widening — `allow_origins`/`allow_origin_regex` still gate who may ask.
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .web.routes_build import router as build_router
    from .web.routes_dev import router as dev_router
    from .web.routes_docker import router as docker_router
    from .web.routes_gallery import router as gallery_router
    from .web.routes_ingest import router as ingest_router
    from .web.routes_ready import router as ready_router
    from .web.routes_s3 import router as s3_router
    from .web.routes_video import router as video_router
    from .web.routes_workspaces import router as workspaces_router

    app.include_router(ingest_router)
    app.include_router(workspaces_router)
    app.include_router(gallery_router)
    app.include_router(video_router)
    app.include_router(build_router)
    app.include_router(ready_router)
    app.include_router(s3_router)
    app.include_router(docker_router)
    app.include_router(dev_router)

    # Dev-mode object store, served so the Dev panel can render each row straight from its
    # `storage_path`. In production that same key is fetched from a CDN domain instead — the
    # DB stores the key, never the base URL.
    settings.media_root.mkdir(parents=True, exist_ok=True)
    app.mount(
        settings.media_base_url,
        StaticFiles(directory=settings.media_root),
        name="media",
    )
    return app
