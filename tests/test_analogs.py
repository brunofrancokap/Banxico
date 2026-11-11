from pathlib import Path

import pytest

from banxico.analogs import text_signal


def _sig(*sentences: str) -> str:
    return text_signal([("guidance", " ".join(sentences))])["label"]


@pytest.mark.parametrize("text, label", [
    ("Así, decidió realizar un ajuste puntual y por mayoría reducir en 25 puntos base el objetivo para la Tasa.", "pausa"),
    ("La Junta considera que no serán recomendables reducciones adicionales al objetivo para la tasa de interés "
     "de referencia en el futuro previsible.", "pausa"),                        # "adicionales" negado
    ("La Junta juzgó apropiado realizar un recorte adicional a la tasa de referencia y con esto concluir el ciclo "
     "iniciado en marzo de 2024.", "pausa"),
    ("Hacia delante, la Junta de Gobierno valorará recortes adicionales a la tasa de referencia.", "mais"),
    ("Hacia delante, prevé que el entorno inflacionario permita seguir reduciendo la tasa de referencia.", "mais"),
    # não é política do Banxico
    ("La Reserva Federal bajó su tasa de referencia y espera implementar reducciones adicionales.", "neutro"),
    ("Ello ha resultado en alzas adicionales de los precios de las materias primas.", "neutro"),
])
def test_text_signal(text, label):
    assert _sig(text) == label


def test_text_signal_mixed():
    assert _sig("La Junta juzgó apropiado hacer una pausa en el ciclo de disminuciones de la tasa de referencia.",
                "Hacia delante, valorará realizar ajustes adicionales a la tasa de referencia.") == "misto"


DB = Path(__file__).resolve().parents[1] / "data" / "banxico.db"


@pytest.mark.skipif(not DB.exists(), reason="banco não gerado")
def test_real_analogs_2026_11_05():
    from banxico.analogs import find_analogs
    from banxico.storage import Store

    store = Store(DB)
    if not store.market_reactions():
        pytest.skip("rode `banxico market`")
    a = find_analogs(store, "2026-11-05")
    assert a["target"]["text_signal"]["label"] == "pausa"
    assert "2013-03-08" in a["both"]                                        # corte "não é início de ciclo"
    assert {"2009-07-17", "2013-10-25", "2014-06-06", "2026-05-07"} <= {c["date"] for c in a["text_analogs"]}
    assert all(c["date"] < "2026-11-05" for c in a["market_analogs"])
    nxt = next(c for c in a["text_analogs"] if c["date"] == "2013-03-08")["aftermath"]["next_move"]
    assert nxt["date"] == "2013-09-06" and nxt["months_later"] == 6
