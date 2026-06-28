from __future__ import annotations

import uvicorn

from .config import settings


def run() -> None:
    uvicorn.run("streamlinify.app:create_app", factory=True, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
