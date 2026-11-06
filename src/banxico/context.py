"""Contexto em JSON para análise (skills do Claude Code e outros consumidores).

Tudo aqui é determinístico: números e citações vêm do banco. A interpretação fica
para quem consome o JSON.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from .compare import diff_documents
from .market.events import slopes
from .storage import Store

SOURCE = "comunicados"


# --- utilidades ------------------------------------------------------------------
def _fold(text: str) -> str:
    """minúsculas e sem acento (busca insensível a acentuação)."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def _docs(store: Store) -> list:
    return list(store.extracted_documents(SOURCE))


def _resolve(docs: list, date: str) -> int:
    hits = [i for i, d in enumerate(docs) if d["doc_date"].startswith(date)]
    if len(hits) != 1:
        raise SystemExit(f"Data {date!r} ambígua ou inexistente ({len(hits)} resultados).")
    return hits[0]


def _decision_view(d: Mapping | None) -> dict[str, Any] | None:
    if not d:
        return None
    return {
        "instrument": d["instrument"], "action": d["action"], "change_bp": d["change_bp"],
        "rate": d["rate"], "corto_mn": d["corto_mn"], "effective_date": d["effective_date"],
        "extraordinary": bool(d["extraordinary"]),
    }


def _vote_view(d: Mapping | None) -> dict[str, Any] | None:
    if not d:
        return None
    return {
        "type": d["vote_type"], "source": d["vote_source"], "n_for": d["n_for"], "n_against": d["n_against"],
        "votes_for": json.loads(d["votes_for"]) if d["votes_for"] else [],
        "dissents": json.loads(d["dissents"]) if d["dissents"] else [],
    }


def _risk_view(d: Mapping | None, prefix: str) -> dict[str, Any] | None:
    if not d:
        return None
    return {"bias": d[f"{prefix}_bias"], "change": d[f"{prefix}_change"], "evidence": d[f"{prefix}_evidence"]}


# --- ciclo de política -------------------------------------------------------------
def cycle_summary(store: Store, upto: str, n_recent: int = 8) -> dict[str, Any]:
    """Ciclo atual (era tasa) até a data `upto`: direção, início, pb acumulados, últimas decisões."""
    rows = [r for r in store.decisions() if r["doc_date"] <= upto and r["instrument"] == "tasa"]
    if not rows:
        return {}
    moves = [r for r in rows if r["action"] in ("hike", "cut")]
    direction = moves[-1]["action"] if moves else None
    start = None
    cumulative = 0
    if direction:
        for r in reversed(moves):
            if r["action"] != direction:
                break
            start = r["doc_date"]
            cumulative += r["change_bp"] or 0
    last_move = moves[-1]["doc_date"] if moves else None
    holds_since = sum(1 for r in rows if last_move and r["doc_date"] > last_move)
    recent = [
        {"date": r["doc_date"], "action": r["action"], "change_bp": r["change_bp"], "rate": r["rate"],
         "vote": r["vote_type"], "n_for": r["n_for"], "n_against": r["n_against"],
         "dissent": r["dissent_summary"]}
        for r in rows[-n_recent:]
    ]
    peak_or_trough = (max if direction == "hike" else min)(
        (r["rate"] for r in rows if start and r["doc_date"] >= start), default=None) if direction else None
    return {
        "current_rate": rows[-1]["rate"],
        "direction": direction,                      # hike | cut | None
        "cycle_start": start,
        "cycle_cumulative_bp": cumulative if direction else 0,
        "rate_before_cycle": next((r["rate"] for r in reversed(rows) if start and r["doc_date"] < start), None),
        "extreme_rate_in_cycle": peak_or_trough,
        "last_move": last_move,
        "meetings_since_last_move": holds_since,
        "recent_decisions": recent,
    }


