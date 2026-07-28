"""Configuración de la app, leída del entorno (.env)."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9 (el VPS corre 3.8)
    from backports.zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-key-change-me")

# Usuarios admin: "user:pass,user2:pass2" -> {user: pass}
def _parse_users(raw: str) -> dict[str, str]:
    users: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        user, _, pw = pair.partition(":")
        user, pw = user.strip(), pw.strip()
        if user and pw:
            users[user] = pw
    return users


ADMIN_USERS = _parse_users(os.getenv("ADMIN_USERS", "admin:admin"))

BAJIE_BASE_URL = os.getenv(
    "BAJIE_BASE_URL", "https://developer.chargenow.top/cdb-open-api/v1"
).rstrip("/")
BAJIE_BASIC_AUTH_KEY = os.getenv("BAJIE_CHARGING_BASIC_AUTH_KEY", "")
BAJIE_MOCK = os.getenv("BAJIE_MOCK", "0") == "1"

DB_PATH = Path(os.getenv("DB_PATH", "vibra.db"))
if not DB_PATH.is_absolute():
    DB_PATH = BASE_DIR / DB_PATH

TZ_NAME = os.getenv("TZ_NAME", "America/Lima")
TZ = ZoneInfo(TZ_NAME)

# Defaults de configuración de negocio (solo para el seed inicial).
DEFAULT_TARIFA_POR_HORA = "10.00"
DEFAULT_TOLERANCIA_MIN = "4"
