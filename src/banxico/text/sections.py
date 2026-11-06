"""Rotulagem heurística de seções dos comunicados de PM (era tasa objetivo, 2008+).

É um *palpite* por palavras-chave no início do parágrafo, usado para alinhar
parágrafos no diff e filtrar análises. Rótulos:
    decision · global · markets · domestic · inflation · forecast · assessment ·
    guidance · vote · other
Para 2000–2007 (era do "corto") tudo vira `other`, exceto decisão/votos.
"""

from __future__ import annotations

import re

from .segment import Segment
from .sentences import first_sentence, split_sentences

# (rótulo, regex aplicada à PRIMEIRA FRASE do parágrafo). A ordem importa.
_RULES: list[tuple[str, re.Pattern]] = [
    ("vote", re.compile(r"^(votaron|vot[oó]|la decisi[oó]n (fue|se tom[oó]) (por )?unanim|por unanimidad)", re.I)),
    ("guidance", re.compile(
        r"(^(hacia (a)?delante|en las (siguientes|pr[oó]ximas) (decisiones|reuniones)|la junta de gobierno (vigilar[aá]|"
        r"continuar[aá]|tomar[aá]|mantendr[aá]|estar[aá]|seguir[aá]|considera que (mantener|ser[aá]|hacia))|"
        r"la junta (seguir[aá]|vigilar[aá])|la postura de pol[ií]tica monetaria (seguir[aá]|continuar[aá])|"
        r"esta acci[oó]n no inicia|las acciones futuras)"
        # "La Junta de Gobierno estima que hacia delante podría..." (2025): "hacia delante" no meio da frase
        r"|^la junta[^.]{0,60}\bhacia (a)?delante"
        # compromissos no futuro no meio da frase (2016–2019): "Tomando en cuenta..., la Junta de
        # Gobierno continuará dando seguimiento..."; "...la política monetaria se ajustará de manera oportuna"
        r"|la junta( de gobierno)? (continuar[aá]|seguir[aá]|vigilar[aá]|mantendr[aá]|tomar[aá] las (acciones|medidas))"
        r"|la pol[ií]tica monetaria (se ajustar[aá]|actuar[aá]))", re.I)),
    ("assessment", re.compile(
        r"(^(la junta de gobierno (evalu[oó]|valor[oó]|juzg[oó]|consider[oó]|tom[oó] en cuenta|estim[oó]|destac[oó])|"
        r"con (base en|esta|estas) |tomando en cuenta|ante (este|el) (panorama|entorno)|considerando|dad[oa]s? )"
        # reiteração da decisão / avaliação da postura no meio do comunicado
        r"|la junta de gobierno (ha decidido|decidi[oó]|considera que la postura)"
        r"|^a partir de lo anterior)", re.I)),
    ("forecast", re.compile(   # pronósticos e balanço de riscos
        r"(^(los pron[oó]sticos|las previsiones|las proyecciones|se prev[eé]|se anticipa|se estima que la inflaci[oó]n|"
        r"el balance de riesgos|los riesgos|entre los riesgos|en cuanto a los riesgos)|sujet[oa] a (diversos )?riesgos|"
        r"balance de riesgos|"
        # revisão de pronósticos (não basta mencionar "previsiones": "En línea con las previsiones, la inflación...")
        r"(pron[oó]sticos|previsiones|trayectorias esperadas)[^.]{0,80}(se (revis|ajust|modific|mantien)|presentan ajustes)|"
        r"actualizaci[oó]n de las trayectorias|se (contin[uú]a|sigue) (esperando|anticipando))", re.I)),
    ("global", re.compile(r"(econom[ií]a (mundial|global)|(actividad|crecimiento) econ[oó]mic[oa] (mundial|global)|"
                          r"econom[ií]as (avanzadas|emergentes)|entorno (externo|internacional)|"
                          r"a nivel global|a nivel mundial|panorama (internacional|externo)|"
                          r"crisis financiera global|recuperaci[oó]n global|desaceleraci[oó]n econ[oó]mica mundial|"
                          r"comercio (mundial|global)|pa[ií]ses industrializados|entre (pa[ií]ses|regiones)|"
                          r"zona del euro|eurozona|uni[oó]n europea|econom[ií]a de estados unidos)", re.I)),
    ("markets", re.compile(r"(mercados financieros|tipo de cambio|tasas de inter[eé]s (de (valores|mediano|largo)|en m[eé]xico)|"
                           r"valores gubernamentales|el peso mexicano|moneda nacional|cotizaci[oó]n del peso|"
                           r"depreciaci[oó]n generalizada de las monedas|volatilidad financiera)", re.I)),
    ("domestic", re.compile(r"(^en m[eé]xico,? (el pib|la actividad|la econom[ií]a|el crecimiento)|"
                            r"actividad econ[oó]mica (en m[eé]xico|de m[eé]xico|nacional|del pa[ií]s)|"
                            r"en el [aá]mbito interno|econom[ií]a (mexicana|nacional)|actividad productiva|"
                            r"actividad en m[eé]xico|crecimiento econ[oó]mico en m[eé]xico|"
                            r"en cuanto a la actividad econ[oó]mica|estancamiento de la actividad|"
                            r"debilidad[^.]{0,60}actividad econ[oó]mica)", re.I)),
    ("inflation", re.compile(
        r"(inflaci[oó]n (general|anual|subyacente|no subyacente)|las presiones inflacionarias|"
        r"(la )?(trayectoria|evoluci[oó]n) (reciente )?de la inflaci[oó]n|la inflaci[oó]n |\binflaciones\b|"
        r"en cuanto a la inflaci[oó]n|cifras de inflaci[oó]n|choques inflacionarios)", re.I)),
]
_DECISION = re.compile(r"(ha decidido|decidi[oó]|ha resuelto|resolvi[oó]|considera prudente|ha determinado)"
                       r".{0,200}(tasa de inter[eé]s interbancaria|tasa objetivo|corto|condiciones monetarias|"
                       r"postura de (la )?pol[ií]tica monetaria)", re.I)


