from datetime import date

from banxico.config import SourceConfig
from banxico.http import decode_html, safe_url
from banxico.sources.banxico_table import parse_banxico_table, parse_spanish_date
from banxico.storage import Store

# Trecho real da página (estrutura preservada), codificado em cp1252 como o site serve.
SNIPPET = """<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<TABLE class="table table-striped bmtableview"><TBODY>
<TR><TD tag="[current].bm:referenceDate" class=bmdateview aria-label="05 de Noviembre 2026"><SPAN aria-hidden=true>05/11/26
</span></td>
<TD tag="[current].bm:linkText" class=bmtextview>El objetivo para la Tasa de Interés Interbancaria a 1 día (tasa objetivo) disminuye en 25 puntos base
<br/>
<A HREF="/publicaciones-y-prensa/anuncios-de-las-decisiones-de-politica-monetaria/{43236252-D06E-5231-27E8-058810A86A52}.pdf" target=_blank><SPAN>Texto completo</span></A>
</td></tr>
<TR><TD tag="[current].bm:referenceDate" class=bmdateview aria-label="18 de Enero 2000"><SPAN aria-hidden=true>18/01/00
</span></td>
<TD tag="[current].bm:linkText" class=bmtextview>El "corto" se aumenta a 180 millones de pesos
<br/>
<A HREF="/publicaciones-y-prensa/anuncios-de-las-decisiones-de-politica-monetaria/{13454A37-A216-337E-9BEE-60EC43BDB91D}.pdf" target=_blank><SPAN>Texto completo</span></A>
</td></tr>
</TBODY></TABLE></body></html>""".encode("cp1252")

SOURCE = SourceConfig(
    id="comunicados", name="x", doc_type="comunicado_pm", language="es",
    parser="banxico_table", listing_url="https://example.org",
)
BASE = "https://www.banxico.org.mx"


def test_decode_cp1252_despite_utf8_meta():
    assert "Interés" in decode_html(SNIPPET)


def test_parse_rows():
    refs = parse_banxico_table(decode_html(SNIPPET), SOURCE, BASE)
    assert len(refs) == 2
    first, last = refs
    assert first.date == date(2026, 11, 5)
    assert first.title.startswith("El objetivo para la Tasa de Interés")
    assert first.title.endswith("disminuye en 25 puntos base")
    assert first.remote_id == "43236252-D06E-5231-27E8-058810A86A52"
    assert first.url.startswith(BASE + "/publicaciones-y-prensa/")
    assert first.doc_id == "comunicados:43236252-D06E-5231-27E8-058810A86A52"
    assert last.date == date(2000, 1, 18)
    assert last.title == 'El "corto" se aumenta a 180 millones de pesos'


def test_spanish_date_fallback():
    assert parse_spanish_date(None, "26/06/00") == date(2000, 6, 26)
    assert parse_spanish_date("3 de Septiembre de 2015", None) == date(2015, 9, 3)
    assert parse_spanish_date("lixo", "lixo") is None


def test_safe_url_escapes_braces():
    url = safe_url(BASE + "/a/{ABC}.pdf")
    assert "{" not in url and url.endswith("%7BABC%7D.pdf")


def test_store_upsert_is_idempotent(tmp_path):
    store = Store(db_path=tmp_path / "t.db", raw_dir=tmp_path / "raw")
    refs = parse_banxico_table(decode_html(SNIPPET), SOURCE, BASE)
    assert store.upsert_refs(refs) == 2
    assert store.upsert_refs(refs) == 0
    pending = store.pending("comunicados")
    assert [r["doc_date"] for r in pending] == ["2000-01-18", "2026-11-05"]
    path = store.raw_path_for(pending[0], "pdf")
    assert path.as_posix().endswith("raw/comunicados/2000/2000-01-18_13454A37-A216-337E-9BEE-60EC43BDB91D.pdf")
    store.close()
