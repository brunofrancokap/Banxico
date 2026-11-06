"""Decisão de política monetária: do parágrafo de decisão do PDF e do título da listagem."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..text.sentences import split_sentences
from .common import BP, RATE, classify_verb, parse_spanish_date, to_float


@dataclass
class Decision:
    instrument: str | None = None      # "tasa" (2008+) | "corto" (2000–2007)
    action: str | None = None          # hike | cut | hold
    change_bp: int | None = None       # tasa: Δ na taxa; corto: Δ nas condições monetárias, se informado
    rate: float | None = None          # nível da tasa objetivo após a decisão
    corto_mn: int | None = None        # nível do "corto" (milhões de pesos)
    effective_date: str | None = None


_TASA = re.compile(r"tasa de inter[eé]s interbancaria|tasa objetivo", re.I)
_CORTO = re.compile(r"[“\"]?corto[”\"]?", re.I)
_CORTO_LEVEL = re.compile(r"(\d{1,4})\s+millones\s+de\s+pesos", re.I)
_EFFECTIVE = re.compile(r"con efectos? a partir del?\s+(.{6,30}?\d{4})", re.I)


def _decision_sentence(text: str) -> str:
    """A frase com o verbo de decisão (no 2000–2007 ela vem no meio do parágrafo)."""
    for s in split_sentences(text):
        if re.search(r"(ha decidido|decidi[oó]|ha resuelto|considera prudente|determin[oó])", s, re.I):
            return s
    return text


def parse_decision(paragraph: str) -> Decision:
    d = Decision()
    sent = _decision_sentence(paragraph)
    tail = sent[re.search(r"(decidi|resuel|prudente|determin)", sent, re.I).start():] if re.search(
        r"(decidi|resuel|prudente|determin)", sent, re.I) else sent

    if _TASA.search(sent):
        d.instrument = "tasa"
        d.action = classify_verb(tail)
        bp = re.search(BP, sent)
        d.change_bp = int(bp.group(1)) if bp else None
        rate = re.search(RATE, sent)
        d.rate = to_float(rate.group(1)) if rate else None
        if d.action == "hold":
            d.change_bp = 0
    elif _CORTO.search(paragraph) or re.search(r"condiciones monetarias", sent, re.I):
        d.instrument = "corto"
        d.action = classify_verb(tail)
        bp = re.search(BP, sent)
        d.change_bp = int(bp.group(1)) if bp else (0 if d.action == "hold" else None)
        levels = _CORTO_LEVEL.findall(paragraph)
        d.corto_mn = int(levels[-1]) if levels else None
        if re.search(r"(el|al)\s+[“\"]?corto[”\"]?\s*(se mantiene|,\s*manteni)", paragraph, re.I) and \
                not re.search(r"condiciones monetarias", sent, re.I):
            d.action = d.action or "hold"

    eff = _EFFECTIVE.search(paragraph)
    if eff:
        d.effective_date = parse_spanish_date(eff.group(1))
    return d


# --- título da listagem (fonte independente para validação) ---------------------
def parse_title(title: str) -> Decision:
    d = Decision()
    t = title.replace("“", '"').replace("”", '"')
    if "tasa objetivo" in t.lower() or _TASA.search(t):
        d.instrument = "tasa"
        if re.search(r"se mantiene sin cambio", t, re.I):
            d.action, d.change_bp = "hold", 0
        elif re.search(r"(se incrementa|aumenta)", t, re.I):
            d.action = "hike"
        elif re.search(r"(disminuye|se reduce)", t, re.I):
            d.action = "cut"
        bp = re.search(BP, t)
        if bp:
            d.change_bp = int(bp.group(1))
        rate = re.search(RATE, t)
        d.rate = to_float(rate.group(1)) if rate else None
    elif "corto" in t.lower():
        d.instrument = "corto"
        if re.search(r"se aumenta", t, re.I):
            d.action = "hike"
        elif re.search(r"se reduce", t, re.I):
            d.action = "cut"
        if re.search(r"restringen", t, re.I):
            d.action = "hike"
        elif re.search(r"relajamiento", t, re.I):
            d.action = "cut"
        elif d.action is None and re.search(r"sin cambio", t, re.I):
            d.action = "hold"
        bp = re.search(BP, t)
        d.change_bp = int(bp.group(1)) if bp else (0 if d.action == "hold" else None)
        lvl = _CORTO_LEVEL.search(t)
        d.corto_mn = int(lvl.group(1)) if lvl else None
    return d
