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
        r"^(hacia (a)?delante|en las (siguientes|pr[oó]ximas) decisiones|la junta de gobierno (vigilar[aá]|continuar[aá]|"
        r"tomar[aá]|mantendr[aá]|estar[aá]|seguir[aá]|considera que (mantener|ser[aá]|hacia))|la junta (seguir[aá]|vigilar[aá])|"
        r"la postura de pol[ií]tica monetaria (seguir[aá]|continuar[aá]))", re.I)),
    ("assessment", re.compile(
        r"^(la junta de gobierno (evalu[oó]|valor[oó]|juzg[oó]|consider[oó]|tom[oó] en cuenta|estim[oó]|destac[oó])|"
        r"con (base en|esta|estas) |tomando en cuenta|ante (este|el) (panorama|entorno)|considerando|dad[oa]s? )", re.I)),
    ("forecast", re.compile(   # pronósticos e balanço de riscos
        r"(^(los pron[oó]sticos|las previsiones|las proyecciones|se prev[eé]|se anticipa|se estima que la inflaci[oó]n|"
        r"el balance de riesgos|los riesgos|entre los riesgos|en cuanto a los riesgos)|sujet[oa] a (diversos )?riesgos|"
        r"balance de riesgos)", re.I)),
    ("global", re.compile(r"(econom[ií]a (mundial|global)|actividad econ[oó]mica (mundial|global)|"
                          r"econom[ií]as (avanzadas|emergentes)|entorno (externo|internacional)|"
                          r"a nivel global|a nivel mundial|panorama (internacional|externo))", re.I)),
    ("markets", re.compile(r"(mercados financieros|tipo de cambio|tasas de inter[eé]s de (valores|mediano|largo)|"
                           r"valores gubernamentales|el peso mexicano|moneda nacional)", re.I)),
    ("domestic", re.compile(r"(^en m[eé]xico|actividad econ[oó]mica (en m[eé]xico|nacional|del pa[ií]s)|"
                            r"en el [aá]mbito interno|econom[ií]a mexicana|actividad productiva)", re.I)),
    ("inflation", re.compile(
        r"(inflaci[oó]n (general|anual|subyacente|no subyacente)|las presiones inflacionarias|"
        r"(la )?(trayectoria|evoluci[oó]n) (reciente )?de la inflaci[oó]n|la inflaci[oó]n )", re.I)),
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
        for name, rx in _RULES:
            if rx.search(head):
                s.section = name
                break
    return segments
