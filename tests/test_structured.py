import sqlite3
from pathlib import Path

import pytest

from banxico.structured import parse_meeting
from banxico.structured.decision import parse_decision, parse_title
from banxico.structured.forecasts import parse_forecast_table
from banxico.structured.risks import parse_risks
from banxico.structured.validate import validate_series
from banxico.structured.votes import parse_votes


# --- decisão -------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("La Junta de Gobierno del Banco de México decidió disminuir en 25 puntos base el objetivo para la Tasa "
     "de Interés Interbancaria a un día a un nivel de 6.25%, con efectos a partir del 6 de noviembre de 2026.",
     dict(instrument="tasa", action="cut", change_bp=25, rate=6.25, effective_date="2026-11-06")),
    ("La Junta de Gobierno del Banco de México decidió mantener el objetivo para la Tasa de Interés "
     "Interbancaria a un día en 6.50%.",
     dict(instrument="tasa", action="hold", change_bp=0, rate=6.5)),
    ("La Junta de Gobierno del Banco de México ha decidido mantener en 4.5 por ciento el objetivo para la "
     "Tasa de Interés Interbancaria a un día.",
     dict(instrument="tasa", action="hold", change_bp=0, rate=4.5)),
    ("La Junta de Gobierno del Banco de México ha decidido incrementar a 8.00 por ciento el objetivo para la "
     "Tasa de Interés Interbancaria a 1 día.",
     dict(instrument="tasa", action="hike", change_bp=None, rate=8.0)),
    ("Por todo lo expuesto, la Junta de Gobierno del Banco de México ha decidido aumentar el “corto” de 160 a "
     "180 millones de pesos diarios a partir de hoy 18 de enero.",
     dict(instrument="corto", action="hike", corto_mn=180)),
    ("Por tanto, la Junta de Gobierno del Banco de México ha decidido no modificar el “corto”, manteniéndolo "
     "en 25 millones de pesos diarios.",
     dict(instrument="corto", action="hold", change_bp=0, corto_mn=25)),
    ("Considerando que ha mejorado el balance de riesgos, la Junta de Gobierno del Banco de México ha decidido "
     "permitir un relajamiento de las condiciones monetarias internas no mayor a 25 puntos base. El “corto” se "
     "mantiene en 79 millones de pesos.",
     dict(instrument="corto", action="cut", change_bp=25, corto_mn=79)),
    ("La Junta de Gobierno del Banco de México ha decidido restringir las condiciones monetarias en 25 puntos "
     "base. El “corto” se mantiene en 79 millones de pesos.",
     dict(instrument="corto", action="hike", change_bp=25, corto_mn=79)),
])
def test_parse_decision(text, expected):
    d = parse_decision(text)
    for k, v in expected.items():
        assert getattr(d, k) == v, k


@pytest.mark.parametrize("title, expected", [
    ("El objetivo para la Tasa de Interés Interbancaria a 1 día (tasa objetivo) disminuye en 25 puntos base",
     dict(instrument="tasa", action="cut", change_bp=25)),
    ("El objetivo para la Tasa de Interés Interbancaria a 1 día (tasa objetivo) se mantiene sin cambio en 6.50 por ciento",
     dict(instrument="tasa", action="hold", change_bp=0, rate=6.5)),
    ('El "corto" se aumenta a 400 millones de pesos', dict(instrument="corto", action="hike", corto_mn=400)),
    ('Se restringen en 25 puntos base las condiciones monetarias. El "corto" se mantiene sin cambio',
     dict(instrument="corto", action="hike", change_bp=25)),
])
def test_parse_title(title, expected):
    d = parse_title(title)
    for k, v in expected.items():
        assert getattr(d, k) == v, k