# --- contexto de uma reunião ---------------------------------------------------------
def meeting_context(store: Store, date: str | None = None, vs: str | None = None) -> dict[str, Any]:
    docs = _docs(store)
    if not docs:
        raise SystemExit("Nada extraído. Rode `banxico sync`.")
    i_new = _resolve(docs, date) if date else len(docs) - 1
    i_old = _resolve(docs, vs) if vs else i_new - 1
    new = docs[i_new]
    old = docs[i_old] if i_old >= 0 else None
    dn = store.decision(new["id"])
    do = store.decision(old["id"]) if old else None

    out: dict[str, Any] = {
        "meeting": {"date": new["doc_date"], "title": new["title"], "url": new["url"]},
        "compared_with": {"date": old["doc_date"], "title": old["title"], "url": old["url"],
                          "is_previous_meeting": vs is None} if old else None,
        "report_html": str(store.data_dir / "reports" / SOURCE /
                           (f"{new['doc_date']}.html" if vs is None else f"{new['doc_date']}_vs_{old['doc_date']}.html"))
        if old else None,
        "decision": {"current": _decision_view(dn), "previous": _decision_view(do)},
        "votes": {"current": _vote_view(dn), "previous": _vote_view(do)},
        "risk_balance": {
            "inflation": {"current": _risk_view(dn, "infl"), "previous": _risk_view(do, "infl")},
            "growth": {"current": _risk_view(dn, "growth"), "previous": _risk_view(do, "growth")},
        },
        "validation_warnings": [c for c in json.loads(dn["checks"] or "[]") if not c.startswith("info")] if dn else [],
        "cycle": cycle_summary(store, new["doc_date"]),
    }

    # Pronósticos: atual vs reunião comparada (ou vintage "anterior" do próprio comunicado)
    fc_new = store.forecasts(new["id"])
    fc_old = store.forecasts(old["id"]) if old else []
    forecasts = []
    for series in ("headline_yoy", "core_yoy"):
        cur = {r["period"]: r["value"] for r in fc_new if r["series"] == series and r["vintage"] == "actual"}
        prev = {r["period"]: r["value"] for r in fc_old if r["series"] == series and r["vintage"] == "actual"}
        basis = "compared_meeting"
        if cur and not prev:
            prev = {r["period"]: r["value"] for r in fc_new if r["series"] == series and r["vintage"] == "anterior"}
            basis = "own_anterior_vintage"
        for p in sorted(cur):
            forecasts.append({"series": series, "period": p, "current": cur[p], "previous": prev.get(p),
                              "delta": round(cur[p] - prev[p], 2) if p in prev else None, "basis": basis})
    out["forecasts"] = forecasts

    # Diff de texto, agrupado por parágrafo (sem repetir texto inalterado)
    if old:
        diff = diff_documents(store.paragraphs(old["id"]), store.paragraphs(new["id"]))
        paras = []
        for p in diff.paragraphs:
            item: dict[str, Any] = {"section": p.section, "status": p.status}
            if p.status == "unchanged":
                paras.append(item)
                continue
            item["similarity"] = round(p.similarity, 2)
            item["added"], item["removed"], item["edited"] = [], [], []
            for s in p.sentences:
                old_txt = "".join(o.text for o in s.ops if o.kind != "insert").strip()
                new_txt = "".join(o.text for o in s.ops if o.kind != "delete").strip()
                if s.status == "added":
                    item["added"].append(new_txt)
                elif s.status == "removed":
                    item["removed"].append(old_txt)
                elif s.status == "modified":
                    item["edited"].append({"old": old_txt, "new": new_txt})
            if p.status == "modified":
                item["full_new_text"] = p.new
            paras.append(item)
        out["text_diff"] = {"change_ratio": round(diff.change_ratio, 3), "sentence_counts": diff.counts,
                            "paragraphs": paras}
    out["guidance_text"] = {"current": dn["guidance"] if dn else None, "previous": do["guidance"] if do else None}
    out["market"] = market_view(store, new["id"])
    return out


