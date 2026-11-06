"""Exporta um documento extraído como Markdown legível (para humanos e para o Claude).

O .md é derivado e regenerável; a fonte da verdade continua sendo o PDF + tabela `segments`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

SECTION_LABELS = {
    "decision": "Decisão",
    "global": "Cenário global",
    "markets": "Mercados financeiros",
    "domestic": "Atividade doméstica",
    "inflation": "Inflação",
    "forecast": "Previsões e riscos",
    "assessment": "Avaliação da Junta",
    "guidance": "Forward guidance",
    "vote": "Votação",
    "other": "Outros",
}


def to_markdown(doc: Mapping, segments: Iterable, extractor_version: str) -> str:
    segments = list(segments)
    out = [
        "---",
        f"id: {doc['id']}",
        f"source: {doc['source']}",
        f"doc_type: {doc['doc_type']}",
        f"date: {doc['doc_date']}",
        f"language: {doc['language']}",
        f"title: {doc['title']!r}",
        f"url: {doc['url']}",
        f"extractor: {extractor_version}",
        "---",
        "",
        f"# {doc['doc_date']} — {doc['title']}",
        "",
    ]
    for s in segments:
        kind, section = s["kind"], s["section"]
        if kind == "paragraph":
            out.append(f"<!-- §{s['seq']} {section} -->")
            out.append(f"**{s['text']}**" if s["bold"] and section == "decision" else s["text"])
        elif kind == "heading":
            out.append(f"### {s['text']}")
        elif kind == "table":
            out.append(f"<!-- §{s['seq']} table -->")
            out.append("```text\n" + s["text"] + "\n```")
        elif kind == "footnote":
            out.append(f"> {s['text']}")
        else:  # figure: texto de gráfico, raramente útil — mantido comentado
            out.append(f"<!-- figure: {s['text'][:200].replace('--', '—')} -->")
        out.append("")
    return "\n".join(out)
