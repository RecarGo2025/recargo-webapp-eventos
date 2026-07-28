"""Lógica de negocio de rentas: crear, finalizar, cancelar, consultar."""
from __future__ import annotations

import sqlite3

from . import db, pricing, timeutil
from .bajie import EjectResult


def normalize_dni(raw: str) -> str:
    """Documento SIN restricciones de formato (DNI, pasaporte, CE, etc.).
    Solo se normaliza para que la búsqueda coincida: trim + mayúsculas."""
    return (raw or "").strip().upper()


class RentaActivaExiste(Exception):
    """El DNI ya tiene una renta activa."""

    def __init__(self, rental_id: int):
        self.rental_id = rental_id
        super().__init__("El DNI ya tiene una renta activa")


# ── Consultas ────────────────────────────────────────────────────
def get_rental(conn: sqlite3.Connection, rental_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT r.*, s.nombre AS station_nombre "
        "FROM rentals r JOIN stations s ON s.id = r.station_id "
        "WHERE r.id = ?",
        (rental_id,),
    ).fetchone()


def active_for_dni(conn: sqlite3.Connection, dni: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT r.*, s.nombre AS station_nombre "
        "FROM rentals r JOIN stations s ON s.id = r.station_id "
        "WHERE r.dni = ? AND r.status = 'activa' LIMIT 1",
        (dni,),
    ).fetchone()


def find_for_public(conn: sqlite3.Connection, dni: str) -> sqlite3.Row | None:
    """Renta activa del DNI; si no hay, la última finalizada; si no, None."""
    row = active_for_dni(conn, dni)
    if row:
        return row
    return conn.execute(
        "SELECT r.*, s.nombre AS station_nombre "
        "FROM rentals r JOIN stations s ON s.id = r.station_id "
        "WHERE r.dni = ? AND r.status = 'finalizada' "
        "ORDER BY r.end_at DESC LIMIT 1",
        (dni,),
    ).fetchone()


def list_rentals(
    conn: sqlite3.Connection, status: str | None = None, dni: str | None = None
) -> list[sqlite3.Row]:
    q = (
        "SELECT r.*, s.nombre AS station_nombre "
        "FROM rentals r JOIN stations s ON s.id = r.station_id WHERE 1=1"
    )
    params: list = []
    if status:
        q += " AND r.status = ?"
        params.append(status)
    if dni:
        q += " AND r.dni LIKE ?"
        params.append(f"%{dni}%")
    q += " ORDER BY r.start_at DESC"
    return conn.execute(q, params).fetchall()


# ── Mutaciones ───────────────────────────────────────────────────
def create_rental(
    conn: sqlite3.Connection,
    dni: str,
    station_id: int,
    created_by: str,
    eject: EjectResult,
) -> int:
    """Crea la renta SIEMPRE (regla RecarGo). El resultado de expulsión solo se
    registra como flag; nunca bloquea. Levanta RentaActivaExiste si el DNI ya
    tiene una activa (garantizado por el índice único parcial)."""
    tarifa = float(db.get_config(conn, "tarifa_por_hora", "10.00"))
    tolerancia = int(db.get_config(conn, "tolerancia_min", "4"))
    start_at = timeutil.now_epoch()

    with db.write_lock:
        existing = active_for_dni(conn, dni)
        if existing:
            raise RentaActivaExiste(existing["id"])
        try:
            cur = conn.execute(
                "INSERT INTO rentals "
                "(dni, station_id, start_at, status, tarifa_hora_snapshot, "
                " tolerancia_min_snapshot, created_by, eject_ok, eject_msg) "
                "VALUES (?, ?, ?, 'activa', ?, ?, ?, ?, ?)",
                (
                    dni,
                    station_id,
                    start_at,
                    tarifa,
                    tolerancia,
                    created_by,
                    1 if eject.ok else 0,
                    eject.msg[:300],
                ),
            )
        except sqlite3.IntegrityError:
            existing = active_for_dni(conn, dni)
            raise RentaActivaExiste(existing["id"] if existing else 0)
        return int(cur.lastrowid)


