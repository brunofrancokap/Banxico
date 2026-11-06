"""Extração estruturada dos comunicados de PM: decisão, votos, balanço de riscos, pronósticos.

Entrada: segmentos já extraídos (tabela `segments`) + título da listagem.
Saída:   um registro por reunião (tabela `decisions`) + pontos de pronóstico (`forecasts`).
Cada mudança de regra deve incrementar STRUCT_VERSION.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .decision import Decision, parse_decision, parse_title
from .forecasts import ForecastPoint, parse_forecast_table
from .risks import RiskBalance, parse_risks
from .votes import Votes, parse_votes

STRUCT_VERSION = "struct-v2"  # v2: guidance também de frases no meio de parágrafos

# Só quando o comunicado diz que ESTA decisão foi tomada em reunião extraordinária
# (menções a reuniões extraordinárias passadas ou "medidas extraordinarias" não contam).
# Limitação: reuniões fora do calendário que não usam a expressão (ex.: 2020-03-20) ficam False.
_EXTRAORDINARY = re.compile(
    r"(esta decisi[oó]n|fue tomada|se tom[oó]|en el d[ií]a de hoy)[^.]{0,80}reuni[oó]n extraordinaria", re.I)


@dataclass
class MeetingRecord:
    document_id: str
    doc_date: str
    decision: Decision
    title: Decision
    votes: Votes
    risks: dict[str, RiskBalance]
    guidance: str | None
    extraordinary: bool
    forecasts: list[ForecastPoint] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)


def parse_meeting(doc: Mapping, segments: Sequence[Mapping]) -> MeetingRecord:
    paragraphs = [(s["section"], s["text"]) for s in segments if s["kind"] == "paragraph"]
    decision_text = next((t for sec, t in paragraphs if sec == "decision"), "")
    all_text = " ".join(t for _, t in paragraphs)

    rec = MeetingRecord(
        document_id=doc["id"],
        doc_date=doc["doc_date"],
        decision=parse_decision(decision_text),
        title=parse_title(doc["title"] or ""),
        votes=parse_votes(paragraphs),
        risks=parse_risks([t for _, t in paragraphs]),
        guidance=_guidance_text(paragraphs, doc["doc_date"]),
        extraordinary=bool(_EXTRAORDINARY.search(all_text)),
    )

    for s in segments:
        if s["kind"] == "table" and ("Actual" in s["text"] and "Anterior" in s["text"]):
            points, warns = parse_forecast_table(s["text"])
            rec.forecasts.extend(points)
            rec.checks.extend(f"pronósticos: {w}" for w in warns)

    rec.checks.extend(_document_checks(rec))
    return rec


def _guidance_text(paragraphs: list[tuple[str, str]], doc_date: str) -> str | None:
    """Parágrafos rotulados guidance; se não houver (comum em 2016–2019), o trecho de cada
    parágrafo que começa na primeira frase classificada como guidance, até o fim do parágrafo."""
    from ..text.sections import classify
    from ..text.sentences import split_sentences

    whole = [t for sec, t in paragraphs if sec == "guidance"]
    if whole:
        return "\n\n".join(whole)
    if doc_date < "2008-01-01":
        return None
    parts = []
    for sec, text in paragraphs:
        if sec in ("decision", "vote"):
            continue
        sents = split_sentences(text)
        start = next((i for i, s in enumerate(sents) if classify(s) == "guidance"), None)
        if start is not None:
            parts.append(" ".join(sents[start:]))
    return "\n\n".join(parts) or None


def _document_checks(rec: MeetingRecord) -> list[str]:
    """Consistência dentro do documento (PDF vs título da listagem, votos)."""
    out: list[str] = []
    d, t = rec.decision, rec.title
    if d.action is None:
        out.append("decisão: ação não identificada no PDF")
    if t.action and d.action and t.action != d.action:
        out.append(f"decisão: PDF diz {d.action}, título diz {t.action}")
    if t.change_bp is not None and d.change_bp is not None and t.change_bp != d.change_bp:
        out.append(f"decisão: PDF {d.change_bp}pb vs título {t.change_bp}pb")
    if t.rate is not None and d.rate is not None and abs(t.rate - d.rate) > 1e-9:
        out.append(f"decisão: PDF {d.rate}% vs título {t.rate}%")
    if d.instrument == "tasa" and d.rate is None:
        out.append("decisão: nível da taxa não encontrado")
    v = rec.votes
    if v.source == "named" and v.n_for is not None and v.n_against is not None:
        if v.n_for + v.n_against != 5:
            out.append(f"votos: {v.n_for}+{v.n_against} != 5 membros")
        if v.n_against >= v.n_for:
            out.append("votos: dissidentes >= votos a favor")
    return out
