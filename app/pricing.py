"""Regla de precio: cobro por hora con tolerancia. Fuente de verdad = servidor."""
from __future__ import annotations

import math


def horas_cobradas(duracion_min: float, tolerancia_min: float) -> int:
    """horas = ceil((duración − tolerancia) / 60), mínimo 1.

    Ejemplos con tolerancia 4:
      0h50m (50) -> 1     1h04m (64) -> 1     1h05m (65) -> 2
    """
    horas = math.ceil((duracion_min - tolerancia_min) / 60)
    return max(1, horas)


def calcular_monto(
    duracion_min: float,
    tolerancia_min: float,
    tarifa_hora: float,
    tope_max: float = 0.0,
) -> tuple[int, float]:
    """Devuelve (horas_cobradas, monto).

    `tope_max` es el techo de cobro en soles: si > 0, el monto nunca supera ese
    valor aunque se acumulen más horas. `tope_max <= 0` = sin tope (desactivado).
    Las horas cobradas se devuelven sin recortar (siguen reflejando el tiempo real).
    """
    horas = horas_cobradas(duracion_min, tolerancia_min)
    monto = horas * tarifa_hora
    if tope_max and tope_max > 0:
        monto = min(monto, tope_max)
    return horas, round(monto, 2)
