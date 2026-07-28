"""Rutas admin (operadores): login, panel, crear/finalizar/cancelar, config, export."""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from .. import auth, bajie, db, rentals, timeutil
from ..templating import flash, pop_flashes, templates

router = APIRouter(prefix="/admin")


def _need_login_json() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "no_auth"}, status_code=401)


def _stations(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM stations ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def _station(conn, station_id: int | None) -> dict | None:
    if station_id is None:
        return None
    row = conn.execute("SELECT * FROM stations WHERE id = ?", (station_id,)).fetchone()
    return dict(row) if row else None


# ── Auth ─────────────────────────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if auth.is_logged_in(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": None})


@router.post("/login")
def login_submit(request: Request, usuario: str = Form(""), password: str = Form("")):
    if auth.authenticate(usuario.strip(), password):
        auth.login(request, usuario.strip())
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        "admin_login.html",
        {"request": request, "error": "Usuario o contraseña incorrectos."},
        status_code=401,
    )


@router.post("/logout")
def logout(request: Request):
    auth.logout(request)
    return RedirectResponse("/admin/login", status_code=303)


# ── Panel ────────────────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def panel(request: Request, status: Optional[str] = None, dni: Optional[str] = None):
    if not auth.is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    conn = db.connect()
    try:
        stations = _stations(conn)
        sel_id = auth.selected_station_id(request)
        if sel_id is None and stations:
            sel_id = stations[0]["id"]
            auth.set_station(request, sel_id)
        sel = _station(conn, sel_id)
        rows = rentals.list_rentals(conn, status=status or None, dni=(dni or "").strip() or None)
        enriched = [rentals.enrich(r) for r in rows]
        cfg = {
            "tarifa_por_hora": db.get_config(conn, "tarifa_por_hora", "10.00"),
            "tolerancia_min": db.get_config(conn, "tolerancia_min", "4"),
            "tope_max": db.get_config(conn, "tope_max", "0.00"),
        }
    finally:
        conn.close()
    return templates.TemplateResponse(
        "admin_panel.html",
        {
            "request": request,
            "user": auth.current_user(request),
            "stations": stations,
            "selected": sel,
            "rentals": enriched,
            "cfg": cfg,
            "filtro_status": status or "",
            "filtro_dni": dni or "",
            "server_now": timeutil.now_epoch(),
            "flashes": pop_flashes(request),
        },
    )


@router.post("/station")
def set_station(request: Request, station_id: int = Form(...)):
    if not auth.is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    auth.set_station(request, station_id)
    return RedirectResponse("/admin", status_code=303)


@router.post("/station/edit")
def edit_station(
    request: Request,
    station_id: int = Form(...),
    nombre: str = Form(...),
    device_id: str = Form(""),
):
    if not auth.is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE stations SET nombre = ?, device_id = ? WHERE id = ?",
            (nombre.strip(), device_id.strip(), station_id),
        )
    finally:
        conn.close()
    flash(request, f"Estación actualizada.", "ok")
    return RedirectResponse("/admin", status_code=303)


@router.post("/config")
def save_config(
    request: Request,
    tarifa_por_hora: str = Form(...),
    tolerancia_min: str = Form(...),
    tope_max: str = Form("0"),
):
    if not auth.is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    try:
        tarifa = round(float(tarifa_por_hora.replace(",", ".")), 2)
        tol = int(float(tolerancia_min))
        # Tope de cobro: vacío o 0 = desactivado (sin límite).
        raw_tope = (tope_max or "").strip().replace(",", ".")
        tope = round(float(raw_tope), 2) if raw_tope else 0.0
        if tarifa < 0 or tol < 0 or tope < 0:
            raise ValueError
    except ValueError:
        flash(request, "Tarifa, tolerancia o tope inválidos.", "error")
        return RedirectResponse("/admin", status_code=303)
    conn = db.connect()
    try:
        db.set_config(conn, "tarifa_por_hora", f"{tarifa:.2f}")
        db.set_config(conn, "tolerancia_min", str(tol))
        db.set_config(conn, "tope_max", f"{tope:.2f}")
    finally:
        conn.close()
    flash(request, "Configuración guardada.", "ok")
    return RedirectResponse("/admin", status_code=303)


# ── Acciones de rentas (JSON, consumidas por JS) ─────────────────
@router.post("/rentals")
def create_rental(request: Request, dni: str = Form("")):
    if not auth.is_logged_in(request):
        return _need_login_json()
    dni = rentals.normalize_dni(dni)
    if not dni:
        return JSONResponse({"ok": False, "error": "dni_vacio"}, status_code=400)

    conn = db.connect()
    try:
        sel_id = auth.selected_station_id(request)
        station = _station(conn, sel_id)
        if not station:
            return JSONResponse(
                {"ok": False, "error": "sin_estacion", "mensaje": "Selecciona una estación."},
                status_code=400,
            )

        # Expulsión de la batería con mayor carga. NUNCA bloquea (regla RecarGo).
        eject = bajie.eject_highest_charge(station["device_id"])

        try:
            rental_id = rentals.create_rental(
                conn, dni, station["id"], auth.current_user(request), eject
            )
        except rentals.RentaActivaExiste as e:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "renta_activa",
                    "rental_id": e.rental_id,
                    "mensaje": f"El documento {dni} ya tiene una renta activa.",
                },
                status_code=409,
            )
    finally:
        conn.close()

    return JSONResponse(
        {
            "ok": True,
            "rental_id": rental_id,
            "dni": dni,
            "eject_ok": eject.ok,
            "eject_msg": eject.msg,
            "slot_num": eject.slot_num,
            "battery_level": eject.battery_level,
            "mensaje": (
                f"Renta creada. Batería expulsada (slot {eject.slot_num}, {eject.battery_level}%)."
                if eject.ok
                else f"Renta creada. ⚠ Expulsión MANUAL: {eject.msg}"
            ),
        }
    )


