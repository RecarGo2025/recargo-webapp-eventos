"""Cliente aislado de la API de Bajie Charging.

Único módulo que conoce la API externa: si Bajie cambia, solo se toca esto.

Regla de negocio (RecarGo x Vibra): NUNCA bloqueamos la operación por Bajie.
Si la API no responde o falla, la renta se crea igual y el operador saca la
batería a mano. Este módulo solo *reporta* qué pasó; nunca detiene el flujo.

Estrategia de expulsión: consultar los slots del gabinete y expulsar el de
MAYOR carga (`vol`), para dispensar siempre la batería más cargada.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

import httpx

from . import config

log = logging.getLogger("bajie")

_TIMEOUT = httpx.Timeout(5.0, connect=5.0)
_SUCCESS_MSG = "Successful operation"


@dataclass
class Battery:
    slot_num: int
    level: float
    battery_id: str


@dataclass
class EjectResult:
    ok: bool
    msg: str
    slot_num: int | None = None
    battery_level: float | None = None


def _headers() -> dict[str, str]:
    return {"Authorization": f"Basic {config.BAJIE_BASIC_AUTH_KEY}"}


def _get(path: str, params: dict) -> dict:
    url = f"{config.BAJIE_BASE_URL}/{path}"
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(url, params=params, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _post(path: str, params: dict) -> dict:
    url = f"{config.BAJIE_BASE_URL}/{path}"
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(url, params=params, headers=_headers())
        resp.raise_for_status()
        return resp.json()


def _with_retry(fn, *args):
    """Un reintento automático ante fallo de red/HTTP."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 — reintento genérico a propósito
        log.warning("Bajie: primer intento falló (%s), reintentando…", exc)
        return fn(*args)


# ── API pública del módulo ───────────────────────────────────────
def query_batteries(device_id: str) -> list[Battery]:
    """Slots con batería del gabinete, ordenados por carga desc."""
    if config.BAJIE_MOCK:
        return _mock_batteries(device_id)

    data = _with_retry(_get, "rent/cabinet/query", {"deviceId": device_id})
    batteries: list[Battery] = []
    if isinstance(data, dict) and "data" in data and data["data"]:
        for b in data["data"].get("batteries", []) or []:
            batteries.append(
                Battery(
                    slot_num=int(b.get("slotNum")),
                    level=float(b.get("vol", 0)),
                    battery_id=str(b.get("batteryId", "")),
                )
            )
    batteries.sort(key=lambda x: x.level, reverse=True)
    return batteries


def eject_slot(device_id: str, slot_num: int | str) -> EjectResult:
    """Expulsa un slot concreto."""
    if config.BAJIE_MOCK:
        log.info("Bajie[MOCK]: eject %s slot %s -> OK", device_id, slot_num)
        return EjectResult(ok=True, msg="OK (mock)", slot_num=int(slot_num))

    try:
        res = _with_retry(
            _post,
            "cabinet/ejectByRepair",
            {"cabinetid": device_id, "slotNum": slot_num},
        )
        msg = str(res.get("msg", ""))
        ok = msg == _SUCCESS_MSG
        log.info("Bajie: eject %s slot %s -> %s (%s)", device_id, slot_num, ok, msg)
        return EjectResult(ok=ok, msg=msg or ("OK" if ok else "Respuesta inesperada"),
                           slot_num=int(slot_num))
    except Exception as exc:  # noqa: BLE001
        log.error("Bajie: eject %s slot %s falló: %s", device_id, slot_num, exc)
        return EjectResult(ok=False, msg=f"Bajie no respondió: {exc}")


def eject_highest_charge(device_id: str) -> EjectResult:
    """Expulsa la batería con mayor carga del gabinete.

    Nunca lanza excepción: ante cualquier fallo devuelve ok=False con el motivo,
    y el flujo de negocio continúa (expulsión manual).
    """
    if not device_id:
        return EjectResult(ok=False, msg="La estación no tiene device_id configurado")

    try:
        batteries = query_batteries(device_id)
    except Exception as exc:  # noqa: BLE001
        log.error("Bajie: no se pudo consultar %s: %s", device_id, exc)
        return EjectResult(ok=False, msg=f"No se pudo consultar el gabinete: {exc}")

    if not batteries:
        return EjectResult(ok=False, msg="No hay baterías reportadas en el gabinete")

    target = batteries[0]  # mayor carga
    result = eject_slot(device_id, target.slot_num)
    result.battery_level = target.level
    if result.slot_num is None:
        result.slot_num = target.slot_num
    return result


# ── Mock local para desarrollar sin hardware ─────────────────────
_MOCK_STATE: dict[str, list[Battery]] = {}


def _mock_batteries(device_id: str) -> list[Battery]:
    if device_id not in _MOCK_STATE:
        _MOCK_STATE[device_id] = [
            Battery(slot_num=1, level=88.0, battery_id="MB-001"),
            Battery(slot_num=2, level=95.0, battery_id="MB-002"),
            Battery(slot_num=3, level=72.0, battery_id="MB-003"),
            Battery(slot_num=4, level=60.0, battery_id="MB-004"),
        ]
    return sorted(_MOCK_STATE[device_id], key=lambda x: x.level, reverse=True)
