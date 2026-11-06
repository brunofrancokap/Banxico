"""Divisão de parágrafos em frases (espanhol), base para o alinhamento do diff."""

from __future__ import annotations

import re

# Abreviações que terminam em ponto e NÃO encerram frase.
_ABBREV = {
    "sr", "sra", "dr", "dra", "no", "núm", "num", "art", "arts", "fracc", "etc", "vs", "aprox",
    "ee", "uu", "ee.uu", "p.b", "pp", "pág", "cfr", "ej", "i.e", "e.g", "s.a", "c.v", "l.p", "gas l.p",
}
_CANDIDATE = re.compile(r"[.;!?](?:[\"”»)]?)\s+(?=[\"“«(]?[A-ZÁÉÍÓÚÑ¿¡\d])")


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    start = 0
    for m in _CANDIDATE.finditer(text):
        end = m.start() + 1
        word = re.search(r"([\w.]+)\.$", text[start:end])
        if word and word.group(1).lower() in _ABBREV:
            continue
        # "6.25%" e similares não casam (exigem espaço após o ponto); siglas tipo "L.P." caem no _ABBREV
        out.append(text[start:m.end()].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def first_sentence(text: str, max_len: int = 300) -> str:
    sents = split_sentences(text[: max_len * 2])
    return sents[0][:max_len] if sents else ""