def _is_decision(text: str) -> bool:
    return any(_DECISION.search(s) for s in split_sentences(text))


def _decision_index(paragraphs: list[Segment], tasa_era: bool) -> int | None:
    """Era tasa objetivo: a decisão abre o comunicado (1º match; parágrafos posteriores
    só a reiteram). Era do "corto": a decisão costuma vir no fim, após menções
    retrospectivas a decisões anteriores (último match)."""
    hits = [i for i, s in enumerate(paragraphs) if _is_decision(s.text)]
    if not hits:
        return None
    return hits[0] if tasa_era else hits[-1]


def label(segments: list[Segment], doc_date: str) -> list[Segment]:
    tasa_era = doc_date >= "2008-01-01"
    paragraphs = [s for s in segments if s.kind == "paragraph"]
    decision = _decision_index(paragraphs, tasa_era)
    for s in segments:
        if s.kind != "paragraph":
            s.section = s.kind          # heading / table / footnote / figure
    for i, s in enumerate(paragraphs):
        if i == decision:
            s.section = "decision"
            continue
        s.section = "other"
        head = first_sentence(s.text)
        if not tasa_era and not head.lower().startswith(("votaron", "votó")):
            continue
        s.section = classify(head)
    return segments


# Regras "funcionais" têm prioridade fixa (identificam o papel do parágrafo); as temáticas
# competem pela posição: vence o tema mencionado primeiro na frase
# ("la actividad económica de México no resintió... la economía de Estados Unidos" -> domestic).
_PRIORITY = ("vote", "guidance", "assessment", "forecast")
_TOPICAL = ("global", "markets", "domestic", "inflation")


def classify(sentence: str) -> str:
    rules = dict(_RULES)
    for name in _PRIORITY:
        if rules[name].search(sentence):
            return name
    hits = [(m.start(), name) for name in _TOPICAL if (m := rules[name].search(sentence))]
    if hits:
        return min(hits)[1]
    # "En México, ..." sem outro tema reconhecível: atividade doméstica (fallback fraco, para não
    # roubar "En México, las tasas de interés..." de markets)
    if _EN_MEXICO.search(sentence):
        return "domestic"
    return "other"


_EN_MEXICO = re.compile(r"^en m[eé]xico\b", re.I)
