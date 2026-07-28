"""App RecarGo x Vibra: alquiler temporal de baterías. FastAPI + Jinja2 + SQLite."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import config, db
from .routes import admin, public
from .templating import templates  # noqa: F401 (asegura init de Jinja)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="RecarGo x Vibra — Alquiler de baterías", docs_url=None, redoc_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    session_cookie="vibra_session",
    max_age=60 * 60 * 24,  # 24h
    same_site="lax",
    https_only=False,  # nginx termina SSL; la cookie viaja por el proxy interno
)

app.mount("/static", StaticFiles(directory=config.BASE_DIR / "app" / "static"), name="static")

app.include_router(public.router)
app.include_router(admin.router)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    logging.getLogger("app").info(
        "Iniciada. TZ=%s  Bajie mock=%s  usuarios admin=%d",
        config.TZ_NAME,
        config.BAJIE_MOCK,
        len(config.ADMIN_USERS),
    )


@app.get("/health")
def health() -> dict:
    return {"ok": True}
