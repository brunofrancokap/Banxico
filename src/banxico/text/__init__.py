"""Extração de texto de PDFs e segmentação em parágrafos/seções.

Fluxo:  PDF --extract.read_lines--> Line[] --segment.build_segments--> Segment[] --sections.label--> Segment[]

Cada mudança de regra deve incrementar EXTRACTOR_VERSION: `banxico extract`
reprocessa automaticamente documentos extraídos com versão anterior.
"""

from __future__ import annotations

from pathlib import Path

EXTRACTOR_VERSION = "comunicado-v2"  # v2: repetição só conta nas margens (bug "ciento." 2013-03-08)


def extract_document(pdf_path: Path, doc_date: str):
    """PDF -> (segmentos rotulados, nº de páginas)."""
    from .extract import read_lines
    from .sections import label
    from .segment import build_segments

    lines = read_lines(pdf_path)
    n_pages = max((l.page for l in lines), default=-1) + 1
    return label(build_segments(lines), doc_date), n_pages
