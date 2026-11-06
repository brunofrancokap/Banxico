"""Quadro de pronósticos de inflação (comunicados ~2021+) em formato longo.

Estrutura do quadro (texto já linha a linha):
    2025 2026 2027 2028                     <- anos
    IV I II III IV I II III IV I II III     <- trimestres (pode faltar)
    INPC | Subyacente                       <- série atual
    Actual (05/11/2026) 1/ 3.7 4.1 ...      <- vintage atual
    Anterior (24/09/2026) 2/ 3.7 4.1 ...    <- vintage anterior (horizonte pode ser menor: valores alinhados à esquerda)
    Memorándum ... anualizada ...
    Actual - INPC 1/ ...                    <- variação trimestral dessazonalizada anualizada
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .common import parse_spanish_date

_YEARS = re.compile(r"^(?:(?:19|20)\d{2}\s*)+$")
_QUARTERS = re.compile(r"^(?:(?:IV|III|II|I)\s*)+$")
_VALUES = re.compile(r"-?\d+\.\d+")
_ROW = re.compile(r"^(Actual|Anterior)\s*(?:-\s*(INPC|Subyacente))?\s*(?:\(([^)]*)\))?\s*\d?/?\s*(.*)$", re.I)
_Q = {"I": 1, "II": 2, "III": 3, "IV": 4}

SERIES = {
    ("INPC", False): "headline_yoy",
    ("SUBYACENTE", False): "core_yoy",
    ("INPC", True): "headline_qoq_saar",
    ("SUBYACENTE", True): "core_qoq_saar",
}


@dataclass
class ForecastPoint:
    vintage: str            # actual | anterior
    vintage_date: str | None
    series: str             # headline_yoy | core_yoy | headline_qoq_saar | core_qoq_saar
    period: str             # "2026Q4"
    value: float


def _periods(years: list[int], quarters: list[str] | None) -> list[str]:
    if not years:
        return []
    if not quarters:
        quarters = ["I", "II", "III", "IV"] * len(years)
    out, y = [], years[0]
    for i, q in enumerate(quarters):
        if i > 0 and _Q[q] <= _Q[quarters[i - 1]]:
            y += 1
        out.append(f"{y}Q{_Q[q]}")
    return out


def _vintage_date(raw: str | None) -> str | None:
    if not raw:
        return None
    if m := re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", raw):
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return parse_spanish_date(raw)


def parse_forecast_table(text: str) -> tuple[list[ForecastPoint], list[str]]:
    """Retorna (pontos, avisos)."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    years: list[int] = []
    quarters: list[str] | None = None
    series: str | None = None
    memo = False
    points: list[ForecastPoint] = []
    warnings: list[str] = []

    for line in lines:
        if _YEARS.match(line) and not years:
            years = [int(y) for y in line.split()]
        elif _QUARTERS.match(line) and quarters is None:
            quarters = line.split()
        elif line.upper() == "INPC":
            series = "INPC"
        elif line.lower().startswith("subyacente"):
            series = "SUBYACENTE"
        elif line.lower().startswith(("memorándum", "memorandum")) or "anualizada" in line.lower():
            memo = True
        elif m := _ROW.match(line):
            vintage = m.group(1).lower()
            row_series = (m.group(2) or series or "").upper()
            values = [float(v) for v in _VALUES.findall(m.group(4))]
            key = (row_series, memo or bool(m.group(2)))
            if key not in SERIES or not values:
                warnings.append(f"linha não reconhecida: {line[:60]}")
                continue
            periods = _periods(years, quarters)
            if len(values) > len(periods):
                warnings.append(f"{SERIES[key]}/{vintage}: {len(values)} valores > {len(periods)} trimestres")
                continue
            vdate = _vintage_date(m.group(3))
            for period, value in zip(periods, values):  # alinhado à esquerda
                points.append(ForecastPoint(vintage, vdate, SERIES[key], period, value))
    if points and not years:
        warnings.append("quadro sem linha de anos")
    if points and quarters is None:
        warnings.append("quadro sem linha de trimestres (assumido início em I)")
    return points, warnings