def market_view(store: Store, doc_id: str) -> dict[str, Any] | None:
    """Reação da curva à decisão (se `banxico market` já rodou e há dados para a data)."""
    try:
        r = store.market_reaction(doc_id)
    except Exception:  # noqa: BLE001 - tabela pode não existir em bancos antigos
        return None
    if not r or not r["d1"]:
        return None
    same = [x["surprise_bp"] for x in store.market_reactions() if x["family"] == r["family"] and x["surprise_bp"] is not None]
    rank = None
    if r["surprise_bp"] is not None and same:
        # 1 = maior surpresa absoluta da família (empates dividem a posição)
        rank = {"position": 1 + sum(abs(v) > abs(r["surprise_bp"]) for v in same), "of": len(same)}
    notes = [
        "Janela: fechamento do pregão anterior -> fechamento do dia da decisão (anúncio às 13h CDMX). "
        "Fechamento diário mistura a decisão com outras notícias do dia.",
    ]
    if r["family"] == "tiie28":
        notes.append("Era TIIE 28 (antes de 2025): só variações são comparáveis; surpresa via 3m inclui "
                     "expectativa da reunião seguinte.")
    else:
        notes.append("Era Fondeo (2025+): priced_bp ≈ 1m(t−1) − tasa vigente; há uma base de ~+2 pb mesmo sem "
                     "expectativa de mudança (média das manutenções de 2026).")
    return {
        "family": r["family"],
        "window": {"prev": r["prev_date"], "decision": r["doc_date"], "next": r["next_date"]},
        "d1_bp": json.loads(r["d1"]), "d2_bp": json.loads(r["d2"]) if r["d2"] else {},
        "ust_d1_bp": json.loads(r["ust_d1"]) if r["ust_d1"] else {},
        "surprise_bp": r["surprise_bp"], "surprise_tenor": r["surprise_tenor"],
        "surprise_abs_rank_in_family": rank,
        "priced_bp": r["priced_bp"], "surprise_level_bp": r["surprise_level_bp"],
        "path_bp": r["path_bp"],
        **{f"slope_{k}_bp": v for k, v in slopes(json.loads(r["d1"])).items()},
        "flags": json.loads(r["flags"]) if r["flags"] else [],
        "notes": notes,
    }


# --- dissidências ---------------------------------------------------------------------
def dissent_history(store: Store, member: str | None = None) -> dict[str, Any]:
    rows = store.decisions()
    events, by_member = [], {}
    for r in rows:
        if not r["dissents"]:
            continue
        for x in json.loads(r["dissents"]):
            if member and _fold(member) not in _fold(x["name"]):
                continue
            # direção do dissidente relativa à decisão da maioria
            maj_bp = {"hike": 1, "cut": -1, "hold": 0}[r["action"]] * (r["change_bp"] or 0)
            dis_bp = {"hike": 1, "cut": -1, "hold": 0}.get(x["action"], 0) * (x["change_bp"] or 0)
            stance = "mais hawkish" if dis_bp > maj_bp else "mais dovish" if dis_bp < maj_bp else "igual"
            ev = {"date": r["doc_date"], "member": x["name"], "majority_action": r["action"],
                  "majority_bp": r["change_bp"], "majority_rate": r["rate"], "dissent_action": x["action"],
                  "dissent_bp": x["change_bp"], "dissent_rate": x["rate"], "relative_stance": stance,
                  "vote": f"{r['n_for']}x{r['n_against']}"}
            events.append(ev)
            m = by_member.setdefault(x["name"], {"dissents": 0, "mais hawkish": 0, "mais dovish": 0,
                                                 "first": ev["date"], "last": ev["date"]})
            m["dissents"] += 1
            m[stance] = m.get(stance, 0) + 1
            m["last"] = ev["date"]
    named_since = next((r["doc_date"] for r in rows if r["vote_source"] == "named"), None)
    named_meetings = [r for r in rows if named_since and r["doc_date"] >= named_since and r["instrument"] == "tasa"]
    split_text_era = [r["doc_date"] for r in rows if r["vote_type"] == "majority" and r["vote_source"] == "text"]
    return {
        "named_votes_since": named_since,
        "meetings_since_named_votes": len(named_meetings),
        "unanimous_since_named_votes": sum(1 for r in named_meetings if r["vote_type"] == "unanimous"),
        "by_member": by_member,
        "events": events,
        "majority_decisions_without_names": split_text_era,
        "note": "Antes de 2021-08 o comunicado não nomeia dissidentes; antes de ~2017 não informa votação.",
    }


