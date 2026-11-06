"""Validações ao longo da série de reuniões (precisam da reunião anterior).

1. Continuidade da taxa: rate_t - rate_{t-1} deve bater com ação/pb informados.
   Quando o PDF não informa os pb (ex.: "incrementar a 8.00 por ciento"), eles são derivados.
2. Pronósticos: a vintage "Anterior" do comunicado t deve repetir a "Actual" do comunicado t-1.
"""

from __future__ import annotations

from .forecasts import ForecastPoint
from . import MeetingRecord

_SIGN = {"hike": 1, "cut": -1, "hold": 0}


def validate_series(records: list[MeetingRecord]) -> None:
    """Muta os registros: preenche change_bp derivado e acrescenta avisos em `checks`."""
    records = sorted(records, key=lambda r: r.doc_date)
    prev_rate: float | None = None
    prev_actual: dict[tuple[str, str], float] = {}
    prev_date: str | None = None

    prev_corto: int | None = None
    for rec in records:
        d = rec.decision
        if d.instrument == "corto":
            if d.corto_mn is None and d.action == "hold" and prev_corto is not None:
                d.corto_mn = prev_corto
                rec.checks.append(f"info: corto não citado; mantido do anterior ({prev_corto} mi)")
            prev_corto = d.corto_mn if d.corto_mn is not None else prev_corto
        if d.instrument == "tasa" and d.rate is not None:
            if prev_rate is not None:
                delta = round((d.rate - prev_rate) * 100)
                if d.change_bp is None and d.action in _SIGN:
                    d.change_bp = abs(delta)
                    rec.checks.append(f"info: pb derivados da taxa anterior ({prev_rate}% -> {d.rate}%)")
                elif d.action in _SIGN and d.change_bp is not None and delta != _SIGN[d.action] * d.change_bp:
                    rec.checks.append(
                        f"série: taxa anterior {prev_rate}% -> {d.rate}% (Δ {delta}pb) "
                        f"não bate com {d.action} {d.change_bp}pb"
                    )
            prev_rate = d.rate

        if rec.forecasts:
            anterior = {(p.series, p.period): p for p in rec.forecasts if p.vintage == "anterior"}
            if prev_actual and anterior:
                diffs = [
                    f"{s} {per}: {prev_actual[(s, per)]} vs {p.value}"
                    for (s, per), p in anterior.items()
                    if (s, per) in prev_actual and abs(prev_actual[(s, per)] - p.value) > 1e-9
                ]
                if diffs:
                    rec.checks.append(f"pronósticos: 'Anterior' difere da 'Actual' de {prev_date} "
                                      f"em {len(diffs)} ponto(s), ex.: {diffs[0]}")
                vdates = {p.vintage_date for p in anterior.values()}
                if prev_date not in vdates:
                    # Normal quando o Banxico revisa pronósticos no Informe Trimestral entre reuniões
                    rec.checks.append(f"info: 'Anterior' datada {sorted(filter(None, vdates))} "
                                      f"(reunião anterior com quadro: {prev_date})")
            prev_actual = {(p.series, p.period): p.value for p in rec.forecasts if p.vintage == "actual"}
            prev_date = rec.doc_date


def forecast_rows(rec: MeetingRecord) -> list[tuple]:
    return [(rec.document_id, p.vintage, p.vintage_date, p.series, p.period, p.value) for p in rec.forecasts]


__all__ = ["validate_series", "forecast_rows", "ForecastPoint"]
