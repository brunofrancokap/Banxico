"""Utilitários compartilhados pela extração estruturada."""

from __future__ import annotations

import re
from datetime import date

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# Verbos -> ação. "hike" = aperto (inclui aumento do corto/restrição de condições monetárias).
ACTION_VERBS = [
    ("hold", r"mant(?:ener|iene|ienen|uvo)|no modificar|sin cambio"),
    ("hike", r"increment\w*|aument\w*|elev\w*|ampli\w*|restring\w*"),
    ("cut", r"reduc\w*|disminu\w*|recort\w*|relaj\w*|baj\w*"),
]

RATE = r"(\d{1,2}(?:\.\d{1,2})?)\s*(?:%|por\s+ciento)"
BP = r"(\d{1,3})\s+puntos\s+base"
SPANISH_DATE = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de|del)\s+(\d{4})", re.I)


def classify_verb(text: str) -> str | None:
    """Primeira ação mencionada (posição no texto), não a primeira da lista."""
    best: tuple[int, str] | None = None
    for action, rx in ACTION_VERBS:
        m = re.search(rf"\b(?:{rx})", text, re.I)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), action)
    return best[1] if best else None


def parse_spanish_date(text: str) -> str | None:
    m = SPANISH_DATE.search(text)
    if not m or m.group(2).lower() not in MESES:
        return None
    return date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1))).isoformat()


def to_float(s: str | None) -> float | None:
    return float(s) if s is not None else None