def finalize_rental(conn: sqlite3.Connection, rental_id: int) -> sqlite3.Row | None:
    """Fija end_at y amount_final aplicando la regla de precio con snapshot."""
    with db.write_lock:
        row = conn.execute(
            "SELECT * FROM rentals WHERE id = ? AND status = 'activa'", (rental_id,)
        ).fetchone()
        if not row:
            return None
        end_at = timeutil.now_epoch()
        duracion_min = (end_at - row["start_at"]) / 60.0
        _, monto = pricing.calcular_monto(
            duracion_min,
            row["tolerancia_min_snapshot"],
            row["tarifa_hora_snapshot"],
        )
        conn.execute(
            "UPDATE rentals SET end_at = ?, amount_final = ?, status = 'finalizada' "
            "WHERE id = ?",
            (end_at, monto, rental_id),
        )
    return get_rental(conn, rental_id)


def cancel_rental(conn: sqlite3.Connection, rental_id: int) -> bool:
    with db.write_lock:
        cur = conn.execute(
            "UPDATE rentals SET status = 'cancelada' "
            "WHERE id = ? AND status = 'activa'",
            (rental_id,),
        )
        return cur.rowcount > 0


def delete_rental(conn: sqlite3.Connection, rental_id: int) -> sqlite3.Row | None:
    """Borra la renta por completo (para corregir una cargada por error).
    Irreversible. Devuelve la fila borrada (para el log) o None si no existía."""
    with db.write_lock:
        row = conn.execute("SELECT * FROM rentals WHERE id = ?", (rental_id,)).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM rentals WHERE id = ?", (rental_id,))
        return row


def update_eject_flag(conn: sqlite3.Connection, rental_id: int, eject: EjectResult) -> None:
    conn.execute(
        "UPDATE rentals SET eject_ok = ?, eject_msg = ? WHERE id = ?",
        (1 if eject.ok else 0, eject.msg[:300], rental_id),
    )


# ── View-model (cálculos en vivo para plantillas / JSON) ─────────
def enrich(row: sqlite3.Row) -> dict:
    """Añade duración y monto calculados en el servidor."""
    start_at = row["start_at"]
    activa = row["status"] == "activa"
    ref = timeutil.now_epoch() if activa else (row["end_at"] or start_at)
    dur_seg = max(0.0, ref - start_at)
    dur_min = dur_seg / 60.0

    if row["status"] == "cancelada":
        monto = 0.0
        horas = 0
    elif activa:
        horas, monto = pricing.calcular_monto(
            dur_min, row["tolerancia_min_snapshot"], row["tarifa_hora_snapshot"]
        )
    else:
        monto = row["amount_final"] if row["amount_final"] is not None else 0.0
        horas, _ = pricing.calcular_monto(
            dur_min, row["tolerancia_min_snapshot"], row["tarifa_hora_snapshot"]
        )

    return {
        "id": row["id"],
        "dni": row["dni"],
        "station_id": row["station_id"],
        "station_nombre": row["station_nombre"],
        "status": row["status"],
        "start_at": start_at,
        "start_at_str": timeutil.fmt_dt(start_at),
        "start_time_str": timeutil.fmt_time(start_at),
        "end_at": row["end_at"],
        "end_at_str": timeutil.fmt_dt(row["end_at"]) if row["end_at"] else "",
        "duracion_seg": int(dur_seg),
        "duracion_str": timeutil.fmt_duracion(dur_seg),
        "horas_cobradas": horas,
        "monto": round(monto, 2),
        "tarifa": row["tarifa_hora_snapshot"],
        "tolerancia": row["tolerancia_min_snapshot"],
        "created_by": row["created_by"],
        "eject_ok": bool(row["eject_ok"]),
        "eject_msg": row["eject_msg"],
    }
