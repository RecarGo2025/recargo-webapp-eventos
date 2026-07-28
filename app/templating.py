"""Entorno Jinja2 compartido + helpers de flash messages."""
from __future__ import annotations

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from . import config

templates = Jinja2Templates(directory=str(config.BASE_DIR / "app" / "templates"))
templates.env.globals["brand"] = "RecarGo x Vibra"


def _asset_version() -> str:
    """Versión para cache-busting: mtime del CSS compilado. Cambia en cada
    rebuild/deploy, forzando a los celulares a descargar el CSS/logos nuevos
    en vez de servir una copia cacheada (que rompía las proporciones)."""
    css = config.BASE_DIR / "app" / "static" / "vibra.css"
    try:
        return str(int(css.stat().st_mtime))
    except OSError:
        return "1"


templates.env.globals["asset_v"] = _asset_version()


def flash(request: Request, text: str, kind: str = "info") -> None:
    request.session.setdefault("_flash", []).append({"text": text, "kind": kind})
    request.session["_flash"] = request.session["_flash"]  # marca dirty


def pop_flashes(request: Request) -> list[dict]:
    msgs = request.session.pop("_flash", [])
    return msgs
