"""Registro de parsers de listagem.

Cada parser recebe o HTML da página de listagem + a config da fonte e devolve
uma lista de DocumentRef. Para suportar um layout novo, crie um módulo aqui e
registre a função em PARSERS; depois aponte `parser = "<nome>"` em sources.toml.
"""

from __future__ import annotations

from typing import Callable

from ..config import SourceConfig
from ..models import DocumentRef
from .banxico_table import parse_banxico_table

ListingParser = Callable[[str, SourceConfig, str], list[DocumentRef]]

PARSERS: dict[str, ListingParser] = {
    "banxico_table": parse_banxico_table,
}


def get_parser(name: str) -> ListingParser:
    try:
        return PARSERS[name]
    except KeyError:
        raise SystemExit(f"Parser '{name}' não registrado. Disponíveis: {list(PARSERS)}") from None
