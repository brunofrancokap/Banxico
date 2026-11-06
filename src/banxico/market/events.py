"""Reação da curva a cada decisão de política monetária.

Janela padrão: fechamento do pregão anterior (t−1) -> fechamento do dia da decisão (t). O anúncio
sai às 13h (Cidade do México), antes do fechamento. Janela alternativa de 2 dias: t−1 -> t+1.

Métricas por reunião:
  surprise_bp    variação do prazo mais curto disponível no dia (1m Fondeo; antes, 3m TIIE 28,
                 que também carrega expectativa da reunião seguinte: aproximação mais ruidosa)
  priced_bp      (só era Fondeo) quanto a curva precificava: 1m(t−1) − tasa vigente, em pb
  surprise_level_bp  (só era Fondeo) variação efetiva − priced_bp
  path_bp        Δ1y − surpresa: mudança na trajetória esperada além da própria decisão
  slope_bp       Δ10y − Δ2y (inclinação 2s10s; demais inclinações via slopes())
  ust2y/ust10y   Δ dos Treasuries na mesma janela (controle; só quando há dados)

Regras por causa da emenda TIIE 28 -> Fondeo (2025-01-01):
  - decisões antes da emenda usam só tiie28_*, depois só fondeo_*;
  - nenhuma janela pode atravessar a data da emenda;
  - nível (priced/surprise_level) só na era Fondeo: o spread TIIE 28 − tasa variava no tempo.
"""

from __future__ import annotations

import bisect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .loader import SPLICE_DATE, TENOR_MONTHS

TENORS = ("1m", "3m", "6m", "1y", "2y", "3y", "5y", "10y", "30y")
SLOPES = (("1y", "2y"), ("2y", "5y"), ("2y", "10y"))   # (curto, longo): Δlongo − Δcurto


def slopes(d: Mapping[str, float]) -> dict[str, float | None]:
    """Inclinações em pb a partir das variações por prazo: {'1s2s': Δ2y − Δ1y, ...}."""
    out = {}
    for a, b in SLOPES:
        key = f"{a[:-1]}s{b[:-1]}s"
        out[key] = round(d[b] - d[a], 2) if a in d and b in d else None
    return out


@dataclass
class Reaction:
    document_id: str
    doc_date: str
    family: str
    prev_date: str | None = None
    next_date: str | None = None
    d1: dict[str, float] = field(default_factory=dict)     # tenor -> pb (t−1 -> t)
    d2: dict[str, float] = field(default_factory=dict)     # tenor -> pb (t−1 -> t+1)
    ust_d1: dict[str, float] = field(default_factory=dict)
    surprise_bp: float | None = None
    surprise_tenor: str | None = None
    priced_bp: float | None = None
    surprise_level_bp: float | None = None
    path_bp: float | None = None
    slope_bp: float | None = None
    flags: list[str] = field(default_factory=list)


class Curve:
    """Acesso a uma família de séries por data."""

    def __init__(self, quotes: Mapping[str, Mapping[str, float]]):
        self.q = quotes                                   # series -> {date: value}
        self.dates: dict[str, list[str]] = {s: sorted(v) for s, v in quotes.items()}

    def value(self, series: str, day: str) -> float | None:
        return self.q.get(series, {}).get(day)

    def prev_day(self, series: str, day: str) -> str | None:
        ds = self.dates.get(series, [])
        i = bisect.bisect_left(ds, day) - 1
        return ds[i] if i >= 0 else None

    def next_day(self, series: str, day: str) -> str | None:
        ds = self.dates.get(series, [])
        i = bisect.bisect_right(ds, day)
        return ds[i] if i < len(ds) else None