# --- busca de frases ------------------------------------------------------------------
def phrase_search(store: Store, phrase: str, section: str | None = None, since: str | None = None) -> dict[str, Any]:
    """Em quais comunicados uma expressão aparece (insensível a acento/maiúscula), com trechos e sequências."""
    from .text.sections import classify
    from .text.sentences import split_sentences

    target = _fold(phrase)
    pattern = re.compile(r"\s+".join(map(re.escape, target.split())))
    docs = _docs(store)
    hits = []
    present = []
    for d in docs:
        if since and d["doc_date"] < since:
            continue
        found = []
        for sec, text in store.paragraphs(d["id"]):
            for s in split_sentences(text):
                if not pattern.search(_fold(s)):
                    continue
                # Filtro de seção por parágrafo OU pela própria frase: guidance de 2016–2019 vem no
                # meio de parágrafos sobre inflação ("Hacia adelante, la Junta seguirá...").
                if section and sec != section and classify(s) != section:
                    continue
                found.append({"section": sec, "sentence": s})
        present.append((d["doc_date"], bool(found)))
        if found:
            hits.append({"date": d["doc_date"], "matches": found})
    runs, cur = [], None
    for date, ok in present:
        if ok and cur is None:
            cur = [date, date]
        elif ok:
            cur[1] = date
        elif cur:
            runs.append({"from": cur[0], "to": cur[1]})
            cur = None
    if cur:
        runs.append({"from": cur[0], "to": cur[1], "ongoing": True})
    return {
        "phrase": phrase, "section_filter": section, "since": since,
        "meetings_searched": len(present), "meetings_with_phrase": len(hits),
        "first": hits[0]["date"] if hits else None, "last": hits[-1]["date"] if hits else None,
        "in_latest_meeting": bool(present and present[-1][1]),
        "runs": runs, "hits": hits,
    }


def _quotes(body: str, min_len: int = 12) -> list[str]:
    """Citações entre aspas, pareando as aspas em ordem dentro de cada linha (“…” ou "...")."""
    out = []
    # Junta linhas quebradas do markdown: blocos = parágrafos / itens de lista / linhas de tabela
    blocks = re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.|\||#)\s)", body)
    for line in (" ".join(b.split()) for b in blocks):
        marks = [m.start() for m in re.finditer(r"[\"“”]", line)]
        for a, b in zip(marks[0::2], marks[1::2]):
            q = line[a + 1:b]
            if len(q) >= min_len:
                out.append(q)
    return out


def verify_quotes(store: Store, md_path: str) -> dict[str, Any]:
    """Confere se cada citação entre aspas de uma análise existe literalmente em algum comunicado.

    Ignora acento, maiúsculas, espaços e reticências (trechos separados por "…" são checados
    por partes). Citações em português (tradução) aparecem como não encontradas: revise-as.
    """
    from pathlib import Path

    text = Path(md_path).read_text(encoding="utf-8")
    body = text.split("---", 2)[-1] if text.startswith("---") else text
    blob = "\n".join(_fold(" ".join(t.split())) for d in _docs(store) for _, t in store.paragraphs(d["id"]))
    results = []
    for q in _quotes(body):
        clean = re.sub(r"\*\*|`", "", q)
        parts = [p.strip(" .,;:") for p in re.split(r"…|\.\.\.", clean) if len(p.strip(" .,;:")) >= 6]
        ok = all(_fold(" ".join(p.split())) in blob for p in parts) if parts else True
        results.append({"quote": q, "found": ok})
    missing = [r["quote"] for r in results if not r["found"]]
    return {"file": md_path, "quotes": len(results), "found": len(results) - len(missing), "missing": missing}


def latest(store: Store) -> dict[str, Any]:
    docs = _docs(store)
    if not docs:
        return {"latest": None}
    d = docs[-1]
    return {"latest": d["doc_date"], "title": d["title"], "url": d["url"], "n_meetings": len(docs)}
