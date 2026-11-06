"""Leitura de linhas do PDF com atributos de layout (página, posição, fonte, região)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf

# Linhas de boilerplate (cabeçalho/rodapé) presentes em várias eras.
_BOILERPLATE = [
    re.compile(p, re.I)
    for p in (
        r"^comunicado de prensa$",
        r"^anuncio de pol[ií]tica monetaria$",
        r"^c\s*o\s*m\s*u\s*n\s*i\s*c\s*a\s*c\s*i\s*[oó]\s*n\s+s\s*o\s*c\s*i\s*a\s*l$",
        r"^bolet[ií]n de prensa$",
        r"^fecha:.*$",                      # boletins 2000–2007: "Fecha: 18 de enero del 2000"
        r"^n[uú]mero:\s*\d+$",              # e "Número: 04" (às vezes na mesma linha)
        r"^\d{1,2} de [a-záéíóú]+ (de |del )?\d{4}( comunicado de prensa)?$",
        r"^comunicado de prensa \d{1,2} de [a-záéíóú]+ (de |del )?\d{4}$",
        r"^\d{1,3}$",                       # número de página
        r"^p[aá]gina \d+ de \d+$",
        r"^www\.banxico\.org\.mx$",
    )
]
_BULLET = re.compile(r"^[•●▪·\-–]\s*")
_NUMERIC_TOKEN = re.compile(r"^[-+]?\d+([.,]\d+)?%?$|^\d+/$|^[IV]+$")


@dataclass
class Line:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    size: float
    bold: bool
    region: str = "body"     # body | header | table | small
    bullet: bool = False
    page_height: float = 792.0

    @property
    def in_margin_band(self) -> bool:
        """Faixa de cabeçalho/rodapé (topo ~17% ou base ~9% da página)."""
        return self.y1 < 0.17 * self.page_height or self.y0 > 0.91 * self.page_height

    @property
    def height(self) -> float:
        return self.y1 - self.y0


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("­", "")).strip()


def is_boilerplate(text: str) -> bool:
    t = _clean(text)
    return any(p.match(t) for p in _BOILERPLATE)


def numeric_ratio(text: str) -> float:
    toks = text.split()
    if not toks:
        return 0.0
    return sum(bool(_NUMERIC_TOKEN.match(t)) for t in toks) / len(toks)


def read_lines(pdf_path: Path) -> list[Line]:
    """Linhas em ordem de leitura com região classificada (body/header/table)."""
    lines: list[Line] = []
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            try:
                table_boxes = [pymupdf.Rect(t.bbox) for t in page.find_tables().tables]
            except Exception:  # noqa: BLE001 - detecção de tabela é best-effort
                table_boxes = []
            page_lines: list[Line] = []
            for block in page.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue
                for ln in block["lines"]:
                    spans = [s for s in ln["spans"] if s["text"].strip()]
                    if not spans:
                        continue
                    text = _clean(" ".join(s["text"] for s in spans))
                    chars = Counter()
                    bold_chars = 0
                    for s in spans:
                        n = len(s["text"].strip())
                        chars[round(s["size"], 1)] += n
                        if s["flags"] & 16 or "bold" in s["font"].lower():
                            bold_chars += n
                    x0, y0, x1, y1 = ln["bbox"]
                    page_lines.append(
                        Line(
                            page=page.number, x0=x0, y0=y0, x1=x1, y1=y1, text=text,
                            size=chars.most_common(1)[0][0],
                            bold=bold_chars > 0.6 * sum(chars.values()),
                            page_height=page.rect.height,
                        )
                    )
            # Ordem de leitura: topo->baixo, esquerda->direita (blocos às vezes vêm fora de ordem)
            page_lines.sort(key=lambda l: (round(l.y0 / 3), l.x0))
            for l in page_lines:
                center = pymupdf.Point((l.x0 + l.x1) / 2, (l.y0 + l.y1) / 2)
                if any(box.contains(center) for box in table_boxes):
                    l.region = "table"
                if _BULLET.match(l.text) and len(l.text) > 3:
                    l.bullet = True
                    l.text = _BULLET.sub("", l.text)
            lines.extend(page_lines)

    _mark_headers(lines)
    _mark_numeric_tables(lines)
    return lines


def _mark_headers(lines: list[Line]) -> None:
    """Remove (região `header`): boilerplate por regex; linhas curtas repetidas em várias
    páginas *na faixa de cabeçalho/rodapé*; glifos soltos de 1 caractere (bullets de fonte
    Symbol/Wingdings). Repetição fora das margens NÃO conta: "ciento." ou "a)" podem
    legitimamente se repetir no corpo."""
    n_pages = len({l.page for l in lines})
    repeated: Counter[str] = Counter()
    if n_pages > 1:
        for _, text in {(l.page, l.text) for l in lines if len(l.text) < 80 and l.in_margin_band}:
            repeated[text] += 1
    for l in lines:
        if l.region != "body":
            continue
        if (
            is_boilerplate(l.text)
            or len(l.text) <= 1
            or (n_pages > 1 and l.in_margin_band and repeated[l.text] >= 2)
        ):
            l.region = "header"


def body_font_size(lines: list[Line]) -> float:
    """Tamanho de fonte dominante do corpo, ponderado pelo nº de caracteres."""
    weights: Counter[float] = Counter()
    for l in lines:
        if l.region == "body":
            weights[l.size] += len(l.text)
    return weights.most_common(1)[0][0] if weights else 0.0


def _mark_numeric_tables(lines: list[Line]) -> None:
    """Separa do corpo: tabelas sem bbox detectada (linhas numéricas) e texto em fonte
    pequena (notas de rodapé, fontes, rótulos de gráficos) -> região `small`."""
    size = body_font_size(lines)
    for l in lines:
        if l.region != "body":
            continue
        if (numeric_ratio(l.text) >= 0.6 and len(l.text.split()) >= 4) or numeric_ratio(l.text) == 1.0:
            l.region = "table"   # inclui números soltos (rótulos de eixo de gráficos)
        elif l.size < size - 1.2:
            l.region = "table" if numeric_ratio(l.text) >= 0.5 else "small"
