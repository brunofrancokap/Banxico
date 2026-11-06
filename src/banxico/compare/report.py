"""Relatório HTML autocontido: comunicado t vs t-1 (cabeçalho estruturado + redline)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from html import escape

from ..text.render import SECTION_LABELS
from .diff import DocDiff, ParagraphDiff

ACTION_PT = {"hike": "alta", "cut": "corte", "hold": "manutenção"}
ARROW = {"hike": "▲", "cut": "▼", "hold": "="}
BIAS_PT = {"up": "altista", "down": "baixista", "balanced": "equilibrado", "uncertain": "incerto"}
CHANGE_PT = {"improved": "melhorou", "deteriorated": "piorou", "unchanged": "sem mudança"}
STATUS_PT = {"unchanged": "sem mudança", "modified": "alterado", "added": "novo", "removed": "removido"}
SERIES_PT = {"headline_yoy": "Inflação geral (a/a)", "core_yoy": "Inflação subjacente (a/a)"}

CSS = """
:root{--fg:#1f2937;--muted:#6b7280;--line:#e5e7eb;--bg:#fff;--soft:#f9fafb;
--del-fg:#991b1b;--del-bg:#fee2e2;--ins-fg:#166534;--ins-bg:#dcfce7;--accent:#1d4ed8}
*{box-sizing:border-box}body{font:15px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
color:var(--fg);background:var(--bg);margin:0}
main{max-width:1040px;margin:0 auto;padding:28px 24px 80px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
h1{font-size:22px;margin:4px 0 2px}h2{font-size:16px;margin:32px 0 10px;text-transform:uppercase;
letter-spacing:.04em;color:var(--muted)}
.sub{color:var(--muted);font-size:13px}.nav{display:flex;justify-content:space-between;font-size:13px;margin-bottom:14px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:18px}
.card{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--soft)}
.card .k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.card .v{font-size:19px;font-weight:600;margin-top:2px}.card .p{font-size:13px;color:var(--muted)}
.card.changed{border-color:#f59e0b;background:#fffbeb}
.chg{display:inline-block;font-size:11px;font-weight:600;color:#92400e;background:#fde68a;border-radius:4px;padding:0 5px;margin-left:6px;vertical-align:2px}
table.fc{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
table.fc th,table.fc td{border-bottom:1px solid var(--line);padding:4px 6px;text-align:right;white-space:nowrap}
table.fc th:first-child,table.fc td:first-child{text-align:left}
table.fc tr.delta td{font-weight:600}.up{color:#b91c1c}.down{color:#1d4ed8}.zero{color:#9ca3af;font-weight:400}
.fcwrap{overflow-x:auto}
.toolbar{position:sticky;top:0;background:rgba(255,255,255,.95);border-bottom:1px solid var(--line);
padding:8px 0;margin-top:8px;font-size:13px;display:flex;gap:18px;align-items:center;z-index:2}
.legend del,.legend ins{padding:0 4px}
.para{display:grid;grid-template-columns:150px 1fr;gap:14px;padding:14px 0;border-top:1px solid var(--line)}
.meta{font-size:12px;color:var(--muted)}.sec{font-weight:600;color:var(--fg);display:block}
.badge{display:inline-block;border-radius:4px;padding:0 6px;font-size:11px;font-weight:600;margin-top:4px}
.b-modified{background:#fef3c7;color:#92400e}.b-added{background:var(--ins-bg);color:var(--ins-fg)}
.b-removed{background:var(--del-bg);color:var(--del-fg)}.b-unchanged{background:#f3f4f6;color:var(--muted)}
.sim{display:block;margin-top:4px}
del{color:var(--del-fg);background:var(--del-bg);text-decoration:line-through;text-decoration-thickness:1px;border-radius:2px}
ins{color:var(--ins-fg);background:var(--ins-bg);text-decoration:none;border-radius:2px}
.s-removed,.s-added{display:block;margin:4px 0;padding:2px 6px;border-radius:4px}
.s-removed{border-left:3px solid #f87171}.s-added{border-left:3px solid #4ade80}
.s-removed del,.s-added ins{background:none}
.para.unchanged .body{color:var(--muted)}
body.hide-unchanged .para.unchanged{display:none}
.text{font-family:Georgia,'Times New Roman',serif;font-size:16px}
.evidence{font-size:12px;color:var(--muted);font-style:italic;margin-top:4px}
footer{margin-top:40px;font-size:12px;color:var(--muted)}
table.idx{border-collapse:collapse;width:100%;font-size:14px}
table.idx td,table.idx th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left}
table.idx td.n{text-align:right;font-variant-numeric:tabular-nums}
.bar{display:inline-block;height:8px;background:#93c5fd;border-radius:2px;vertical-align:middle}
"""

JS = """
const cb=document.getElementById('hideUnchanged');
if(cb){const apply=()=>document.body.classList.toggle('hide-unchanged',cb.checked);cb.addEventListener('change',apply);apply();}
"""


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}%".replace(".", ",")


def _date_br(iso: str | None) -> str:
    return "—" if not iso else f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def describe_decision(d: Mapping | None) -> tuple[str, str]:
    """(linha principal, detalhe) para um registro de `decisions`."""
    if not d:
        return "—", ""
    act = d["action"]
    if d["instrument"] == "tasa":
        if act == "hold":
            return f"= mantém em {_pct(d['rate'])}", "tasa objetivo"
        return f"{ARROW.get(act, '?')} {d['change_bp'] or '?'} pb → {_pct(d['rate'])}", "tasa objetivo"
    move = {"hike": "aperto", "cut": "relaxamento", "hold": "sem mudança"}.get(act, "?")
    bp = f" {d['change_bp']} pb" if d["change_bp"] else ""
    corto = f"corto {d['corto_mn']} mi" if d["corto_mn"] is not None else "corto"
    return f"{ARROW.get(act, '?')} {move}{bp}", corto


def describe_vote(d: Mapping | None) -> tuple[str, str]:
    if not d or not d["vote_type"]:
        return "não informado", ""
    if d["vote_type"] == "unanimous":
        return "unânime", ""
    head = f"{d['n_for']} × {d['n_against']}" if d["n_for"] else "por maioria"
    if not d["dissents"]:
        return head, ""
    verbs = {"hold": "manter", "cut": "cortar", "hike": "subir"}
    parts = []
    for x in json.loads(d["dissents"]):
        pref = verbs.get(x["action"], "?") + (f" {x['change_bp']} pb" if x.get("change_bp") else "")
        parts.append(f"{x['name']} ({pref})")
    return head, "dissidência: " + "; ".join(parts)


def describe_risk(d: Mapping | None, prefix: str) -> tuple[str, str]:
    if not d:
        return "—", ""
    bias, change = d[f"{prefix}_bias"], d[f"{prefix}_change"]
    main = BIAS_PT.get(bias, "não informado")
    return main, CHANGE_PT.get(change, "")


def _card(label: str, new: tuple[str, str], old: tuple[str, str], changed: bool, extra: str = "") -> str:
    tag = '<span class="chg">mudou</span>' if changed else ""
    detail = f'<div class="p">{escape(new[1])}</div>' if new[1] else ""
    return (f'<div class="card{" changed" if changed else ""}"><div class="k">{escape(label)}{tag}</div>'
            f'<div class="v">{escape(new[0])}</div>{detail}'
            f'<div class="p">antes: {escape(old[0])}{(" · " + escape(old[1])) if old[1] else ""}</div>{extra}</div>')


def _forecast_table(new_fc: Sequence[Mapping], old_fc: Sequence[Mapping], new_date: str, old_date: str) -> str:
    if not new_fc:
        return ""
    blocks: list[str] = []
    header = ""
    for series, label in SERIES_PT.items():
        cur = {r["period"]: r["value"] for r in new_fc if r["series"] == series and r["vintage"] == "actual"}
        if not cur:
            continue
        prev = {r["period"]: r["value"] for r in old_fc if r["series"] == series and r["vintage"] == "actual"}
        prev_label = _date_br(old_date)
        if not prev:  # reunião anterior sem quadro: usar a vintage "Anterior" do próprio comunicado
            ant = [r for r in new_fc if r["series"] == series and r["vintage"] == "anterior"]
            prev = {r["period"]: r["value"] for r in ant}
            prev_label = _date_br(ant[0]["vintage_date"]) if ant else "—"
        periods = sorted(cur)
        head = "".join(f"<th>{p[-1]}T{p[2:4]}</th>" for p in periods)   # 2026Q4 -> 4T26

        def cells(values: Mapping[str, float]) -> str:
            return "".join(f"<td>{'' if values.get(p) is None else f'{values[p]:.1f}'.replace('.', ',')}</td>"
                           for p in periods)

        deltas = []
        for p in periods:
            if p in prev:
                dv = round(cur[p] - prev[p], 2)
                cls = "up" if dv > 0 else "down" if dv < 0 else "zero"
                deltas.append(f'<td class="{cls}">{"" if dv == 0 else ("+" if dv > 0 else "")}'
                              f'{"0" if dv == 0 else f"{dv:.1f}".replace(".", ",")}</td>')
            else:
                deltas.append("<td></td>")
        blocks.append(
            f'<tr><th colspan="{len(periods) + 1}" style="text-align:left;padding-top:10px">{escape(label)}</th></tr>'
            f'<tr><td>Atual ({_date_br(new_date)})</td>{cells(cur)}</tr>'
            f'<tr><td>Anterior ({prev_label})</td>{cells(prev)}</tr>'
            f'<tr class="delta"><td>Δ (p.p.)</td>{"".join(deltas)}</tr>'
        )
        header = f"<tr><th>trimestre</th>{head}</tr>"
    if not blocks:
        return ""
    return (f'<h2>Pronósticos de inflação</h2><div class="fcwrap"><table class="fc">{header}'
            f'{"".join(blocks)}</table></div>')


def _render_ops(p: ParagraphDiff) -> str:
    out = []
    for s in p.sentences:
        inner = "".join(
            f"<del>{escape(o.text)}</del>" if o.kind == "delete"
            else f"<ins>{escape(o.text)}</ins>" if o.kind == "insert"
            else escape(o.text)
            for o in s.ops
        )
        if s.status in ("added", "removed") and p.status == "modified":
            out.append(f'<span class="s-{s.status}">{inner}</span>')
        else:
            out.append(inner + " ")
    return "".join(out)


def _paragraph(p: ParagraphDiff) -> str:
    sec = SECTION_LABELS.get(p.section or "other", p.section or "")
    sim = f'<span class="sim">similaridade {p.similarity:.0%}</span>' if p.status == "modified" else ""
    return (f'<div class="para {p.status}"><div class="meta"><span class="sec">{escape(sec)}</span>'
            f'<span class="badge b-{p.status}">{STATUS_PT[p.status]}</span>{sim}</div>'
            f'<div class="body text">{_render_ops(p)}</div></div>')


def render_report(
    new_doc: Mapping, old_doc: Mapping, diff: DocDiff,
    new_dec: Mapping | None, old_dec: Mapping | None,
    new_fc: Sequence[Mapping], old_fc: Sequence[Mapping],
    nav: Mapping[str, str | None],
) -> str:
    nd, od = describe_decision(new_dec), describe_decision(old_dec)
    nv, ov = describe_vote(new_dec), describe_vote(old_dec)
    ni, oi = describe_risk(new_dec, "infl"), describe_risk(old_dec, "infl")
    ng, og = describe_risk(new_dec, "growth"), describe_risk(old_dec, "growth")
    ev = new_dec["infl_evidence"] if new_dec and new_dec["infl_evidence"] else ""
    c = diff.counts
    text_card = (
        f'<div class="card"><div class="k">Texto</div><div class="v">{diff.change_ratio:.0%} alterado</div>'
        f'<div class="p">{c["added"]} frases novas · {c["removed"]} removidas · {c["modified"]} editadas · '
        f'{c["unchanged"]} iguais</div></div>'
    )
    extra = " · reunião extraordinária" if new_dec and new_dec["extraordinary"] else ""
    cards = "".join([
        _card("Decisão", nd, od, nd != od),
        _card("Votação", nv, ov, nv != ov),
        _card("Riscos p/ inflação", ni, oi, ni[0] != oi[0],
              f'<div class="evidence">“{escape(ev[:220])}”</div>' if ev and ni[0] != oi[0] else ""),
        _card("Riscos p/ crescimento", ng, og, ng[0] != og[0]),
        text_card,
    ])
    prev_link = f'<a href="{escape(nav["prev"])}">← reunião anterior</a>' if nav.get("prev") else ""
    next_link = f'<a href="{escape(nav["next"])}">próxima reunião →</a>' if nav.get("next") else ""
    nav_html = f'<div class="nav"><span>{prev_link}</span><a href="index.html">índice</a><span>{next_link}</span></div>'
    body = "".join(_paragraph(p) for p in diff.paragraphs)
    title = f"Banxico · {_date_br(new_doc['doc_date'])} vs {_date_br(old_doc['doc_date'])}"
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{CSS}</style></head>
<body class="hide-unchanged"><main>
{nav_html}
<div class="sub">Comunicado de política monetária{extra}</div>
<h1>{_date_br(new_doc['doc_date'])} <span style="color:var(--muted);font-weight:400">vs</span> {_date_br(old_doc['doc_date'])}</h1>
<div class="sub">{escape(new_doc['title'] or '')}</div>
<div class="sub" style="margin-top:4px"><a href="{escape(new_doc['url'])}">PDF {_date_br(new_doc['doc_date'])}</a> ·
<a href="{escape(old_doc['url'])}">PDF {_date_br(old_doc['doc_date'])}</a></div>
<div class="cards">{cards}</div>
{_forecast_table(new_fc, old_fc, new_doc['doc_date'], old_doc['doc_date'])}
<h2>Texto</h2>
<div class="toolbar"><label><input type="checkbox" id="hideUnchanged" checked> ocultar parágrafos sem mudança</label>
<span class="legend"><del>removido</del> <ins>incluído</ins></span></div>
{body}
<footer>Gerado por banxico · seções são rótulos heurísticos · fonte: banxico.org.mx</footer>
</main><script>{JS}</script></body></html>"""


def render_index(rows: Sequence[Mapping]) -> str:
    """rows: dicts com date, prev_date, file, decision, vote, change_ratio, flags."""
    trs = []
    for r in rows:
        w = int(round(r["change_ratio"] * 120))
        trs.append(
            f'<tr><td><a href="{escape(r["file"])}">{_date_br(r["date"])}</a></td>'
            f'<td class="sub">{_date_br(r["prev_date"])}</td><td>{escape(r["decision"])}</td>'
            f'<td>{escape(r["vote"])}</td>'
            f'<td class="n">{r["change_ratio"]:.0%} <span class="bar" style="width:{w}px"></span></td>'
            f'<td class="sub">{escape(r["flags"])}</td></tr>'
        )
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Banxico · comparações de comunicados</title><style>{CSS}</style></head>
<body><main><h1>Comunicados de política monetária: comparações</h1>
<div class="sub">Cada linha compara o comunicado com o da reunião anterior. {len(rows)} relatórios.</div>
<table class="idx" style="margin-top:18px"><tr><th>reunião</th><th>vs</th><th>decisão</th><th>votação</th>
<th style="text-align:right">texto alterado</th><th></th></tr>{"".join(trs)}</table>
<footer>Gerado por banxico · fonte: banxico.org.mx</footer></main></body></html>"""


def decision_summary(d: Mapping | None) -> str:
    main, detail = describe_decision(d)
    return main if not detail or detail == "tasa objetivo" else f"{main} ({detail})"


def flags(d: Mapping | None) -> str:
    if not d:
        return ""
    out = []
    if d["extraordinary"]:
        out.append("extraordinária")
    if d["n_warnings"]:
        out.append("⚠ " + "; ".join(c for c in json.loads(d["checks"] or "[]") if not c.startswith("info"))[:80])
    return " · ".join(out)
