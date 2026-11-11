"""Linha de comando.

Exemplos:
    uv run banxico sources
    uv run banxico discover                 # todas as fontes habilitadas
    uv run banxico download -s comunicados --since 2015-01-01
    uv run banxico sync                     # discover + download + extract + structure + report
    uv run banxico extract --force          # reextrai tudo (após mudar regras)
    uv run banxico structure                # decisões/votos/riscos/pronósticos + CSVs
    uv run banxico decisions --since 2024   # tabela de decisões
    uv run banxico report --open            # HTML de todas as comparações t vs t-1 + índice
    uv run banxico diff --open              # último comunicado vs anterior, abre no navegador
    uv run banxico diff 2026-11-05 --vs 2024-03-21
    uv run banxico market                   # carrega data/TIIE e calcula reação da curva (manual)
    uv run banxico reactions --since 2025   # tabela de reações
    uv run banxico show 2026-11-05          # parágrafos de um comunicado
    uv run banxico status
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import load_settings
from .http import HttpClient
from .pipeline import discover, download, extract, report, structure
from .market.events import slopes
from .storage import Store


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="banxico", description="Coleta de documentos oficiais do Banxico")
    p.add_argument("-v", "--verbose", action="store_true", help="log detalhado")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_source_arg(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("-s", "--source", action="append", help="id da fonte (repetível); padrão: habilitadas")

    sub.add_parser("sources", help="lista as fontes configuradas")

    sp = sub.add_parser("discover", help="lê as páginas de listagem e registra documentos")
    add_source_arg(sp)

    for name, help_ in (("download", "baixa documentos pendentes"), ("sync", "discover + download + extract + structure + report")):
        sp = sub.add_parser(name, help=help_)
        add_source_arg(sp)
        sp.add_argument("--since", help="só documentos com data >= YYYY-MM-DD")
        sp.add_argument("--limit", type=int, help="baixa só os N mais recentes")
        sp.add_argument("--force", action="store_true", help="rebaixa mesmo se já baixado")

    sp = sub.add_parser("extract", help="extrai texto e segmentos dos PDFs baixados")
    add_source_arg(sp)
    sp.add_argument("--since", help="só documentos com data >= YYYY-MM-DD")
    sp.add_argument("--force", action="store_true", help="reextrai mesmo se já na versão atual")

    sp = sub.add_parser("show", help="mostra os segmentos de um documento")
    sp.add_argument("date", help="data (YYYY-MM-DD, ou prefixo YYYY-MM) ou id do documento")
    sp.add_argument("-s", "--source", default="comunicados")
    sp.add_argument("--all", action="store_true", help="inclui tabelas, notas e texto de gráficos")

    sp = sub.add_parser("structure", help="extrai decisão, votos, riscos e pronósticos; exporta CSVs")
    add_source_arg(sp)

    sp = sub.add_parser("decisions", help="mostra a tabela de decisões")
    sp.add_argument("--since", help="data inicial (YYYY ou YYYY-MM-DD)")
    sp.add_argument("--checks", action="store_true", help="mostra avisos de validação")

    sp = sub.add_parser("report", help="gera HTML de todas as comparações t vs t-1 + índice")
    add_source_arg(sp)
    sp.add_argument("--open", action="store_true", help="abre o índice no navegador")

    sp = sub.add_parser("diff", help="compara um comunicado com o anterior (ou com --vs) em HTML")
    sp.add_argument("date", nargs="?", help="data (YYYY-MM-DD ou prefixo único); padrão: o mais recente")
    sp.add_argument("--vs", help="data do comunicado de referência (padrão: reunião anterior)")
    sp.add_argument("-s", "--source", default="comunicados")
    sp.add_argument("--open", action="store_true", help="abre no navegador")

    # --- saídas JSON para análise (usadas pelas skills em .claude/skills) ---
    sp = sub.add_parser("context", help="JSON com decisão, votos, riscos, pronósticos, diff e ciclo de uma reunião")
    sp.add_argument("date", nargs="?", help="data (padrão: a mais recente)")
    sp.add_argument("--vs", help="reunião de referência (padrão: a anterior)")

    sp = sub.add_parser("dissents", help="JSON com o histórico de dissidências nominais")
    sp.add_argument("--member", help="filtra por nome (parcial, sem acento)")

    sp = sub.add_parser("search", help="JSON: em quais comunicados uma expressão aparece")
    sp.add_argument("phrase")
    sp.add_argument("--section", help="decision|global|markets|domestic|inflation|forecast|assessment|guidance|vote")
    sp.add_argument("--since", help="data inicial")

    sub.add_parser("latest", help="JSON com o comunicado mais recente no banco")

    sp = sub.add_parser("analogs", help="JSON: reuniões passadas parecidas (texto e reação da curva)")
    sp.add_argument("date", nargs="?", help="data (padrão: a mais recente)")
    sp.add_argument("-n", type=int, default=8, help="nº de análogos de mercado (padrão 8)")

    sp = sub.add_parser("verify-quotes", help="confere se as citações de uma análise existem nos comunicados")
    sp.add_argument("file", help="arquivo .md da análise")

    sp = sub.add_parser("market", help="carrega data/TIIE (swaps TIIE 28/Fondeo, Treasuries) e calcula reações")
    sp.add_argument("--dir", help="pasta dos CSVs (padrão: data/TIIE)")

    sp = sub.add_parser("reactions", help="tabela de reação da curva às decisões")
    sp.add_argument("--since", help="data inicial")

    sub.add_parser("status", help="resumo do registro de documentos")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    # Console do Windows: evita UnicodeEncodeError com acentos
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = load_settings()

    if args.cmd == "sources":
        for s in settings.sources.values():
            flag = "on " if s.enabled else "off"
            print(f"[{flag}] {s.id:<14} {s.doc_type:<15} {s.language}  {s.name}")
        return 0

    store = Store()
    try:
        if args.cmd == "status":
            rows = store.summary()
            if not rows:
                print("Registro vazio. Rode `banxico sync`.")
            for r in rows:
                print(f"{r['source']:<14} {r['status']:<11} {r['n']:>5}  {r['first']} → {r['last']}")
            for r in store.extraction_summary():
                print(f"{r['source']:<14} extraídos   {r['n']:>5}  {r['extractor_version']}  "
                      f"({r['paragraphs']} parágrafos, {r['errors']} erro(s))")
            dec = store.decisions()
            if dec:
                flagged = sum(1 for r in dec if r["n_warnings"])
                print(f"{'decisões':<14} {'':<11} {len(dec):>5}  {dec[0]['struct_version']}  ({flagged} com aviso)")
            return 0

        if args.cmd == "show":
            return _show(store, args)
        if args.cmd == "decisions":
            return _decisions(store, args)
        if args.cmd == "market":
            from pathlib import Path

            from .pipeline import market_and_reports

            market_and_reports(store, settings.sources["comunicados"], Path(args.dir) if args.dir else None)
            return 0
        if args.cmd == "reactions":
            return _reactions(store, args)
        if args.cmd == "analogs":
            from .analogs import find_analogs

            print(json.dumps(find_analogs(store, args.date, args.n), ensure_ascii=False, indent=1))
            return 0
        if args.cmd in ("context", "dissents", "search", "latest", "verify-quotes"):
            from . import context as ctx

            if args.cmd == "verify-quotes":
                data = ctx.verify_quotes(store, args.file)
                print(json.dumps(data, ensure_ascii=False, indent=1))
                return 1 if data["missing"] else 0
            if args.cmd == "context":
                data = ctx.meeting_context(store, args.date, args.vs)
            elif args.cmd == "dissents":
                data = ctx.dissent_history(store, args.member)
            elif args.cmd == "search":
                data = ctx.phrase_search(store, args.phrase, args.section, args.since)
            else:
                data = ctx.latest(store)
            print(json.dumps(data, ensure_ascii=False, indent=1))
            return 0

        failures = 0
        if args.cmd == "extract":
            for source in settings.resolve(args.source):
                failures += extract(store, source, since=args.since, force=args.force)[1]
            return 1 if failures else 0
        if args.cmd == "structure":
            for source in settings.resolve(args.source):
                structure(store, source)
            return 0
        if args.cmd == "report":
            for source in settings.resolve(args.source):
                paths = report(store, source)
                if args.open and paths:
                    _open(paths[0].parent / "index.html")
            return 0
        if args.cmd == "diff":
            source = settings.resolve([args.source])[0]
            docs = store.extracted_documents(source.id)
            if not docs:
                print("Nada extraído ainda. Rode `banxico sync`.")
                return 1
            (path,) = report(store, source, date=args.date or docs[-1]["doc_date"], vs=args.vs)
            print(path)
            if args.open:
                _open(path)
            return 0

        client = HttpClient(settings.http)
        for source in settings.resolve(args.source):
            if args.cmd in ("discover", "sync"):
                discover(settings, client, store, source)
            if args.cmd in ("download", "sync"):
                _, err = download(client, store, source, since=args.since, limit=args.limit, force=args.force)
                failures += err
            if args.cmd == "sync":
                failures += extract(store, source, since=args.since)[1]
                structure(store, source)
                if source.doc_type == "comunicado_pm":
                    report(store, source)
        return 1 if failures else 0
    finally:
        store.close()


def _reactions(store: Store, args: argparse.Namespace) -> int:
    rows = store.market_reactions(args.since)
    if not rows:
        print("Sem reações. Rode `banxico market` (requer data/TIIE).")
        return 1

    def f(v, w=6):
        return f"{v:+{w}.1f}" if v is not None else " " * (w - 1) + "—"

    print(f"{'data':<10} {'fam':<6} {'decisão':<13} {'surpr':>6} {'via':<3} {'prec.':>6} {'Δ1y':>6} {'Δ2y':>6} "
          f"{'Δ10y':>6} {'1s2s':>6} {'2s5s':>6} {'2s10s':>6} {'UST2y':>6}  avisos")
    for r in rows:
        d1 = json.loads(r["d1"]) if r["d1"] else {}
        ust = json.loads(r["ust_d1"]) if r["ust_d1"] else {}
        act = {"hike": "↑", "cut": "↓", "hold": "="}.get(r["action"], "?")
        dec = f"{act} {r['change_bp'] or 0}pb {r['rate'] or '':}" if r["rate"] is not None else act
        flags = "; ".join(json.loads(r["flags"])) if r["flags"] else ""
        sl = slopes(d1)
        print(f"{r['doc_date']} {r['family']:<6} {dec:<13} {f(r['surprise_bp'])} {r['surprise_tenor'] or '':<3} "
              f"{f(r['priced_bp'])} {f(d1.get('1y'))} {f(d1.get('2y'))} {f(d1.get('10y'))} "
              f"{f(sl['1s2s'])} {f(sl['2s5s'])} {f(sl['2s10s'])} "
              f"{f(ust.get('2y'))}  {flags[:70]}")
    return 0


def _open(path) -> None:
    """Abre o arquivo no navegador padrão."""
    import os
    import webbrowser

    if hasattr(os, "startfile"):
        os.startfile(path)  # Windows
    else:
        webbrowser.open(path.as_uri())


def _show(store: Store, args: argparse.Namespace) -> int:
    rows = [store.get(args.date)] if ":" in args.date else store.find(args.source, args.date)
    rows = [r for r in rows if r is not None]
    if not rows:
        print(f"Nenhum documento para {args.date!r} em {args.source}.")
        return 1
    if len(rows) > 1:
        for r in rows:
            print(f"{r['doc_date']}  {r['id']}  {r['title']}")
        return 0
    doc = rows[0]
    segs = store.segments(doc["id"])
    if not segs:
        print("Documento ainda não extraído. Rode `banxico extract`.")
        return 1
    print(f"{doc['doc_date']} — {doc['title']}")
    print(doc["url"], end="\n\n")
    for s in segs:
        if not args.all and s["kind"] not in ("paragraph", "heading"):
            continue
        tag = s["section"] if s["kind"] == "paragraph" else s["kind"]
        print(f"[{s['seq']:>2}] ({tag})")
        print(s["text"], end="\n\n")
    return 0


_ARROW = {"hike": "↑", "cut": "↓", "hold": "="}
_BIAS = {"up": "alta", "down": "baixa", "balanced": "equil.", "uncertain": "incerto"}


def _decisions(store: Store, args: argparse.Namespace) -> int:
    import json

    rows = store.decisions(args.since)
    if not rows:
        print("Sem decisões. Rode `banxico structure`.")
        return 1
    print(f"{'data':<10}  {'decisão':<16} {'nível':>8}  {'voto':<6} {'riscos infl.':<20} dissidência")
    for r in rows:
        if r["instrument"] == "tasa":
            move = f"{_ARROW.get(r['action'], '?')} {r['change_bp'] or 0}pb" if r["action"] != "hold" else "= mantém"
            level = f"{r['rate']:.2f}%" if r["rate"] is not None else "?"
        else:
            move = f"{_ARROW.get(r['action'], '?')} corto" + (f" {r['change_bp']}pb" if r["change_bp"] else "")
            level = f"{r['corto_mn']} mi" if r["corto_mn"] is not None else "?"
        vote = {"unanimous": "unân.", "majority": f"{r['n_for']}x{r['n_against']}" if r["n_for"] else "maior."}.get(
            r["vote_type"], "")
        risk = " / ".join(filter(None, [_BIAS.get(r["infl_bias"]), {"improved": "melhorou",
                          "deteriorated": "piorou", "unchanged": "s/ mudança"}.get(r["infl_change"])]))
        flag = "  ⚠" if r["n_warnings"] else ""
        extra = " (extraord.)" if r["extraordinary"] else ""
        print(f"{r['doc_date']}  {move + extra:<16} {level:>8}  {vote:<6} {risk:<20} {r['dissent_summary'] or ''}{flag}")
        if args.checks and r["checks"]:
            for c in json.loads(r["checks"]):
                print(f"{'':12}- {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
