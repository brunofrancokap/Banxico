from pathlib import Path

import pytest

from banxico.compare.align import align, similarity
from banxico.compare.diff import diff_documents, word_ops


def test_align_keeps_order_and_marks_gaps():
    a = ["alpha beta", "gamma delta", "epsilon"]
    b = ["alpha beta", "nuevo texto", "gamma delta", "epsilon zeta"]
    pairs = align(a, b, lambda i, j: similarity(a[i], b[j]), 0.5)
    assert pairs == [(0, 0), (None, 1), (1, 2), (2, 3)]


def test_word_ops_reconstruct_both_sides():
    old = "La Junta decidió mantener el objetivo en 6.50%."
    new = "La Junta decidió disminuir en 25 puntos base el objetivo a 6.25%."
    ops = word_ops(old, new)
    rebuilt_new = "".join(o.text for o in ops if o.kind != "delete")
    rebuilt_old = "".join(o.text for o in ops if o.kind != "insert")
    assert rebuilt_new.split() == new.split()
    assert rebuilt_old.split() == old.split()
    assert any(o.kind == "delete" and "mantener" in o.text for o in ops)


def test_diff_documents_statuses():
    old = [
        ("decision", "La Junta de Gobierno decidió mantener el objetivo en 6.50%."),
        ("global", "La economía mundial se desaceleró. El dólar se apreció."),
        ("guidance", "Dado que las condiciones son distintas, la política no reaccionará de manera mecánica."),
        ("forecast", "Se considera que el balance de riesgos mantiene un sesgo al alza."),
    ]
    new = [
        ("decision", "La Junta de Gobierno decidió disminuir en 25 puntos base el objetivo a 6.25%."),
        ("global", "La economía mundial se desaceleró. El dólar mostró variaciones acotadas."),
        ("forecast", "Se considera que el balance de riesgos mantiene un sesgo al alza."),
        ("vote", "Votaron a favor de la decisión A, B y C."),
    ]
    d = diff_documents(old, new)
    statuses = [(p.section, p.status) for p in d.paragraphs]
    assert statuses == [
        ("decision", "modified"), ("global", "modified"), ("guidance", "removed"),
        ("forecast", "unchanged"), ("vote", "added"),
    ]
    glob = d.paragraphs[1]
    assert [s.status for s in glob.sentences][0] == "unchanged"
    assert 0 < d.change_ratio < 1
    assert d.counts["added"] >= 1 and d.counts["removed"] >= 1


def test_rewritten_sentence_becomes_remove_plus_add():
    old = [("assessment", "La Junta evaluó el panorama. Valoró el comportamiento del tipo de cambio y la holgura.")]
    new = [("assessment", "La Junta evaluó el panorama. Estimó que no se perciben presiones de demanda en la economía.")]
    p = diff_documents(old, new).paragraphs[0]
    assert [s.status for s in p.sentences] == ["unchanged", "removed", "added"]


def test_identical_documents():
    doc = [("decision", "Texto igual."), ("vote", "Otro texto.")]
    d = diff_documents(doc, doc)
    assert d.change_ratio == 0 and all(p.status == "unchanged" for p in d.paragraphs)


DB = Path(__file__).resolve().parents[1] / "data" / "banxico.db"


@pytest.mark.skipif(not DB.exists(), reason="banco não gerado (rode `banxico sync`)")
def test_render_real_report(tmp_path):
    from banxico.compare.report import render_report
    from banxico.storage import Store

    store = Store(db_path=DB, raw_dir=DB.parent / "raw")
    try:
        docs = store.extracted_documents("comunicados")
        if len(docs) < 2 or store.decision(docs[-1]["id"]) is None:
            pytest.skip("rode `banxico structure`")
        new, old = docs[-1], docs[-2]
        diff = diff_documents(store.paragraphs(old["id"]), store.paragraphs(new["id"]))
        html = render_report(new, old, diff, store.decision(new["id"]), store.decision(old["id"]),
                             store.forecasts(new["id"]), store.forecasts(old["id"]), {})
    finally:
        store.close()
    assert html.startswith("<!DOCTYPE html>")
    assert "Decisão" in html and "<del>" in html and "<ins>" in html
