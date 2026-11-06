from pathlib import Path

import pytest

from banxico.text.extract import Line, is_boilerplate, numeric_ratio
from banxico.text.sections import label
from banxico.text.segment import build_segments
from banxico.text.sentences import first_sentence, split_sentences

RIGHT = 563.0


def mk(page, y1, text, x1=RIGHT, bold=False, size=11.0, region="body"):
    return Line(page=page, x0=57, y0=y1 - 15, x1=x1, y1=y1, text=text, size=size, bold=bold, region=region)


# --- sentenças -----------------------------------------------------------------
def test_split_sentences_keeps_numbers_and_abbreviations():
    t = ("La inflación general aumentó de 3.42 a 3.62%. El precio del gas L.P. subió. "
         "Se ubicó en 6.25% en EE.UU. Otro dato.")
    assert split_sentences(t) == [
        "La inflación general aumentó de 3.42 a 3.62%.",
        "El precio del gas L.P. subió.",
        "Se ubicó en 6.25% en EE.UU. Otro dato.",
    ]


def test_first_sentence():
    assert first_sentence("Hacia delante, la Junta vigilará. Otra frase.") == "Hacia delante, la Junta vigilará."


# --- boilerplate ---------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Comunicado de Prensa", "Anuncio de Política Monetaria", "5 de noviembre de 2026",
    "8 de febrero de 2018 Comunicado de Prensa", "C O M U N I C A C I Ó N S O C I A L",
    "Fecha: 18 de enero del 2000", "Número: 04", "2", "Página 2 de 4",
])
def test_boilerplate(text):
    assert is_boilerplate(text)


def test_not_boilerplate():
    assert not is_boilerplate("La Junta de Gobierno decidió mantener la tasa.")
    assert numeric_ratio("Actual (05/11/2026) 1/ 3.7 4.1 3.9 3.3 3.7") > 0.6


# --- segmentação ---------------------------------------------------------------
def test_paragraphs_with_overlapping_bboxes_and_page_break():
    """Linhas com espaçamento simples (bboxes sobrepostas) formam um parágrafo;
    espaço extra separa parágrafos; parágrafo continua na página seguinte."""
    lines = [
        mk(0, 200, "La Junta de Gobierno del Banco de México decidió disminuir en 25 puntos base el objetivo para", bold=True),
        mk(0, 213.6, "la Tasa de Interés Interbancaria a un día a un nivel de 6.25%.", x1=400, bold=True),
        mk(0, 233, "En el tercer trimestre de 2026, la actividad económica global se habría expandido a un"),
        mk(0, 246.6, "ritmo ligeramente menor. Los mercados mostraron volatilidad.", x1=300),
        mk(0, 266, "La Junta de Gobierno juzgó que el proceso desinflacionario ha continuado y que el traspaso"),
        mk(1, 80, "ha sido limitado.", x1=200),
        mk(1, 100, "1/ Pronóstico a partir de octubre de 2026.", x1=250),
    ]
    segs = build_segments(lines)
    kinds = [(s.kind, s.text[:25]) for s in segs]
    assert kinds == [
        ("paragraph", "La Junta de Gobierno del "),
        ("paragraph", "En el tercer trimestre de"),
        ("paragraph", "La Junta de Gobierno juzg"),
        ("footnote", "1/ Pronóstico a partir de"),
    ]
    assert segs[0].bold
    assert segs[2].text.endswith("el traspaso ha sido limitado.")


def test_same_row_fragments_and_list_markers_are_joined():
    lines = [
        mk(0, 186, "La inflación se explica por la influencia de diversos factores que se describen a"),
        mk(0, 200, "continuación. Los factores fueron:", x1=300),
        mk(0, 220, "a)", x1=70),
        mk(0, 220.5, "la demanda agregada creció.", x1=300),
        mk(0, 240, "b)", x1=70),
        mk(0, 240, "las expectativas subieron.", x1=300),
    ]
    texts = [s.text for s in build_segments(lines)]
    assert texts[1:] == ["a) la demanda agregada creció.", "b) las expectativas subieron."]


def test_inline_enumeration_wrapping_at_line_start_is_not_split():
    """Em parágrafos modernos, 'i)' pode cair no início de uma linha por quebra de linha."""
    lines = [
        mk(0, 200, "Entre los riesgos a la baja destacan: una actividad menor a la anticipada; y"),
        mk(0, 213.6, "ii) un menor traspaso de aumentos de costos. El balance se mantiene al alza.", x1=450),
    ]
    assert len(build_segments(lines)) == 1


def test_small_font_and_tables_are_separated():
    lines = [
        mk(0, 200, "La inflación general se ubicó en 3.6% y la subyacente en 4.3%, mientras que la no"),
        mk(0, 700, "1/ Nota al pie en letra pequeña.", x1=250, size=8.0, region="small"),
        mk(1, 80, "subyacente disminuyó.", x1=200),
        mk(1, 300, "Actual (05/11/2026) 1/ 3.7 4.1 3.9", region="table"),
    ]
    segs = build_segments(lines)
    assert [s.kind for s in segs] == ["paragraph", "table", "footnote"]
    assert segs[0].text.endswith("mientras que la no subyacente disminuyó.")


