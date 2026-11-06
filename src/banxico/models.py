"""Modelos de dados compartilhados entre fontes, storage e pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DocumentRef:
    """Documento descoberto numa página de listagem (ainda não baixado)."""

    source: str          # id da fonte em sources.toml (ex.: "comunicados")
    doc_type: str        # tipo lógico (ex.: "comunicado_pm", "minuta_pm")
    language: str        # "es" | "en"
    date: date           # data de referência publicada pelo Banxico
    title: str           # resumo/título exibido na listagem
    url: str             # URL absoluta do arquivo
    remote_id: str       # identificador estável no site (GUID do CMS)

    @property
    def doc_id(self) -> str:
        return f"{self.source}:{self.remote_id}"

    @property
    def extension(self) -> str:
        tail = self.url.rsplit("/", 1)[-1]
        return tail.rsplit(".", 1)[-1].lower() if "." in tail else "bin"
