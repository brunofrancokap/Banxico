"""Permite `python -m banxico ...` (equivalente ao comando `banxico`)."""

from .cli import main

raise SystemExit(main())
