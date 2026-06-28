from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

WEB_DIR = Path(__file__).parent / "web"


def create_app() -> FastAPI:
    app = FastAPI(title="Streamlinify")
    app.state.templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
    app.state.session = None
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    from .web.routes_build import router as build_router
    from .web.routes_gallery import router as gallery_router
    from .web.routes_ingest import router as ingest_router

    app.include_router(ingest_router)
    app.include_router(gallery_router)
    app.include_router(build_router)
    return app