# --- votos ---------------------------------------------------------------------
def test_named_votes_two_dissenters():
    v = parse_votes([("vote",
        "Votaron a favor de la decisión Victoria Rodríguez Ceja, José Gabriel Cuadra García y Omar Mejía "
        "Castelazo. Votaron a favor de mantener el objetivo para la Tasa de Interés Interbancaria a un día en "
        "un nivel de 6.50% Galia Borja Gómez y Jonathan Heath.")])
    assert v.vote_type == "majority" and v.source == "named"
    assert v.votes_for == ["Victoria Rodríguez Ceja", "José Gabriel Cuadra García", "Omar Mejía Castelazo"]
    assert [(d.name, d.action, d.rate) for d in v.dissents] == [
        ("Galia Borja Gómez", "hold", 6.5), ("Jonathan Heath", "hold", 6.5)]
    assert (v.n_for, v.n_against) == (3, 2)


def test_named_vote_dissenter_preferring_smaller_hike():
    v = parse_votes([("vote",
        "Votaron a favor de la decisión Victoria Rodríguez Ceja, Galia Borja Gómez, Irene Espinosa Cantellano y "
        "Jonathan Heath. Votó a favor de incrementar en 25 puntos base el objetivo para la Tasa de Interés "
        "Interbancaria a un día a un nivel de 5.75% Gerardo Esquivel Hernández.")])
    (d,) = v.dissents
    assert (d.name, d.action, d.change_bp, d.rate) == ("Gerardo Esquivel Hernández", "hike", 25, 5.75)


@pytest.mark.parametrize("text, expected", [
    ("En este contexto, la Junta de Gobierno ha decidido por unanimidad mantener sin cambio el objetivo.", "unanimous"),
    ("Así, con la presencia de todos sus miembros, decidió por mayoría reducir en 25 puntos base el objetivo.", "majority"),
    ("Esta decisión fue tomada en una reunión extraordinaria, contando con el voto favorable de todos los miembros.", "unanimous"),
    ("La economía mundial se desaceleró en la mayoría de los países.", None),
])
def test_text_votes(text, expected):
    assert parse_votes([("assessment", text)]).vote_type == expected


# --- riscos --------------------------------------------------------------------
def test_risks():
    r = parse_risks([
        "En suma, el balance de riesgos para el crecimiento mundial se deterioró.",          # global: ignorar
        "Se considera que el balance de riesgos respecto de la trayectoria prevista para la inflación en el "
        "horizonte de pronóstico es más equilibrado, pero mantiene un sesgo al alza.",
        "El balance de riesgos para el crecimiento se encuentra equilibrado.",
    ])
    assert (r["inflation"].bias, r["growth"].bias) == ("up", "balanced")
    assert "sesgo al alza" in r["inflation"].evidence


def test_risk_change_and_es_al_alza():
    r = parse_risks(["En suma, se considera que el balance de riesgos para la inflación ha mejorado.",
                     "El balance de los riesgos para la actividad económica es a la baja."])
    assert (r["inflation"].bias, r["inflation"].change) == (None, "improved")
    assert r["growth"].bias == "down"


# --- pronósticos ---------------------------------------------------------------
TABLE_2026 = """Pronósticos de la inflación general y subyacente
2025 2026 2027 2028
IV I II III IV I II III IV I II III
INPC
Actual (05/11/2026) 1/ 3.7 4.1 3.9 3.3 3.7 3.4 3.3 3.2 3.0 3.0 3.0 3.0
Anterior (24/09/2026) 2/ 3.7 4.1 3.9 3.3 3.5 3.4 3.3 3.2 3.0 3.0 3.0
Subyacente
Actual (05/11/2026) 1/ 4.3 4.5 4.2 3.9 3.7 3.4 3.3 3.2 3.0 3.0 3.0 3.0
Memorándum
Variación trimestral desestacionalizada anualizada en por ciento 3/
Actual - INPC 1/ 3.3 4.3 4.2 1.5 4.4 3.1 3.1 2.4 3.6 3.0 3.1 2.7"""


