"""Alinhamento monotônico (preserva a ordem) entre duas sequências, por programação dinâmica.

Usado em dois níveis: parágrafos (com bônus por mesma seção) e frases dentro de um par de
parágrafos. Itens sem par viram inserção/remoção.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from difflib import SequenceMatcher

_WORD = re.compile(r"\w+", re.UNICODE)


def words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def similarity(a: str, b: str) -> float:
    """Razão de similaridade por palavras (0–1), robusta a pontuação/espacos."""
    wa, wb = words(a), words(b)
    if not wa and not wb:
        return 1.0
    return SequenceMatcher(None, wa, wb, autojunk=False).ratio()


def align(
    a: Sequence, b: Sequence, score: Callable[[int, int], float], threshold: float
) -> list[tuple[int | None, int | None]]:
    """Retorna pares (i, j) em ordem; (i, None) = removido de a, (None, j) = novo em b.

    Maximiza a soma dos scores dos pares aceitos (score >= threshold), sem cruzamentos.
    """
    n, m = len(a), len(b)
    s = [[score(i, j) for j in range(m)] for i in range(n)]
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best = max(dp[i + 1][j], dp[i][j + 1])
            if s[i][j] >= threshold:
                best = max(best, s[i][j] + dp[i + 1][j + 1])
            dp[i][j] = best

    out: list[tuple[int | None, int | None]] = []
    i = j = 0
    while i < n and j < m:
        if s[i][j] >= threshold and abs(dp[i][j] - (s[i][j] + dp[i + 1][j + 1])) < 1e-12:
            out.append((i, j))
            i += 1
            j += 1
        elif abs(dp[i][j] - dp[i + 1][j]) < 1e-12:
            out.append((i, None))
            i += 1
        else:
            out.append((None, j))
            j += 1
    out.extend((k, None) for k in range(i, n))
    out.extend((None, k) for k in range(j, m))
    return out
