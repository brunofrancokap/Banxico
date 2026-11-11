"""Reuniões passadas parecidas com uma reunião-alvo, no texto e/ou na reação da curva.

Determinístico: classifica a sinalização de cada comunicado por regras de frase e mede a distância
entre reações de mercado. A interpretação (qual análogo importa e por quê) fica para a skill.

Mercado: vetor de variações no dia (pb) = surpresa, trajetória, inclinações 1s2s, 2s5s, 2s10s.
Cada métrica é padronizada pelo desvio-padrão de todas as reuniões com dados; a distância é a raiz
da média dos quadrados das diferenças padronizadas. Só **variações** são comparadas, então TIIE 28 e
Fondeo podem ser comparadas entre si (nunca níveis). Antes de 2025 a surpresa vem do 3m.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import Any

from .context import _docs, _fold, _resolve
from .market.events import slopes
from .storage import Store
from .text.sentences import split_sentences

FEATURES = ("surprise", "path", "1s2s", "2s5s", "2s10s")
SIGN_EPS = 1.0       # |Δ| < 1 pb conta como "zero" na comparação de sinais

# Sinalização de próximos passos, sobre a frase sem acento e em minúsculas.
# "pausa" = fim/interrupção de ciclo; "mais" = abre espaço para novos movimentos na mesma direção.
_PAUSE = [
    r"\bpausa\b",
    r"\bno (?:seran|serian|son|resultaran|resultarian) (?:recomendables|convenientes)",
    r"\bno (?:se )?considera(?:n)? (?:recomendable|conveniente)",
    r"no representa el inicio de un ciclo",
    r"ajuste puntual",
    r"mantener (?:la tasa|el objetivo)[^.]*(?:tiempo|periodo|lapso) prolongado",
    r"\bnivel alcanzado\b",
    r"\b(?:concluir|concluye|concluyo|termino|terminar|fin d)\w* (?:\w+ )?(?:el |del )?ciclo",
]
_MORE = [
    r"\b(?:recortes?|reducciones?|disminuciones?|ajustes?|incrementos?|alzas?|aumentos?) adicional",
    r"continuar con el ciclo",
    r"\bseguir (?:reduciendo|recortando|disminuyendo|incrementando|aumentando)\b",
]
_PAUSE_RE = [re.compile(p) for p in _PAUSE]
_MORE_RE = [re.compile(p) for p in _MORE]
# A frase precisa falar da política do Banxico (não de preços nem do Fed).
_POLICY_RE = re.compile(r"tasa de referencia|tasa de interes interbancaria|objetivo para la tasa|postura monetaria"
                        r"|\bciclo\b|\bla tasa\b|\bcorto\b")
_NOT_POLICY_RE = re.compile(r"reserva federal|fondos federales|\bprecios\b|inflacion (?:general|subyacente) anual")


def _is_policy(f: str) -> bool:
    return bool(_POLICY_RE.search(f)) and not _NOT_POLICY_RE.search(f)


def text_signal(paragraphs: list[tuple[str | None, str]]) -> dict[str, Any]:
    """Classifica a sinalização do comunicado: pausa | mais | misto | neutro, com as frases literais."""
    pause, more = [], []
    for _, text in paragraphs:
        for s in split_sentences(text):
            f = _fold(s)
            if not _is_policy(f):
                continue
            if any(r.search(f) for r in _PAUSE_RE):
                pause.append(s)          # frase de pausa com "adicional" negado não conta como "mais"
            elif any(r.search(f) for r in _MORE_RE):
                more.append(s)
    label = ("misto" if pause and more else "pausa" if pause else "mais" if more else "neutro")
    return {"label": label, "pause_sentences": pause, "more_sentences": more}


def _features(r: Mapping) -> dict[str, float | None]:
    d1 = json.loads(r["d1"]) if r["d1"] else {}
    out = {"surprise": r["surprise_bp"], "path": r["path_bp"]}
    out.update(slopes(d1))
    return out


def _sign(v: float | None) -> int | None:
    if v is None:
        return None
    return 0 if abs(v) < SIGN_EPS else (1 if v > 0 else -1)


def _aftermath(decs: list[Mapping], date: str, n: int = 3) -> dict[str, Any]:
    """O que o Banxico fez depois: próximas n decisões e o próximo movimento de taxa."""
    after = [d for d in decs if d["doc_date"] > date]
    base = next((d for d in decs if d["doc_date"] == date), None)
    nxt = next((d for d in after if d["action"] in ("cut", "hike")), None)

    def months(a: str, b: str) -> int:
        return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])

    def rate_change(m: int) -> float | None:
        if not base or base["rate"] is None:
            return None
        y, mo = int(date[:4]), int(date[5:7]) + m
        horizon = f"{y + (mo - 1) // 12:04d}-{(mo - 1) % 12 + 1:02d}{date[7:]}"
        if decs[-1]["doc_date"] < horizon:
            return None                     # horizonte além dos dados
        last = [d for d in decs if d["doc_date"] <= horizon and d["rate"] is not None][-1]
        return round((last["rate"] - base["rate"]) * 100)

    return {
        "next_decisions": [{"date": d["doc_date"], "action": d["action"], "change_bp": d["change_bp"],
                            "rate": d["rate"]} for d in after[:n]],
        "next_move": ({"date": nxt["doc_date"], "action": nxt["action"], "change_bp": nxt["change_bp"],
                       "months_later": months(date, nxt["doc_date"])} if nxt else None),
        "rate_change_bp_6m": rate_change(6),
        "rate_change_bp_12m": rate_change(12),
    }


def find_analogs(store: Store, date: str | None = None, n: int = 8) -> dict[str, Any]:
    docs = _docs(store)
    if not docs:
        raise SystemExit("Banco vazio. Rode `banxico sync`.")
    i = _resolve(docs, date) if date else len(docs) - 1
    target_doc = docs[i]
    tdate = target_doc["doc_date"]
    decs = list(store.decisions())
    dec_by_id = {d["document_id"]: d for d in decs}
    reactions = {r["document_id"]: r for r in store.market_reactions()}

    # padronização: desvio-padrão de cada métrica em todas as reuniões com dados
    feats = {k: _features(r) for k, r in reactions.items()}
    sd = {}
    for f in FEATURES:
        vals = [v[f] for v in feats.values() if v[f] is not None]
        mu = sum(vals) / len(vals) if vals else 0
        sd[f] = math.sqrt(sum((x - mu) ** 2 for x in vals) / max(len(vals) - 1, 1)) or 1.0

    def view(doc) -> dict[str, Any]:
        d = dec_by_id.get(doc["id"])
        return {"date": doc["doc_date"],
                "action": d["action"] if d else None, "change_bp": d["change_bp"] if d else None,
                "rate": d["rate"] if d else None,
                "vote": (f"{d['vote_type']}" + (f" {d['n_for']}x{d['n_against']}" if d and d["n_for"] else ""))
                if d and d["vote_type"] else None}

    target = view(target_doc)
    target["text_signal"] = text_signal(store.paragraphs(target_doc["id"]))
    tf = feats.get(target_doc["id"])
    target["market"] = ({"family": reactions[target_doc["id"]]["family"], **{f"{k}_bp": v for k, v in tf.items()}}
                        if tf else None)

    candidates = []
    for doc in docs[:i]:
        c = view(doc)
        sig = text_signal(store.paragraphs(doc["id"]))
        c["text_signal"] = sig
        c["same_action"] = c["action"] == target["action"]
        c["same_text_signal"] = sig["label"] == target["text_signal"]["label"]
        cf = feats.get(doc["id"])
        if cf and tf:
            pairs = [(tf[f], cf[f], f) for f in FEATURES if tf[f] is not None and cf[f] is not None]
            c["market"] = {"family": reactions[doc["id"]]["family"], **{f"{k}_bp": v for k, v in cf.items()}}
            c["market_distance"] = round(math.sqrt(sum(((a - b) / sd[f]) ** 2 for a, b, f in pairs) / len(pairs)), 3) \
                if pairs else None
            c["sign_matches"] = f"{sum(_sign(a) == _sign(b) for a, b, _ in pairs)}/{len(pairs)}"
        else:
            c["market"], c["market_distance"], c["sign_matches"] = None, None, None
        candidates.append(c)

    with_mkt = sorted((c for c in candidates if c["same_action"] and c["market_distance"] is not None),
                      key=lambda c: c["market_distance"])
    for rank, c in enumerate(with_mkt, 1):
        c["market_rank"] = rank
    market_top = with_mkt[:n]
    text_matches = [c for c in candidates if c["same_action"] and c["same_text_signal"]
                    and target["text_signal"]["label"] != "neutro"]
    both = [c for c in text_matches if c.get("market_rank") and c["market_rank"] <= n]

    keep = {c["date"] for c in market_top + text_matches}
    for c in candidates:
        if c["date"] in keep:
            c["aftermath"] = _aftermath(decs, c["date"])

    def slim(c):
        return {k: v for k, v in c.items() if k != "same_action"}

    return {
        "target": target,
        "method": {
            "market_features": [f"{f}_bp" for f in FEATURES],
            "standard_deviation_bp": {f: round(v, 2) for f, v in sd.items()},
            "distance": "raiz da média dos quadrados das diferenças padronizadas (menor = mais parecido)",
            "sign_matches": f"quantas métricas têm o mesmo sinal (|Δ| < {SIGN_EPS:g} pb = zero)",
            "text_signal": "regras de frase: pausa (fim/interrupção do ciclo) | mais (novos movimentos) | misto | neutro",
            "candidates": "só reuniões anteriores com a mesma ação (corte/alta/manutenção)",
        },
        "market_analogs": [slim(c) for c in market_top],
        "text_analogs": [slim(c) for c in text_matches],
        "both": [c["date"] for c in both],
        "caveats": [
            "Antes de 2025 a surpresa é a variação do 3m da TIIE 28 (contém expectativa da reunião seguinte).",
            "Fechamento diário: a reação mistura a decisão com outras notícias do dia.",
            "text_signal é heurístico: confira as frases (pause_sentences / more_sentences) antes de citar.",
            "Votação nominal só desde 2021-08; antes de ~2017 o comunicado não informa votação.",
        ],
    }
