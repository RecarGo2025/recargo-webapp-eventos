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
    duracion_min: float, tolerancia_min: float, tarifa_hora: float
) -> tuple[int, float]:
    """Devuelve (horas_cobradas, monto)."""
    horas = horas_cobradas(duracion_min, tolerancia_min)
    return horas, round(horas * tarifa_hora, 2)
