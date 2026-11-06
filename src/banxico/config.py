"""Caminhos do projeto e carregamento da configuração (config/sources.toml)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.environ.get("BANXICO_CONFIG", PROJECT_ROOT / "config" / "sources.toml"))
DATA_DIR = Path(os.environ.get("BANXICO_DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "banxico.db"
# Dados de mercado (Bloomberg) fornecidos pelo usuário; fora do git por licença.
MARKET_DIR = Path(os.environ.get("BANXICO_MARKET_DIR", DATA_DIR / "TIIE"))


@dataclass(frozen=True)
class HttpConfig:
    base_url: str
    user_agent: str
    timeout_seconds: float = 30
    delay_seconds: float = 1.0
    max_retries: int = 3


@dataclass(frozen=True)
class SourceConfig:
    id: str
    name: str
    doc_type: str
    language: str
    parser: str
    listing_url: str
    enabled: bool = True


@dataclass(frozen=True)
class Settings:
    http: HttpConfig
    sources: dict[str, SourceConfig]

    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources.values() if s.enabled]

    def resolve(self, ids: list[str] | None) -> list[SourceConfig]:
        """Retorna as fontes pedidas (ou todas as habilitadas se `ids` for vazio)."""
        if not ids:
            return self.enabled_sources()
        unknown = [i for i in ids if i not in self.sources]
        if unknown:
            raise SystemExit(f"Fonte(s) desconhecida(s): {unknown}. Disponíveis: {list(self.sources)}")
        return [self.sources[i] for i in ids]


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    http = HttpConfig(**raw["http"])
    sources = {sid: SourceConfig(id=sid, **cfg) for sid, cfg in raw.get("sources", {}).items()}
    return Settings(http=http, sources=sources)
