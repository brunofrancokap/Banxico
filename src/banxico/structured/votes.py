"""Votação da Junta de Gobierno.

- 2021-08+: parágrafo nominal "Votaron a favor de la decisión A, B y C. Votó a favor de <alternativa> D."
- ~2017–2021: só "por unanimidad" / "por mayoría" no texto (sem nomes).
- Antes: em geral não informado (exceto menções pontuais, ex. reunião extraordinária 2016).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..text.sentences import split_sentences
from .common import BP, RATE, classify_verb, to_float


@dataclass
class Dissent:
    name: str
    action: str | None          # hike | cut | hold (o que o dissidente preferia)
    change_bp: int | None
    rate: float | None


@dataclass
class Votes:
    vote_type: str | None = None             # unanimous | majority | None (não informado)
    votes_for: list[str] = field(default_factory=list)
    dissents: list[Dissent] = field(default_factory=list)
    source: str | None = None                # named | text

    @property
    def n_for(self) -> int | None:
        return len(self.votes_for) or None

    @property
    def n_against(self) -> int | None:
        return len(self.dissents) if self.votes_for else None


def _split_names(chunk: str) -> list[str]:
    chunk = chunk.strip().rstrip(".").strip()
    parts = re.split(r",\s*(?:y\s+)?|\s+y\s+", chunk)
    return [p.strip() for p in parts if p.strip()]


_FOR = re.compile(r"^vot(?:aron|ó) a favor de la decisi[oó]n\s+(.+)$", re.I)
_ALT = re.compile(r"^vot(?:aron|ó) a favor de\s+(.+)$", re.I)
_NAME_START = re.compile(r"(?:%|por ciento)\s+(?=[A-ZÁÉÍÓÚÑ])")


def _parse_named(paragraph: str) -> Votes | None:
    v = Votes(source="named")
    for sent in split_sentences(paragraph):
        if m := _FOR.match(sent):
            v.votes_for = _split_names(m.group(1))
        elif m := _ALT.match(sent):
            body = m.group(1)
            cut = list(_NAME_START.finditer(body))
            if not cut:
                continue
            proposal, names = body[: cut[-1].end()], body[cut[-1].end():]
            bp = re.search(BP, proposal)
            rate = re.search(RATE, proposal)
            action = classify_verb(proposal)
            for name in _split_names(names):
                v.dissents.append(Dissent(name=name, action=action,
                                          change_bp=int(bp.group(1)) if bp else (0 if action == "hold" else None),
                                          rate=to_float(rate.group(1)) if rate else None))
    if not v.votes_for:
        return None
    v.vote_type = "majority" if v.dissents else "unanimous"
    return v


def parse_votes(paragraphs: list[tuple[str, str]]) -> Votes:
    """paragraphs: lista de (section, text) em ordem."""
    for section, text in paragraphs:
        if section == "vote" or text.lower().startswith(("votaron a favor", "votó a favor")):
            named = _parse_named(text)
            if named:
                return named
    for _, text in paragraphs:
        for sent in split_sentences(text):
            if not re.search(r"(decidi|determin|resolvi|tomada)", sent, re.I):
                continue
            if re.search(r"por unanimidad|voto favorable de todos", sent, re.I):
                return Votes(vote_type="unanimous", source="text")
            if re.search(r"por mayor[ií]a|la mayor[ií]a de la junta", sent, re.I):
                return Votes(vote_type="majority", source="text")
    return Votes()
