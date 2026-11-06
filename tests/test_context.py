from pathlib import Path

import pytest

from banxico.context import _fold, _quotes

DB = Path(__file__).resolve().parents[1] / "data" / "banxico.db"


def test_fold_removes_accents_and_case():
    assert _fold("Restricción MONETARIA") == "restriccion monetaria"


def test_quotes_pairing_and_line_wrap():
    body = (
        '# Título com "curta" e "uma citação longa o bastante"\n\n'
        "- as taxas “disminuyeron en sus plazos medios y largos y aumentaron en los\n"
        "  plazos cortos” e mais texto\n"
    )
    assert _quotes(body) == [
        "uma citação longa o bastante",
        "disminuyeron en sus plazos medios y largos y aumentaron en los plazos cortos",
    ]


needs_db = pytest.mark.skipif(not DB.exists(), reason="banco não gerado (rode `banxico sync`)")


@pytest.fixture
def store():
    from banxico.storage import Store

    s = Store(db_path=DB, raw_dir=DB.parent / "raw")
    if s.decision(s.extracted_documents("comunicados")[-1]["id"]) is None:
        s.close()
        pytest.skip("rode `banxico structure`")
    yield s
    s.close()


@needs_db
def test_cycle_summary(store):
    from banxico.context import cycle_summary

    c = cycle_summary(store, "2024-03-21")
    assert (c["direction"], c["cycle_start"], c["cycle_cumulative_bp"], c["rate_before_cycle"]) == (
        "cut", "2024-03-21", 25, 11.25)
    c = cycle_summary(store, "2023-02-09")
    assert (c["direction"], c["cycle_start"], c["rate_before_cycle"]) == ("hike", "2021-06-24", 4.0)


@needs_db
def test_meeting_context_shape(store):
    from banxico.context import meeting_context

    d = meeting_context(store, "2026-11-05")
    assert d["compared_with"]["date"] == "2026-09-24"
    assert d["decision"]["current"]["rate"] == 6.25
    assert d["votes"]["current"]["n_against"] == 2
    assert any(f["period"] == "2026Q4" and f["delta"] == 0.2 for f in d["forecasts"])
    guidance = [p for p in d["text_diff"]["paragraphs"] if p["section"] == "guidance"][0]
    assert any("tiempo prolongado" in s for s in guidance["added"])


@needs_db
def test_dissent_history_direction(store):
    from banxico.context import dissent_history

    d = dissent_history(store, "heath")
    assert d["by_member"]["Jonathan Heath"]["mais dovish"] == 0
    assert all(e["relative_stance"] == "mais hawkish" for e in d["events"])


@needs_db
def test_phrase_search_accent_insensitive(store):
    from banxico.context import phrase_search

    a = phrase_search(store, "restriccion monetaria", since="2024-01-01")
    b = phrase_search(store, "restricción monetaria", since="2024-01-01")
    assert a["meetings_with_phrase"] == b["meetings_with_phrase"] > 0
    assert a["in_latest_meeting"]


@needs_db
def test_section_filter_matches_unfiltered_for_guidance_phrase(store):
    """Regressão: em 2025 o guidance era rotulado 'other' e o filtro perdia 3 de 11 reuniões."""
    from banxico.context import phrase_search

    filtered = phrase_search(store, "manteniendo una postura restrictiva", section="guidance")
    unfiltered = phrase_search(store, "manteniendo una postura restrictiva")
    assert filtered["meetings_with_phrase"] == unfiltered["meetings_with_phrase"] >= 4


@needs_db
def test_guidance_field_coverage_since_2016(store):
    rows = [r for r in store.decisions("2016-01-01")]
    assert rows and all(r["guidance"] for r in rows)


@needs_db
def test_verify_quotes(store, tmp_path):
    from banxico.context import verify_quotes

    md = tmp_path / "a.md"
    md.write_text('---\nx: "ignorado no front matter"\n---\n'
                  'Ok: "mantener la tasa por un tiempo prolongado en el nivel alcanzado".\n'
                  'Inventada: "la Junta prometió subir la tasa en diciembre".\n', encoding="utf-8")
    r = verify_quotes(store, str(md))
    assert r["quotes"] == 2 and r["missing"] == ["la Junta prometió subir la tasa en diciembre"]