# --- seções --------------------------------------------------------------------
def _para(text):
    from banxico.text.segment import Segment
    return Segment(seq=0, kind="paragraph", page=0, text=text)


def test_section_labels_modern_era():
    segs = label([
        _para("La Junta de Gobierno del Banco de México decidió mantener el objetivo para la Tasa de Interés Interbancaria a un día en 6.50%."),
        _para("La actividad económica mundial continuó recuperándose. La inflación general subió."),
        _para("En los mercados financieros nacionales, el tipo de cambio se apreció."),
        _para("En México, la actividad productiva se contrajo."),
        _para("La inflación general anual aumentó a 3.6%."),
        _para("Las previsiones para la inflación se ajustaron al alza."),
        _para("La Junta de Gobierno evaluó la magnitud de los choques."),
        _para("Hacia delante, la Junta de Gobierno vigilará las presiones inflacionarias."),
        _para("Votaron a favor de la decisión Victoria Rodríguez Ceja y Omar Mejía Castelazo."),
    ], "2026-11-05")
    assert [s.section for s in segs] == [
        "decision", "global", "markets", "domestic", "inflation", "forecast", "assessment", "guidance", "vote",
    ]


@pytest.mark.parametrize("sentence, expected", [
    # guidance com "hacia delante" no meio da frase (2025) e compromissos no futuro (2016–2019)
    ("La Junta de Gobierno estima que hacia delante podría continuar con la calibración de la postura monetaria.", "guidance"),
    ("Tomando en cuenta los retos, la Junta de Gobierno continuará dando seguimiento cercano a la inflación.", "guidance"),
    ("La Junta mantendrá una postura monetaria prudente y continuará dando un seguimiento especial.", "guidance"),
    ("Esta acción no inicia un ciclo de contracción monetaria.", "guidance"),
    # reiteração da decisão no meio do comunicado
    ("En este contexto, la Junta de Gobierno ha decidido por unanimidad mantener sin cambio el objetivo.", "assessment"),
    # tema que aparece primeiro vence
    ("Los indicadores de la actividad económica de México no han resentido el debilitamiento de la economía de Estados Unidos.", "domestic"),
    ("La desaceleración económica mundial se ha intensificado en Europa y Japón.", "global"),
    ("En México, las tasas de interés de valores gubernamentales presentaron movimientos acotados.", "markets"),
    ("En México, la contracción de la actividad económica ha sido severa.", "domestic"),
    ("Desde la última reunión, las inflaciones general y subyacente anuales siguieron descendiendo.", "inflation"),
    ("En línea con las previsiones del Instituto Central, la inflación mostró un incremento en enero.", "inflation"),
    ("Ante mayores presiones inflacionarias, los pronósticos de las inflaciones se revisaron al alza.", "forecast"),
    ("Los pronósticos de inflación general permanecieron prácticamente sin cambio.", "forecast"),
])
def test_classify_sentence(sentence, expected):
    from banxico.text.sections import classify

    assert classify(sentence) == expected


def test_guidance_fallback_inside_other_paragraph():
    from banxico.structured import _guidance_text

    paras = [
        ("decision", "La Junta de Gobierno decidió mantener el objetivo en 7.00%."),
        ("inflation", "La inflación general aumentó. Hacia adelante, la Junta de Gobierno seguirá muy de cerca "
                      "la evolución de la inflación. Actuará con oportunidad."),
    ]
    assert _guidance_text(paras, "2017-03-30") == (
        "Hacia adelante, la Junta de Gobierno seguirá muy de cerca la evolución de la inflación. Actuará con oportunidad.")
    assert _guidance_text(paras, "2005-01-01") is None


def test_decision_old_era_takes_last_mention():
    segs = label([
        _para("La Junta decidió ampliar el “corto” el 23 de septiembre. Desde entonces la inflación cedió."),
        _para("Por ello, la Junta de Gobierno del Banco de México considera prudente incrementar el “corto” de 400 a 475 millones de pesos."),
    ], "2002-12-06")
    assert [s.section for s in segs] == ["other", "decision"]


# --- integração (só roda se os PDFs já foram baixados) ---------------------------
DATA = Path(__file__).resolve().parents[1] / "data" / "raw" / "comunicados"


@pytest.mark.skipif(not DATA.exists(), reason="PDFs não baixados (rode `banxico sync`)")
def test_real_pdf_2026_11_05():
    from banxico.text import extract_document

    pdf = next(DATA.glob("2026/2026-11-05_*.pdf"))
    segs, n_pages = extract_document(pdf, "2026-11-05")
    paras = [s for s in segs if s.kind == "paragraph"]
    assert n_pages == 2
    assert paras[0].section == "decision" and "6.25%" in paras[0].text
    assert any(s.section == "guidance" for s in paras)
    assert any(s.kind == "table" and "Actual (05/11/2026)" in s.text for s in segs)
    assert not any("Comunicado de Prensa" in s.text for s in segs)
