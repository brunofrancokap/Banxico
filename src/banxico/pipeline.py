"""Etapas do pipeline:
    discover  listagem -> registro (documents)
    download  registro -> data/raw (PDF)
    extract   PDF -> segments + data/text (.md)
    structure segments -> decisions + forecasts (+ data/exports/*.csv)
    report    comparações t vs t-1 -> data/reports/<fonte>/*.html
"""

from __future__ import annotations

import hashlib
import logging
import os

from .config import SourceConfig, Settings
from .http import HttpClient
from .sources import get_parser
from .storage import Store

log = logging.getLogger(__name__)


def discover(settings: Settings, client: HttpClient, store: Store, source: SourceConfig) -> tuple[int, int]:
    """Lê a página de listagem e registra os documentos. Retorna (total listado, novos)."""
    log.info("[%s] lendo listagem %s", source.id, source.listing_url)
    html = client.get_html(source.listing_url)
    refs = get_parser(source.parser)(html, source, settings.http.base_url)
    if not refs:
        raise RuntimeError(f"[{source.id}] nenhum documento encontrado; o layout da página pode ter mudado")
    new = store.upsert_refs(refs)
    log.info("[%s] %d documentos listados (%d novos)", source.id, len(refs), new)
    return len(refs), new


def download(
    client: HttpClient,
    store: Store,
    source: SourceConfig,
    since: str | None = None,
    limit: int | None = None,
    force: bool = False,
) -> tuple[int, int]:
    """Baixa documentos pendentes. Retorna (ok, erros)."""
    rows = store.pending(source.id, since=since, force=force)
    if limit:
        rows = rows[-limit:]  # os mais recentes
    log.info("[%s] %d documento(s) para baixar", source.id, len(rows))
    ok = errors = 0
    for i, row in enumerate(rows, 1):
        try:
            resp = client.get(row["url"])
            content = resp.content
            ctype = resp.headers.get("Content-Type", "").split(";")[0].strip()
            if ctype == "application/pdf" and not content.startswith(b"%PDF"):
                raise ValueError("resposta declarada como PDF não começa com %PDF")
            ext = "pdf" if ctype == "application/pdf" else row["url"].rsplit(".", 1)[-1].lower()
            path = store.raw_path_for(row, ext)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(content)
            os.replace(tmp, path)  # escrita atômica
            store.mark_downloaded(row["id"], path, hashlib.sha256(content).hexdigest(), len(content), ctype)
            ok += 1
            log.info("[%s] (%d/%d) %s ok (%d KB)", source.id, i, len(rows), row["doc_date"], len(content) // 1024)
        except Exception as exc:  # noqa: BLE001 - registra e segue para o próximo
            errors += 1
            store.mark_error(row["id"], f"{type(exc).__name__}: {exc}")
            log.error("[%s] (%d/%d) %s falhou: %s", source.id, i, len(rows), row["doc_date"], exc)
    return ok, errors


def extract(
    store: Store,
    source: SourceConfig,
    since: str | None = None,
    force: bool = False,
) -> tuple[int, int]:
    """Extrai texto/segmentos dos PDFs baixados (só os novos ou de versão antiga). Retorna (ok, erros)."""
    from .text import EXTRACTOR_VERSION, extract_document
    from .text.render import to_markdown

    rows = store.pending_extraction(source.id, EXTRACTOR_VERSION, since=since, force=force)
    log.info("[%s] %d documento(s) para extrair (%s)", source.id, len(rows), EXTRACTOR_VERSION)
    ok = errors = 0
    for row in rows:
        try:
            segments, n_pages = extract_document(store.abs_path(row["local_path"]), row["doc_date"])
            if not any(s.kind == "paragraph" for s in segments):
                raise ValueError("nenhum parágrafo extraído (PDF escaneado?)")
            text_path = store.text_path_for(row)
            text_path.parent.mkdir(parents=True, exist_ok=True)
            seg_rows = [vars(s) for s in segments]
            text_path.write_text(to_markdown(row, seg_rows, EXTRACTOR_VERSION), encoding="utf-8")
            store.save_extraction(row["id"], EXTRACTOR_VERSION, n_pages, segments, text_path)
            ok += 1
            log.debug("[%s] %s: %d segmentos", source.id, row["doc_date"], len(segments))
        except Exception as exc:  # noqa: BLE001
            errors += 1
            store.save_extraction_error(row["id"], EXTRACTOR_VERSION, f"{type(exc).__name__}: {exc}")
            log.error("[%s] %s extração falhou: %s", source.id, row["doc_date"], exc)
    log.info("[%s] extração: %d ok, %d erro(s)", source.id, ok, errors)
    return ok, errors


def structure(store: Store, source: SourceConfig) -> tuple[int, int]:
    """Extrai dados estruturados (decisão, votos, riscos, pronósticos) de TODOS os documentos
    extraídos da fonte, valida a série e exporta CSVs. Retorna (reuniões, reuniões com aviso).

    Recalcula tudo a cada execução (é rápido) porque as validações dependem da reunião anterior.
    """
    import json
    from datetime import datetime, timezone

    from .structured import STRUCT_VERSION, parse_meeting
    from .structured.validate import forecast_rows, validate_series

    if source.doc_type != "comunicado_pm":
        log.info("[%s] structure: tipo %s ainda não suportado", source.id, source.doc_type)
        return 0, 0

    records = []
    for doc in store.extracted_documents(source.id):
        records.append(parse_meeting(doc, store.segments(doc["id"])))
    validate_series(records)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows, fc_rows = [], []
    for r in records:
        d, v, t = r.decision, r.votes, r.title
        warnings = [c for c in r.checks if not c.startswith("info")]
        rows.append({
            "document_id": r.document_id, "doc_date": r.doc_date, "struct_version": STRUCT_VERSION,
            "instrument": d.instrument, "action": d.action, "change_bp": d.change_bp, "rate": d.rate,
            "corto_mn": d.corto_mn, "effective_date": d.effective_date, "extraordinary": int(r.extraordinary),
            "vote_type": v.vote_type, "vote_source": v.source, "n_for": v.n_for, "n_against": v.n_against,
            "votes_for": json.dumps(v.votes_for, ensure_ascii=False) if v.votes_for else None,
            "dissents": json.dumps([vars(x) for x in v.dissents], ensure_ascii=False) if v.dissents else None,
            "dissent_summary": "; ".join(
                f"{x.name}: {x.action}" + (f" {x.change_bp}pb" if x.change_bp else "") for x in v.dissents
            ) or None,
            "infl_bias": r.risks["inflation"].bias, "infl_change": r.risks["inflation"].change,
            "infl_evidence": r.risks["inflation"].evidence,
            "growth_bias": r.risks["growth"].bias, "growth_change": r.risks["growth"].change,
            "growth_evidence": r.risks["growth"].evidence,
            "guidance": r.guidance,
            "title_action": t.action, "title_change_bp": t.change_bp, "title_rate": t.rate,
            "checks": json.dumps(r.checks, ensure_ascii=False) if r.checks else None,
            "n_warnings": len(warnings), "parsed_at": now,
        })
        fc_rows.extend(forecast_rows(r))
        for w in warnings:
            log.warning("[%s] %s: %s", source.id, r.doc_date, w)

    store.replace_structured(source.id, rows, fc_rows)
    _export_csv(store, source.id, rows, fc_rows)
    flagged = sum(1 for r in rows if r["n_warnings"])
    log.info("[%s] structure: %d reuniões, %d pontos de pronóstico, %d reunião(ões) com aviso",
             source.id, len(rows), len(fc_rows), flagged)
    return len(rows), flagged


def _export_csv(store: Store, source_id: str, rows: list[dict], fc_rows: list[tuple]) -> None:
    """CSV em utf-8-sig (abre direto no Excel com acentos)."""
    import csv

    out = store.data_dir / "exports"
    out.mkdir(parents=True, exist_ok=True)
    skip = {"struct_version", "parsed_at", "votes_for", "dissents", "infl_evidence", "growth_evidence", "checks"}
    if rows:
        cols = [c for c in rows[0] if c not in skip]
        with open(out / f"{source_id}_decisions.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    dates = {r["document_id"]: r["doc_date"] for r in rows}
    with open(out / f"{source_id}_forecasts.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["doc_date", "vintage", "vintage_date", "series", "period", "value"])
        for doc_id, vintage, vdate, series, period, value in fc_rows:
            w.writerow([dates[doc_id], vintage, vdate, series, period, value])
    log.info("[%s] CSVs em %s", source_id, out)


def report(store: Store, source: SourceConfig, date: str | None = None, vs: str | None = None) -> list:
    """Gera relatórios HTML de comparação em data/reports/<fonte>/.

    Sem `date`: todas as comparações consecutivas (t vs t-1) + index.html.
    Com `date` (e opcional `vs`): só esse par (padrão: vs reunião anterior).
    Retorna os caminhos gerados.
    """
    from .compare import diff_documents
    from .compare.report import decision_summary, describe_vote, flags, render_index, render_report

    docs = list(store.extracted_documents(source.id))
    by_date = {d["doc_date"]: i for i, d in enumerate(docs)}
    out_dir = store.data_dir / "reports" / source.id
    out_dir.mkdir(parents=True, exist_ok=True)

    def fname(i: int) -> str:
        return f"{docs[i]['doc_date']}.html"

    def build(i_new: int, i_old: int, consecutive: bool):
        new, old = docs[i_new], docs[i_old]
        diff = diff_documents(store.paragraphs(old["id"]), store.paragraphs(new["id"]))
        nav: dict[str, str | None] = {}
        if consecutive:
            nav["prev"] = fname(i_new - 1) if i_new - 1 >= 1 else None
            nav["next"] = fname(i_new + 1) if i_new + 1 < len(docs) else None
        html = render_report(new, old, diff, store.decision(new["id"]), store.decision(old["id"]),
                             store.forecasts(new["id"]), store.forecasts(old["id"]), nav)
        path = out_dir / (fname(i_new) if consecutive else f"{new['doc_date']}_vs_{old['doc_date']}.html")
        path.write_text(html, encoding="utf-8")
        return path, diff

    def resolve(d: str) -> int:
        hits = [k for k in by_date if k.startswith(d)]
        if len(hits) != 1:
            raise SystemExit(f"Data {d!r} ambígua ou inexistente: {hits[:5] or 'nenhuma'}")
        return by_date[hits[0]]

    if date:
        i_new = resolve(date)
        i_old = resolve(vs) if vs else i_new - 1
        if i_old < 0:
            raise SystemExit("Primeiro comunicado da série: não há anterior para comparar.")
        path, diff = build(i_new, i_old, consecutive=vs is None)
        log.info("[%s] %s vs %s: %.0f%% do texto alterado -> %s", source.id, docs[i_new]["doc_date"],
                 docs[i_old]["doc_date"], diff.change_ratio * 100, path)
        return [path]

    paths, index_rows = [], []
    for i in range(1, len(docs)):
        path, diff = build(i, i - 1, consecutive=True)
        paths.append(path)
        dec = store.decision(docs[i]["id"])
        index_rows.append({
            "date": docs[i]["doc_date"], "prev_date": docs[i - 1]["doc_date"], "file": path.name,
            "decision": decision_summary(dec),
            "vote": describe_vote(dec)[0] if dec and dec["vote_type"] else "",
            "change_ratio": diff.change_ratio, "flags": flags(dec),
        })
    index_rows.reverse()
    (out_dir / "index.html").write_text(render_index(index_rows), encoding="utf-8")
    log.info("[%s] %d relatórios + index em %s", source.id, len(paths), out_dir)
    return paths