def test_forecast_table():
    points, warnings = parse_forecast_table(TABLE_2026)
    assert not warnings
    idx = {(p.vintage, p.series, p.period): p for p in points}
    assert idx[("actual", "headline_yoy", "2025Q4")].value == 3.7
    assert idx[("actual", "headline_yoy", "2026Q4")].value == 3.7
    assert idx[("anterior", "headline_yoy", "2026Q4")].value == 3.5
    assert idx[("anterior", "headline_yoy", "2026Q4")].vintage_date == "2026-09-24"
    assert ("anterior", "headline_yoy", "2028Q3") not in idx          # horizonte menor, alinhado à esquerda
    assert idx[("actual", "core_yoy", "2028Q3")].value == 3.0
    assert idx[("actual", "headline_qoq_saar", "2026Q3")].value == 1.5   # 25Q4, 26Q1, 26Q2, 26Q3


def test_forecast_spanish_vintage_date():
    t = "2021 2022\nI II III IV I\nINPC\nActual (16 de diciembre de 2021) 1/ 4.0 6.0 5.8 7.1 6.7"
    points, _ = parse_forecast_table(t)
    assert points[0].vintage_date == "2021-12-16" and points[-1].period == "2022Q1"


# --- validação de série --------------------------------------------------------
def _meeting(date, decision_text, title="", table=None):
    doc = {"id": f"x:{date}", "doc_date": date, "title": title}
    segs = [{"kind": "paragraph", "section": "decision", "text": decision_text}]
    if table:
        segs.append({"kind": "table", "section": "table", "text": table})
    return parse_meeting(doc, segs)


def test_series_derives_bp_and_flags_inconsistency():
    a = _meeting("2008-06-20", "La Junta de Gobierno ha decidido mantener en 7.75 por ciento el objetivo para la "
                               "Tasa de Interés Interbancaria a 1 día.")
    b = _meeting("2008-07-18", "La Junta de Gobierno ha decidido incrementar a 8.00 por ciento el objetivo para la "
                               "Tasa de Interés Interbancaria a 1 día.")
    c = _meeting("2008-08-15", "La Junta de Gobierno ha decidido mantener en 8.50 por ciento el objetivo para la "
                               "Tasa de Interés Interbancaria a 1 día.")
    validate_series([a, b, c])
    assert b.decision.change_bp == 25
    assert any(ch.startswith("série:") for ch in c.checks)          # hold mas taxa mudou 50pb


def test_series_forecast_vintage_consistency():
    t1 = "2026\nI II\nINPC\nActual (01/01/2026) 1/ 3.0 3.1\nAnterior (01/12/2025) 2/ 3.0"
    t2 = "2026\nI II\nINPC\nActual (01/02/2026) 1/ 3.0 3.3\nAnterior (01/01/2026) 2/ 3.0 3.2"
    m1 = _meeting("2026-01-01", "", table=t1)
    m2 = _meeting("2026-02-01", "", table=t2)
    validate_series([m1, m2])
    assert any("difere" in ch for ch in m2.checks)                 # 3.1 (actual t-1) vs 3.2 (anterior t)


# --- integração com o banco real -------------------------------------------------
DB = Path(__file__).resolve().parents[1] / "data" / "banxico.db"


@pytest.mark.skipif(not DB.exists(), reason="banco não gerado (rode `banxico sync`)")
def test_real_series_is_consistent():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    if not conn.execute("SELECT name FROM sqlite_master WHERE name='decisions'").fetchone():
        pytest.skip("rode `banxico structure`")
    rows = conn.execute("SELECT * FROM decisions WHERE doc_date >= '2008-02-01' ORDER BY doc_date").fetchall()
    assert len(rows) >= 160
    assert all(r["action"] for r in rows) and all(r["rate"] is not None for r in rows)
    assert sum(r["n_warnings"] for r in rows) == 0
    last = conn.execute("SELECT * FROM decisions WHERE doc_date = '2026-11-05'").fetchone()
    assert (last["action"], last["change_bp"], last["rate"], last["n_for"], last["n_against"]) == ("cut", 25, 6.25, 3, 2)
