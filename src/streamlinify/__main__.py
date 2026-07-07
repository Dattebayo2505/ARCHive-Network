"""Enable ``python -m streamlinify`` to start the API server.

A convenience for non-uv setups (plain ``pip install -e .`` + ``python``) so the
server can be launched without the ``streamlinify`` console script on PATH.
"""

from .main import run

if __name__ == "__main__":
    run()
