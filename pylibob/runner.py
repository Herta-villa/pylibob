from __future__ import annotations

from pylibob.asgi import _asgi_app

import uvicorn


def run_server():
    uvicorn.run(_asgi_app)
