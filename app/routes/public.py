"""Rutas públicas (usuario): buscar alquiler y ver contador en vivo."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import db, rentals, timeutil
from ..templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        "public_search.html", {"request": request, "error": error}
    )


@router.post("/buscar")
def buscar(request: Request, dni: str = Form("")):
    dni = rentals.normalize_dni(dni)
    if not dni:
        return templates.TemplateResponse(
            "public_search.html",
            {"request": request, "error": "Ingresa tu documento."},
            status_code=400,
        )
    conn = db.connect()
    try:
        row = rentals.find_for_public(conn, dni)
    finally:
        conn.close()
    if not row:
        return templates.TemplateResponse(
            "public_search.html",
            {
                "request": request,
                "error": f"No encontramos un alquiler con el documento {dni}.",
                "dni": dni,
            },
            status_code=404,
        )
    return RedirectResponse(url=f"/r/{row['id']}", status_code=303)


@router.get("/r/{rental_id}", response_class=HTMLResponse)
def rental_page(request: Request, rental_id: int):
    conn = db.connect()
    try:
        row = rentals.get_rental(conn, rental_id)
    finally:
        conn.close()
    if not row:
        return templates.TemplateResponse(
            "public_search.html",
            {"request": request, "error": "Ese alquiler no existe."},
            status_code=404,
        )
    r = rentals.enrich(row)
    return templates.TemplateResponse(
        "public_rental.html",
        {"request": request, "r": r, "server_now": timeutil.now_epoch()},
    )


@router.get("/api/r/{rental_id}")
def rental_api(rental_id: int):
    """Estado para polling. El cliente anima el contador; el servidor es la verdad."""
    conn = db.connect()
    try:
        row = rentals.get_rental(conn, rental_id)
    finally:
        conn.close()
    if not row:
        return JSONResponse({"error": "not_found"}, status_code=404)
    r = rentals.enrich(row)
    return JSONResponse(
        {
            "id": r["id"],
            "status": r["status"],
            "start_at": r["start_at"],
            "end_at": r["end_at"],
            "server_now": timeutil.now_epoch(),
            "tarifa": r["tarifa"],
            "tolerancia": r["tolerancia"],
            "monto": r["monto"],
            "duracion_seg": r["duracion_seg"],
            "duracion_str": r["duracion_str"],
            "horas_cobradas": r["horas_cobradas"],
            "end_at_str": r["end_at_str"],
        }
    )