@router.get("/lookup")
def lookup(request: Request, dni: str = ""):
    if not auth.is_logged_in(request):
        return _need_login_json()
    dni = rentals.normalize_dni(dni)
    conn = db.connect()
    try:
        row = rentals.active_for_dni(conn, dni)
        if not row:
            return JSONResponse({"found": False})
        return JSONResponse({"found": True, "rental": rentals.enrich(row)})
    finally:
        conn.close()


@router.post("/finalize")
def finalize(request: Request, dni: str = Form(""), rental_id: int = Form(0)):
    if not auth.is_logged_in(request):
        return _need_login_json()
    conn = db.connect()
    try:
        if not rental_id:
            row = rentals.active_for_dni(conn, rentals.normalize_dni(dni))
            if not row:
                return JSONResponse(
                    {"ok": False, "error": "no_activa", "mensaje": "No hay renta activa para ese documento."},
                    status_code=404,
                )
            rental_id = row["id"]
        result = rentals.finalize_rental(conn, rental_id)
        if not result:
            return JSONResponse(
                {"ok": False, "error": "no_activa", "mensaje": "La renta ya no está activa."},
                status_code=409,
            )
        return JSONResponse({"ok": True, "rental": rentals.enrich(result)})
    finally:
        conn.close()


@router.post("/rentals/{rental_id}/cancel")
def cancel(request: Request, rental_id: int):
    if not auth.is_logged_in(request):
        return _need_login_json()
    conn = db.connect()
    try:
        ok = rentals.cancel_rental(conn, rental_id)
    finally:
        conn.close()
    if not ok:
        return JSONResponse({"ok": False, "mensaje": "No se pudo cancelar (¿ya no está activa?)."}, status_code=409)
    return JSONResponse({"ok": True})


@router.post("/rentals/{rental_id}/delete")
def delete_rental_route(request: Request, rental_id: int):
    """Elimina una renta cargada por error. Destructivo e irreversible."""
    if not auth.is_logged_in(request):
        return _need_login_json()
    conn = db.connect()
    try:
        row = rentals.delete_rental(conn, rental_id)
    finally:
        conn.close()
    if not row:
        return JSONResponse({"ok": False, "mensaje": "La renta ya no existe."}, status_code=404)
    return JSONResponse({"ok": True, "dni": row["dni"]})


@router.post("/eject")
def quick_eject(request: Request):
    """Expulsión rápida de mantenimiento (sin crear renta)."""
    if not auth.is_logged_in(request):
        return _need_login_json()
    conn = db.connect()
    try:
        station = _station(conn, auth.selected_station_id(request))
    finally:
        conn.close()
    if not station:
        return JSONResponse({"ok": False, "mensaje": "Selecciona una estación."}, status_code=400)
    res = bajie.eject_highest_charge(station["device_id"])
    return JSONResponse(
        {
            "ok": res.ok,
            "slot_num": res.slot_num,
            "battery_level": res.battery_level,
            "mensaje": (
                f"Batería expulsada (slot {res.slot_num}, {res.battery_level}%)."
                if res.ok
                else f"No se pudo expulsar por Bajie: {res.msg}. Hazlo manualmente."
            ),
        }
    )


# ── Export CSV ───────────────────────────────────────────────────
@router.get("/export.csv")
def export_csv(request: Request):
    if not auth.is_logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    conn = db.connect()
    try:
        rows = rentals.list_rentals(conn)
        enriched = [rentals.enrich(r) for r in rows]
    finally:
        conn.close()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["id", "documento", "estacion", "estado", "inicio", "fin", "duracion",
         "horas_cobradas", "tarifa_hora", "tolerancia_min", "tope_max", "tope_alcanzado",
         "monto", "creado_por", "expulsion_ok", "expulsion_detalle"]
    )
    for r in enriched:
        w.writerow(
            [r["id"], r["dni"], r["station_nombre"], r["status"], r["start_at_str"],
             r["end_at_str"], r["duracion_str"], r["horas_cobradas"], f'{r["tarifa"]:.2f}',
             r["tolerancia"],
             f'{r["tope_max"]:.2f}' if r["tope_max"] else "",
             "SI" if r["tope_alcanzado"] else "",
             f'{r["monto"]:.2f}', r["created_by"],
             "SI" if r["eject_ok"] else "NO", r["eject_msg"]]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="rentas_vibra.csv"'},
    )