def _bp(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else round((b - a) * 100, 2)


SPIKE_BP = 15.0


def _shape_dev(curve: "Curve", series: str, day: str) -> float | None:
    """Desvio do prazo em relação à interpolação linear entre os prazos vizinhos da mesma família
    (no mesmo dia). Nas pontas, diferença para o único vizinho."""
    family, tenor = series.split("_", 1)
    order = sorted((m, t) for t, m in TENOR_MONTHS.items() if curve.value(f"{family}_{t}", day) is not None)
    names = [t for _, t in order]
    if tenor not in names or len(names) < 2:
        return None
    i = names.index(tenor)
    x = curve.value(series, day)
    if 0 < i < len(names) - 1:
        (m0, t0), (m1, t1), m = order[i - 1], order[i + 1], TENOR_MONTHS[tenor]
        v0, v1 = curve.value(f"{family}_{t0}", day), curve.value(f"{family}_{t1}", day)
        return x - (v0 + (v1 - v0) * (m - m0) / (m1 - m0))
    other = names[1] if i == 0 else names[-2]
    return x - curve.value(f"{family}_{other}", day)


def spike_score(curve: "Curve", series: str, day: str) -> float:
    """Tamanho (pb) do vai-e-volta da forma da curva no prazo; 0 se não houver reversão."""
    b, a = curve.prev_day(series, day), curve.next_day(series, day)
    if b is None or a is None:
        return 0.0
    devs = [_shape_dev(curve, series, x) for x in (b, day, a)]
    if None in devs:
        return 0.0
    up, down = (devs[1] - devs[0]) * 100, (devs[2] - devs[1]) * 100
    return min(abs(up), abs(down)) if up * down < 0 else 0.0


def is_bad_print(curve: "Curve", series: str, day: str) -> bool:
    """Spike neste prazo E maior que o dos prazos vizinhos: um print errado no 1y também distorce
    a interpolação do 2y; só o prazo com a maior anomalia é o culpado."""
    score = spike_score(curve, series, day)
    if score <= SPIKE_BP:
        return False
    family, tenor = series.split("_", 1)
    names = [t for t in sorted(TENOR_MONTHS, key=TENOR_MONTHS.get) if curve.value(f"{family}_{t}", day) is not None]
    if tenor not in names:
        return False
    i = names.index(tenor)
    neighbors = [names[j] for j in (i - 1, i + 1) if 0 <= j < len(names)]
    return all(score >= spike_score(curve, f"{family}_{n}", day) for n in neighbors)


def is_spike(curve: "Curve", series: str, day: str) -> bool:
    """Erro de cotação isolado: a FORMA da curva naquele prazo salta > SPIKE_BP e volta no pregão
    seguinte. Movimentos reais deslocam a curva toda (ex.: 2020-03-20, −35 a −48 pb em todos os
    prazos) e não disparam; um print errado só num prazo, sim (tiie28_1y em 2022-09-28 = 10.21
    entre 10.635 e 10.585, com 9m e 2y estáveis)."""
    b, a = curve.prev_day(series, day), curve.next_day(series, day)
    if b is None or a is None:
        return False
    devs = [_shape_dev(curve, series, x) for x in (b, day, a)]
    if None in devs:
        return False
    up, down = (devs[1] - devs[0]) * 100, (devs[2] - devs[1]) * 100
    return abs(up) > SPIKE_BP and abs(down) > SPIKE_BP and up * down < 0


def compute_reactions(curve: Curve, decisions: Sequence[Mapping]) -> list[Reaction]:
    out = []
    prev_rate: float | None = None
    for d in decisions:
        day = d["doc_date"]
        family = "tiie28" if day < SPLICE_DATE else "fondeo"
        anchor = f"{family}_2y"
        r = Reaction(d["document_id"], day, family)
        current_prev_rate = prev_rate
        if d["instrument"] == "tasa" and d["rate"] is not None:
            prev_rate = d["rate"]
        if anchor not in curve.q:
            r.flags.append(f"sem dados {family}")
            out.append(r)
            continue
        if curve.value(anchor, day) is None:
            r.flags.append("sem cotação no dia da decisão")
            out.append(r)
            continue
        r.prev_date = curve.prev_day(anchor, day)
        r.next_date = curve.next_day(anchor, day)
        if r.prev_date is None:
            r.flags.append("sem pregão anterior na série")
            out.append(r)
            continue
        # Cada família só tem dados do seu lado da emenda, então isto não deveria ocorrer;
        # a checagem explícita protege contra arquivos futuros que misturem as bases.
        if r.prev_date < SPLICE_DATE <= day:
            r.flags.append("janela atravessaria a emenda TIIE 28 -> Fondeo; descartada")
            out.append(r)
            continue
        if r.next_date and day < SPLICE_DATE <= r.next_date:
            r.next_date = None
            r.flags.append("janela de 2 dias atravessaria a emenda; só janela de 1 dia")

        for t in TENORS:
            s = f"{family}_{t}"
            bad = [x for x in (r.prev_date, day, r.next_date) if x and is_bad_print(curve, s, x)]
            if bad:
                r.flags.append(f"cotação isolada suspeita em {s} ({', '.join(bad)}): prazo descartado")
                continue
            a, b = curve.value(s, r.prev_date), curve.value(s, day)
            if (v := _bp(a, b)) is not None:
                r.d1[t] = v
            if r.next_date and (v2 := _bp(a, curve.value(s, r.next_date))) is not None:
                r.d2[t] = v2
            u = f"ust_{t}"
            if (uv := _bp(curve.value(u, r.prev_date), curve.value(u, day))) is not None:
                r.ust_d1[t] = uv

        # dia "parado" (feriado/stale): 3m, 2y e 10y idênticos ao pregão anterior
        if all(r.d1.get(t) == 0 for t in ("3m", "2y", "10y") if t in r.d1) and r.d1:
            r.flags.append("curva sem variação no dia (feriado ou dado não atualizado?)")

        for t in ("1m", "3m"):
            if t in r.d1:
                r.surprise_bp, r.surprise_tenor = r.d1[t], t
                break
        if r.surprise_tenor == "3m":
            r.flags.append("surpresa via 3m (contém expectativa da reunião seguinte)")
        if family == "fondeo" and current_prev_rate is not None:
            one_m = curve.value("fondeo_1m", r.prev_date)
            if one_m is not None:
                r.priced_bp = round((one_m - current_prev_rate) * 100, 1)
                actual = {"hike": 1, "cut": -1, "hold": 0}.get(d["action"], 0) * (d["change_bp"] or 0)
                r.surprise_level_bp = round(actual - r.priced_bp, 1)
        if r.surprise_bp is not None and "1y" in r.d1:
            r.path_bp = round(r.d1["1y"] - r.surprise_bp, 2)
        r.slope_bp = slopes(r.d1)["2s10s"]
        out.append(r)
    return out
