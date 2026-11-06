"""Parser das páginas de listagem do CMS do Banxico (tabela `bmtableview`).

Usado por: anúncios de decisões de PM, minutas (e provavelmente outras seções).
Estrutura de cada linha:
    <TR>
      <TD class=bmdateview aria-label="05 de Noviembre 2026"><SPAN>05/11/26</SPAN></TD>
      <TD class=bmtextview>Resumo da decisão<br/><A HREF="/.../{GUID}.pdf">Texto completo</A></TD>
    </TR>
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import SourceConfig
from ..models import DocumentRef

log = logging.getLogger(__name__)

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_LONG_DATE = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de\s+)?(\d{4})", re.I)
_GUID = re.compile(r"\{([0-9A-Fa-f-]{36})\}")


def parse_spanish_date(label: str | None, fallback: str | None) -> date | None:
    """Prefere o aria-label com ano de 4 dígitos; cai para dd/mm/aa."""
    if label:
        m = _LONG_DATE.search(label)
        if m and m.group(2).lower() in MESES:
            return date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))
    if fallback:
        try:
            return datetime.strptime(fallback.strip(), "%d/%m/%y").date()
        except ValueError:
            pass
    return None


def parse_banxico_table(html: str, source: SourceConfig, base_url: str) -> list[DocumentRef]:
    soup = BeautifulSoup(html, "html.parser")
    refs: list[DocumentRef] = []
    for row in soup.select("table.bmtableview tr"):
        date_td = row.find("td", class_="bmdateview")
        text_td = row.find("td", class_="bmtextview")
        if not date_td or not text_td:
            continue
        doc_date = parse_spanish_date(date_td.get("aria-label"), date_td.get_text())
        if doc_date is None:
            log.warning("Linha sem data reconhecível: %r", date_td.get_text(strip=True))
            continue

        # Título = texto antes dos links ("Texto completo", etc.)
        title = " ".join(
            s.strip() for s in text_td.find_all(string=True, recursive=False) if s.strip()
        )

        for a in text_td.find_all("a", href=True):
            href = a["href"]
            url = urljoin(base_url, href)
            m = _GUID.search(href)
            remote_id = m.group(1).upper() if m else href.rsplit("/", 1)[-1]
            refs.append(
                DocumentRef(
                    source=source.id,
                    doc_type=source.doc_type,
                    language=source.language,
                    date=doc_date,
                    title=title,
                    url=url,
                    remote_id=remote_id,
                )
            )
    return refs
