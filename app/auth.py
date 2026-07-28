"""Autenticación admin por cookie de sesión firmada."""
from __future__ import annotations

from starlette.requests import Request

from . import config


def authenticate(user: str, password: str) -> bool:
    expected = config.ADMIN_USERS.get(user)
    return expected is not None and expected == password


def current_user(request: Request) -> str | None:
    return request.session.get("user")


def is_logged_in(request: Request) -> bool:
    return current_user(request) is not None


def login(request: Request, user: str) -> None:
    request.session["user"] = user


def logout(request: Request) -> None:
    request.session.clear()


def selected_station_id(request: Request) -> int | None:
    val = request.session.get("station_id")
    return int(val) if val is not None else None


def set_station(request: Request, station_id: int) -> None:
    request.session["station_id"] = int(station_id)
