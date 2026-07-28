"""Acceso a SQLite con WAL. Timestamps guardados como epoch (REAL, UTC)."""
from __future__ import annotations

import sqlite3
import threading

from . import config

# Serializa las escrituras críticas (crear/finalizar renta) por encima del
# locking de SQLite, para blindar la comprobación "un DNI = una renta activa".
write_lock = threading.Lock()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(
        config.DB_PATH,
        timeout=10,
        check_same_thread=False,
        isolation_level=None,  # autocommit; controlamos transacciones a mano
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stations (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre    TEXT NOT NULL,
    device_id TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS rentals (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    dni                     TEXT NOT NULL,
    station_id              INTEGER NOT NULL REFERENCES stations(id),
    start_at                REAL NOT NULL,
    end_at                  REAL,
    status                  TEXT NOT NULL DEFAULT 'activa',
    tarifa_hora_snapshot    REAL NOT NULL,
    tolerancia_min_snapshot INTEGER NOT NULL,
    tope_max_snapshot       REAL NOT NULL DEFAULT 0,
    amount_final            REAL,
    created_by              TEXT NOT NULL,
    eject_ok                INTEGER NOT NULL DEFAULT 0,
    eject_msg               TEXT NOT NULL DEFAULT ''
);

-- Un DNI solo puede tener UNA renta activa a la vez (garantía a nivel de motor).
CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_dni
    ON rentals(dni) WHERE status = 'activa';

CREATE INDEX IF NOT EXISTS idx_rentals_dni    ON rentals(dni);
CREATE INDEX IF NOT EXISTS idx_rentals_status ON rentals(status);
"""


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        _seed(conn)
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Migraciones idempotentes para bases ya creadas (CREATE IF NOT EXISTS no
    agrega columnas nuevas a una tabla existente)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(rentals)").fetchall()}
    if "tope_max_snapshot" not in cols:
        conn.execute(
            "ALTER TABLE rentals ADD COLUMN tope_max_snapshot REAL NOT NULL DEFAULT 0"
        )


def _seed(conn: sqlite3.Connection) -> None:
    # Config inicial (solo si no existe la clave).
    defaults = {
        "tarifa_por_hora": config.DEFAULT_TARIFA_POR_HORA,
        "tolerancia_min": config.DEFAULT_TOLERANCIA_MIN,
        "tope_max": config.DEFAULT_TOPE_MAX,
    }
    for k, v in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO config(key, value) VALUES (?, ?)", (k, v)
        )

    # Dos estaciones con device_id vacío (se editan desde el admin el día del evento).
    (count,) = conn.execute("SELECT COUNT(*) FROM stations").fetchone()
    if count == 0:
        conn.execute(
            "INSERT INTO stations(nombre, device_id) VALUES (?, ?)",
            ("Estación 1", ""),
        )
        conn.execute(
            "INSERT INTO stations(nombre, device_id) VALUES (?, ?)",
            ("Estación 2", ""),
        )


# ── Helpers de config ────────────────────────────────────────────
def get_config(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_config(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO config(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
