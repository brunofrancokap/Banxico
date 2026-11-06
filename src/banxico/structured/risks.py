"""Balanço de riscos (doméstico) para inflação e crescimento.

Para cada alvo extrai:
    bias    up | down | balanced | uncertain       (nível: "sesgado al alza", "equilibrado", "incierto")
    change  improved | deteriorated | unchanged    (vs. decisão anterior: "ha mejorado", "se deterioró")
    evidence  a frase de origem (para auditoria)
Frases sobre o balanço global/mundial são ignoradas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..text.sentences import split_sentences


@dataclass
class RiskBalance:
    bias: str | None = None
    change: str | None = None
    evidence: str | None = None


_ANCHOR = re.compile(r"balance de (?:los )?riesgos", re.I)
_GLOBAL = re.compile(r"mundial|global|internacional|economías avanzadas|estadounidense", re.I)
_INFL = re.compile(r"inflaci", re.I)
_GROWTH = re.compile(r"crecimiento|actividad econ|\bPIB\b|holgura", re.I)


def _target(sentence: str) -> str | None:
    """Alvo = palavra-chave mais próxima APÓS 'balance de riesgos'; senão, a mais próxima antes."""
    m = _ANCHOR.search(sentence)
    after = sentence[m.end(): m.end() + 110]
    if _GLOBAL.search(after[:60]):
        return None
    hits = [(x.start(), "inflation") for x in [_INFL.search(after)] if x] + \
           [(x.start(), "growth") for x in [_GROWTH.search(after)] if x]
    if hits:
        return min(hits)[1]
    before = sentence[max(0, m.start() - 150): m.start()]
    if _GLOBAL.search(before):
        return None
    if _GROWTH.search(before):
        return "growth"
    if _INFL.search(before):
        return "inflation"
    return None


def _bias(s: str) -> str | None:
    if m := re.search(r"sesg\w*\s+(?:\w+\s+){0,2}?(al alza|a la baja)", s, re.I):
        return "up" if m.group(1).lower() == "al alza" else "down"
    # "El balance de riesgos ... es al alza" / "se mantiene al alza"
    if m := re.search(r"\b(?:es|se mantiene|permanece|contin[uú]a|sigue)\s+(?:\w+\s+)?(al alza|a la baja)", s, re.I):
        return "up" if m.group(1).lower() == "al alza" else "down"
    if re.search(r"\b(neutral|equilibrad[oa]|balancead[oa])\b", s, re.I):
        return "balanced"
    if re.search(r"incierto|incertidumbre", s, re.I):
        return "uncertain"
    return None


def _change(s: str) -> str | None:
    if re.search(r"mejor(ado|ó|a)\b", s, re.I):
        return "improved"
    if re.search(r"deterior", s, re.I):
        return "deteriorated"
    if re.search(r"sin cambios?|permanece sin|se mantiene sin", s, re.I):
        return "unchanged"
    return None


def parse_risks(texts: list[str]) -> dict[str, RiskBalance]:
    out = {"inflation": RiskBalance(), "growth": RiskBalance()}
    for text in texts:
        for sent in split_sentences(text):
            if not _ANCHOR.search(sent):
                continue
            target = _target(sent)
            if not target or out[target].evidence:
                continue
            bias, change = _bias(sent), _change(sent)
            if bias or change:
                out[target] = RiskBalance(bias=bias, change=change, evidence=sent.strip())
    return out
