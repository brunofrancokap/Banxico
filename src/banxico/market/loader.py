"""Carga dos dados de mercado (Bloomberg) de data/TIIE/ para a tabela `market_quotes`.

Arquivos e o que cada um realmente contém (verificado em 2026-11):

  MPSW.csv              swaps de TIIE 28 (família "tiie28"), 2007-04 → 2024-12-31, 3m..30a.
                        `;` como separador, vírgula decimal, datas dd/mm/aaaa.
  MPSWF_combined.csv    série "emendada" pelo usuário. ANTES de 2025 é TIIE 28 menos um spread
                        FIXO por prazo (−23,5 a −30 pb): níveis artificiais, variações iguais às
                        da TIIE 28. A partir de 2025-01-01 é TIIE de Fondeo (OIS) de verdade; a
                        coluna 1m é Fondeo real desde 2024-12-19. Só usamos a parte real.
  MPSWF_AAAAMMDD.csv    snapshots diários (janela móvel de ~9 dias). Bloco 1: Fondeo (MPSWF...);
                        bloco 2: Treasuries (USGG...). Arquivo mais recente prevalece por data.

ATENÇÃO aos tickers: na família TIIE 28, "MPSWF" é o swap de 6 MESES (MPSW + sufixo F). A família
é decidida pelo arquivo, nunca pelo prefixo do ticker.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Data da emenda TIIE 28 -> Fondeo. Nenhuma comparação de nível ou variação pode atravessá-la.
SPLICE_DATE = "2025-01-01"
FONDEO_1M_SINCE = "2024-12-19"

# Sufixo Bloomberg (períodos) -> prazo
SUFFIX_TENOR = {
    "A": "1m", "C": "3m", "F": "6m", "I": "9m", "1A": "1y", "2B": "2y", "3C": "3y", "4D": "4y",
    "5E": "5y", "7G": "7y", "10J": "10y", "16C": "15y", "21H": "20y", "32F": "30y",
}
UST_TENOR = {
    "3M": "3m", "6M": "6m", "12M": "1y", "2YR": "2y", "3YR": "3y", "5YR": "5y", "7YR": "7y",
    "10YR": "10y", "20YR": "20y", "30YR": "30y",
}
TENOR_MONTHS = {"1m": 1, "3m": 3, "6m": 6, "9m": 9, "1y": 12, "2y": 24, "3y": 36, "4y": 48, "5y": 60,
                "7y": 84, "10y": 120, "15y": 180, "20y": 240, "30y": 360}
FAMILIES = {
    "tiie28": "Swap TIIE 28 dias (IRS), Bloomberg MPSW*",
    "fondeo": "Swap TIIE de Fondeo (OIS), Bloomberg MPSWF*",
    "ust": "Treasuries EUA (Bloomberg USGG*), só nos snapshots diários",
}


@dataclass(frozen=True)
class Quote:
    series: str      # ex.: "fondeo_1m", "tiie28_2y", "ust_10y"
    date: str        # ISO
    value: float     # % a.a.
    source: str      # arquivo de origem


def _iso(dmy: str) -> str:
    d, m, y = dmy.strip().split("/")
    return f"{y}-{int(m):02d}-{int(d):02d}"


def _num(s: str) -> float | None:
    s = s.strip().replace(",", ".")
    return float(s) if s else None


def _tenor(ticker: str, prefix: str) -> str | None:
    """'MPSW2B CURNCY' com prefixo 'MPSW' -> '2y'."""
    code = ticker.split()[0]
    if not code.startswith(prefix):
        return None
    return SUFFIX_TENOR.get(code[len(prefix):])


def read_tiie28(path: Path) -> list[Quote]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    header = lines[0].split(";")
    tenors = [_tenor(h, "MPSW") for h in header[1:]]
    out = []
    for ln in lines[1:]:
        parts = ln.split(";")
        if not parts[0].strip():
            continue
        day = _iso(parts[0])
        for ten, raw in zip(tenors, parts[1:]):
            if ten and (v := _num(raw)) is not None:
                out.append(Quote(f"tiie28_{ten}", day, v, path.name))
    return out


def read_combined_fondeo(path: Path) -> list[Quote]:
    """Só a parte real (Fondeo) do arquivo emendado."""
    out = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            day = row["date"]
            for ten, raw in row.items():
                if ten == "date" or not raw:
                    continue
                real = day >= SPLICE_DATE or (ten == "1m" and day >= FONDEO_1M_SINCE)
                if real and ten in TENOR_MONTHS:
                    out.append(Quote(f"fondeo_{ten}", day, round(float(raw), 6), path.name))
    return out


def read_daily(path: Path) -> list[Quote]:
    """Snapshot diário com dois blocos (Fondeo e Treasuries), cada um com seu cabeçalho."""
    out, header, family = [], None, None
    for ln in path.read_text(encoding="utf-8-sig").splitlines():
        parts = ln.split(";")
        if parts[0].strip().lower() == "date":
            header = parts[1:]
            first = header[0].split()[0] if header and header[0] else ""
            family = "fondeo" if first.startswith("MPSWF") else "ust" if first.startswith("USGG") else None
            continue
        if not header or not family or not parts[0].strip():
            continue
        day = _iso(parts[0])
        for h, raw in zip(header, parts[1:]):
            if not h.strip():
                continue
            code = h.split()[0]
            ten = _tenor(h, "MPSWF") if family == "fondeo" else UST_TENOR.get(code.removeprefix("USGG"))
            if ten and (v := _num(raw)) is not None:
                out.append(Quote(f"{family}_{ten}", day, v, path.name))
    return out


def load_folder(folder: Path) -> tuple[list[Quote], list[str]]:
    """Lê tudo da pasta. Ordem de prioridade (o último vence por série/data):
    MPSW.csv < MPSWF_combined.csv < snapshots diários (em ordem cronológica de arquivo)."""
    notes: list[str] = []
    quotes: dict[tuple[str, str], Quote] = {}

    def add(qs: list[Quote]) -> None:
        for q in qs:
            quotes[(q.series, q.date)] = q

    if (p := folder / "MPSW.csv").exists():
        add(read_tiie28(p))
    else:
        notes.append("MPSW.csv ausente: sem histórico de TIIE 28 (reações antes de 2025 indisponíveis)")
    if (p := folder / "MPSWF_combined.csv").exists():
        add(read_combined_fondeo(p))
    dailies = sorted(folder.glob("MPSWF_2*.csv"), key=lambda p: re.sub(r"\D", "", p.stem))
    for p in dailies:
        add(read_daily(p))
    notes.append(f"{len(dailies)} snapshot(s) diário(s) lidos")
    return list(quotes.values()), notes
