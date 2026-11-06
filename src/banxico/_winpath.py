r"""Contorno para venv em drive de rede no Windows.

Quando o projeto está num drive mapeado (ex.: G: -> \\servidor\share), os
launchers .exe do venv (`banxico.exe`, `pytest.exe`) resolvem o caminho para a
forma estendida `\\?\UNC\servidor\share\...`. O Windows recusa carregar DLLs de
extensões nativas (ex.: PyMuPDF) a partir desse prefixo ("Parâmetro incorreto").
Normalizar sys.path para `\\servidor\share\...` resolve.
"""

from __future__ import annotations

import sys

_EXTENDED_UNC = "\\\\?\\UNC\\"
_EXTENDED = "\\\\?\\"


def _normalize(path: str) -> str:
    if path.startswith(_EXTENDED_UNC):
        return "\\\\" + path[len(_EXTENDED_UNC):]
    if path.startswith(_EXTENDED):
        return path[len(_EXTENDED):]
    return path


def fix_sys_path() -> None:
    if sys.platform == "win32":
        sys.path[:] = [_normalize(p) for p in sys.path]
