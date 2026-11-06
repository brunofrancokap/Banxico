"""Dados de mercado (swaps de TIIE 28 / TIIE de Fondeo, Treasuries) e reação às decisões.

`banxico market` carrega os arquivos de data/TIIE e recalcula as reações; ver loader.py para o
que cada arquivo contém e o tratamento da emenda TIIE 28 -> Fondeo (2025-01-01).
"""

from .events import Curve, Reaction, compute_reactions, slopes
from .loader import FAMILIES, SPLICE_DATE, TENOR_MONTHS, load_folder

__all__ = ["Curve", "Reaction", "compute_reactions", "FAMILIES", "SPLICE_DATE", "TENOR_MONTHS", "load_folder"]
