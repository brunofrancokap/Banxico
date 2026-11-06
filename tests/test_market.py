from pathlib import Path

import pytest

from banxico.market import Curve, compute_reactions, slopes
from banxico.market.events import is_bad_print
from banxico.market.loader import read_combined_fondeo, read_daily, read_tiie28


def test_tiie28_reader_maps_mpswf_to_6m(tmp_path):
    """Armadilha: no arquivo de TIIE 28, 'MPSWF' é o swap de 6 MESES, não Fondeo."""
    p = tmp_path / "MPSW.csv"
    p.write_text("date;MPSWC CURNCY;MPSWF CURNCY;MPSW2B CURNCY\n31/12/2024;10,205;10,03;9,42\n", encoding="utf-8")
    q = {x.series: x.value for x in read_tiie28(p)}
    assert q == {"tiie28_3m": 10.205, "tiie28_6m": 10.03, "tiie28_2y": 9.42}


def test_combined_keeps_only_real_fondeo(tmp_path):
    p = tmp_path / "MPSWF_combined.csv"
    p.write_text("date,3m,2y,1m\n2024-12-18,9.92,8.97,\n2024-12-19,9.91,9.06,10.05\n2025-01-02,9.91,9.12,10.04\n",
                 encoding="utf-8")
    got = sorted((x.series, x.date) for x in read_combined_fondeo(p))
    assert got == [("fondeo_1m", "2024-12-19"), ("fondeo_1m", "2025-01-02"),
                   ("fondeo_2y", "2025-01-02"), ("fondeo_3m", "2025-01-02")]


def test_daily_reader_two_blocks(tmp_path):
    p = tmp_path / "MPSWF_20261105.csv"
    p.write_text(
        "date;MPSWFA CURNCY;MPSWF1A CURNCY;MPSWF2B CURNCY\n05/11/2026;6.275;6.4925;6.91\n"
        "date;USGG2YR Index;USGG10YR Index;;\n05/11/2026;4.4623;4.8347;;\n", encoding="utf-8")
    q = {x.series: x.value for x in read_daily(p)}
    assert q == {"fondeo_1m": 6.275, "fondeo_1y": 6.4925, "fondeo_2y": 6.91, "ust_2y": 4.4623, "ust_10y": 4.8347}


def _curve(rows: dict[str, dict[str, float]]) -> Curve:
    return Curve(rows)


def test_bad_print_vs_real_move():
    days = ["2022-09-27", "2022-09-28", "2022-09-29"]
    # 1y despenca só num dia com 9m e 2y estáveis -> print errado
    bad = _curve({
        "tiie28_9m": dict(zip(days, [10.52, 10.47, 10.50])),
        "tiie28_1y": dict(zip(days, [10.635, 10.21, 10.585])),
        "tiie28_2y": dict(zip(days, [10.277, 10.182, 10.150])),
    })
    assert is_bad_print(bad, "tiie28_1y", "2022-09-28")
    assert not is_bad_print(bad, "tiie28_2y", "2022-09-28")      # vizinho contaminado não é culpado
    # curva inteira cai e volta (2020-03-20) -> movimento real
    real = _curve({
        "tiie28_7y": dict(zip(days, [7.465, 7.070, 7.320])),
        "tiie28_10y": dict(zip(days, [7.640, 7.280, 7.540])),
        "tiie28_15y": dict(zip(days, [7.830, 7.482, 7.845])),
    })
    assert not is_bad_print(real, "tiie28_10y", "2022-09-28")


def test_reaction_fondeo_surprise_and_priced():
    c = _curve({
        "fondeo_1m": {"2026-11-04": 6.43, "2026-11-05": 6.275, "2026-11-06": 6.275},
        "fondeo_1y": {"2026-11-04": 6.525, "2026-11-05": 6.4925, "2026-11-06": 6.46},
        "fondeo_2y": {"2026-11-04": 6.91, "2026-11-05": 6.91, "2026-11-06": 6.885},
        "fondeo_10y": {"2026-11-04": 8.09, "2026-11-05": 8.16, "2026-11-06": 8.115},
    })
    decisions = [
        {"document_id": "a", "doc_date": "2026-09-24", "instrument": "tasa", "action": "hold", "change_bp": 0, "rate": 6.5},
        {"document_id": "b", "doc_date": "2026-11-05", "instrument": "tasa", "action": "cut", "change_bp": 25, "rate": 6.25},
    ]
    r = compute_reactions(c, decisions)[1]
    assert (r.family, r.prev_date, r.surprise_tenor, r.surprise_bp) == ("fondeo", "2026-11-04", "1m", -15.5)
    assert r.priced_bp == -7.0 and r.surprise_level_bp == -18.0
    assert r.slope_bp == 7.0 and r.path_bp == pytest.approx(12.25)
    assert slopes(r.d1) == {"1s2s": 3.25, "2s5s": None, "2s10s": 7.0}   # sem 5y na curva de teste


def test_reaction_family_by_date_never_crosses_splice():
    c = _curve({
        "tiie28_2y": {"2024-12-18": 9.24, "2024-12-19": 9.355, "2024-12-31": 9.42},
        "tiie28_3m": {"2024-12-18": 10.185, "2024-12-19": 10.18, "2024-12-31": 10.205},
        "fondeo_2y": {"2025-01-02": 9.12, "2025-02-05": 8.90, "2025-02-06": 8.83},
    })
    decisions = [
        {"document_id": "a", "doc_date": "2024-12-19", "instrument": "tasa", "action": "cut", "change_bp": 25, "rate": 10.0},
        {"document_id": "b", "doc_date": "2025-02-06", "instrument": "tasa", "action": "cut", "change_bp": 50, "rate": 9.5},
    ]
    a, b = compute_reactions(c, decisions)
    assert a.family == "tiie28" and a.prev_date == "2024-12-18" and a.surprise_tenor == "3m"
    assert b.family == "fondeo" and b.prev_date == "2025-02-05"
    assert a.priced_bp is None                               # nível só na era Fondeo


DB = Path(__file__).resolve().parents[1] / "data" / "banxico.db"


@pytest.mark.skipif(not DB.exists(), reason="banco não gerado")
def test_real_market_known_events():
    import sqlite3

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    if not conn.execute("SELECT name FROM sqlite_master WHERE name='market_reactions'").fetchone() or \
            not conn.execute("SELECT 1 FROM market_reactions LIMIT 1").fetchone():
        pytest.skip("rode `banxico market`")
    s = {r["doc_date"]: r["surprise_bp"] for r in conn.execute("SELECT doc_date, surprise_bp FROM market_reactions")}
    assert s["2016-02-17"] > 30            # alta extraordinária de 50 pb
    assert s["2009-03-20"] < -40           # corte de 75 pb
    assert s["2026-11-05"] == -15.5
