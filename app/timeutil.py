"""Utilidades de tiempo. Todo se calcula/formatea en hora de servidor (America/Lima)."""
from __future__ import annotations

import time
from datetime import datetime

from . import config


def now_epoch() -> float:
    return time.time()


def fmt_dt(epoch: float | None) -> str:
    """Epoch -> 'dd/mm/YYYY HH:MM' en zona horaria configurada."""
    if epoch is None:
        return ""
    return datetime.fromtimestamp(epoch, config.TZ).strftime("%d/%m/%Y %H:%M")


def fmt_time(epoch: float | None) -> str:
    """Epoch -> 'HH:MM:SS' en zona horaria configurada."""
    if epoch is None:
        return ""
    return datetime.fromtimestamp(epoch, config.TZ).strftime("%H:%M:%S")


def fmt_duracion(segundos: float) -> str:
    """Segundos -> 'HH:MM:SS'."""
    segundos = max(0, int(segundos))
    h, rem = divmod(segundos, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
