from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .config import get_settings
from .providers import available_providers  # noqa: F401  (ensures adapters register)
from .web import auth, bots, releases, repos, routes, users
from .web.deps import LoginRequired, redirect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = get_settings()
app = FastAPI(title="Release Radar", version=__version__)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_signing_key,
    https_only=settings.session_https_only,
    same_site="lax",
    max_age=60 * 60 * 12,  # 12h — was unset (Starlette default: 2 weeks)
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    return redirect("/login")


app.include_router(auth.router)
app.include_router(releases.router)
app.include_router(repos.router)
app.include_router(bots.router)
app.include_router(routes.router)
app.include_router(users.router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "version": __version__}
