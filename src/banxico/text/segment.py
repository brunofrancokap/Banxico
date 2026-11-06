"""Montagem de segmentos a partir das linhas (inclusive parágrafos que cruzam página).

Tipos de segmento (`kind`):
    paragraph  texto corrido do corpo
    heading    linha isolada curta sem pontuação final (subtítulos, títulos de gráfico/quadro)
    table      linhas de tabela (ex.: quadro de pronósticos), uma linha por linha da tabela
    footnote   notas "1/ ...", "Fuente: ...", "Nota: ..."
    figure     texto em fonte pequena que não é nota (rótulos de gráficos nos boletins antigos)
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from .extract import Line

_FOOTNOTE = re.compile(r"^((\d{1,2}/|\*)\s|(fuente|fuentes|nota|notas)\s*:)", re.I)
_TERMINAL = re.compile(r"[.:;!?\"”»)]$")
_LIST_MARKER = re.compile(r"^([a-z]|[ivx]{1,5}|\d{1,2})[.)]$", re.I)


@dataclass
class Segment:
    seq: int
    kind: str
    page: int
    text: str
    bold: bool = False
    section: str | None = None


def _join(a: str, b: str) -> str:
    if a.endswith("-") and b[:1].islower():
        return a[:-1] + b
    return f"{a} {b}"


def _group(lines: list[Line]) -> list[list[Line]]:
    """Agrupa linhas consecutivas em parágrafos usando espaçamento, margem e pontuação."""
    if not lines:
        return []
    # Pitch = distância entre linhas de base. Não usar gap entre bboxes: elas se
    # sobrepõem (gap negativo) em espaçamento simples.
    pitches = [b.y1 - a.y1 for a, b in zip(lines, lines[1:]) if a.page == b.page and 2 < b.y1 - a.y1 < 40]
    normal_pitch = statistics.median(pitches) if pitches else 14.0
    x1s = [l.x1 for l in lines]
    right_margin = statistics.quantiles(x1s, n=10)[-1] if len(x1s) > 5 else max(x1s)

    groups: list[list[Line]] = [[lines[0]]]
    for prev, l in zip(lines, lines[1:]):
        prev_ended = bool(_TERMINAL.search(prev.text))
        prev_short = prev.x1 < right_margin - 40      # última linha de parágrafo não chega à margem
        same_row = l.page == prev.page and abs(l.y1 - prev.y1) < 2.5
        pitch = l.y1 - prev.y1

        starts_item = bool(_LIST_MARKER.match(l.text.split(" ", 1)[0]))
        if same_row or _LIST_MARKER.match(prev.text):
            new_para = False
        elif _FOOTNOTE.match(l.text) or l.bullet or (starts_item and prev_ended and prev_short):
            new_para = True
        elif l.page != prev.page:
            # Continua na página seguinte se o parágrafo anterior não terminou
            new_para = prev_ended and (prev_short or not l.text[:1].islower())
        elif not prev_ended and l.bold == prev.bold and abs(l.size - prev.size) < 0.5:
            # Frase não terminou: só quebra com espaço muito grande (ex.: subtítulo sem ponto)
            new_para = pitch > normal_pitch * 2.2 or pitch < -2
        else:
            new_para = (
                pitch > normal_pitch * 1.3                    # espaço extra entre parágrafos
                or pitch < -2                                 # voltou para cima (ordem estranha)
                or (prev.bold != l.bold and prev_ended)
                or (prev_ended and prev_short and not l.text[:1].islower())
                or (not prev_ended and prev.bold != l.bold)   # título em negrito seguido de corpo
            )
        if new_para:
            groups.append([l])
        else:
            groups[-1].append(l)
    return groups


def _text(group: list[Line]) -> str:
    text = group[0].text
    for l in group[1:]:
        text = _join(text, l.text)
    return re.sub(r"\s+([.,;:])", r"\1", text)


def _table_rows(lines: list[Line]) -> list[str]:
    """Junta células na mesma linha visual (|Δy| < 3pt), da esquerda para a direita."""
    rows: list[list[Line]] = []
    for l in sorted(lines, key=lambda l: (l.y1, l.x0)):
        if rows and abs(rows[-1][0].y1 - l.y1) < 3:
            rows[-1].append(l)
        else:
            rows.append([l])
    return [" ".join(c.text for c in sorted(r, key=lambda c: c.x0)) for r in rows]


def _is_heading(group: list[Line], text: str) -> bool:
    return len(group) <= 2 and len(text) < 110 and not _TERMINAL.search(text) and text[:1].isupper()


def build_segments(lines: list[Line]) -> list[Segment]:
    segments: list[Segment] = []

    for g in _group([l for l in lines if l.region == "body"]):
        text = _text(g)
        if _FOOTNOTE.match(text):
            kind = "footnote"
        elif _is_heading(g, text):
            kind = "heading"
        else:
            kind = "paragraph"
        bold = sum(l.bold for l in g) > len(g) / 2
        segments.append(Segment(seq=0, kind=kind, page=g[0].page, text=text, bold=bold))

    for g in _group([l for l in lines if l.region == "small"]):
        text = _text(g)
        kind = "footnote" if _FOOTNOTE.match(text) else "figure"
        segments.append(Segment(seq=0, kind=kind, page=g[0].page, text=text))

    # Tabelas: uma por página, preservando quebras de linha
    tables: dict[int, list[Line]] = {}
    for l in lines:
        if l.region == "table":
            tables.setdefault(l.page, []).append(l)
    for page, tl in tables.items():
        segments.append(Segment(seq=0, kind="table", page=page, text="\n".join(_table_rows(tl))))

    # Ordem final: corpo (parágrafos + subtítulos) na ordem de leitura; depois tabelas,
    # notas e texto de figuras, por página.
    order = {"table": 0, "footnote": 1, "figure": 2}
    main = [s for s in segments if s.kind in ("paragraph", "heading")]
    rest = sorted((s for s in segments if s.kind in order), key=lambda s: (order[s.kind], s.page))
    result = main + rest
    for i, s in enumerate(result, 1):
        s.seq = i
    return result
