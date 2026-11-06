# Análises

Leituras interpretadas geradas pelas skills do Claude Code (`.claude/skills/`). Diferente de
`data/` (regenerável pelo código), estas são interpretações e ficam versionadas no git.

| pasta | skill | arquivo |
|---|---|---|
| `diff/` | `/banxico-diff` | `<data>.md` ou `<data>_vs_<data>.md` |
| `resumo/` | `/banxico-resumo` | `<data>.md` |
| `dissidencias/` | `/banxico-dissidencias` | `<dados_ate>[_membro].md` |
| `busca/` | `/banxico-busca` | `<slug-da-frase>.md` |

Cada arquivo tem um cabeçalho YAML (`tom_relativo`, `postura`, datas...) que permite, no futuro,
montar séries das notas de tom. Escala em `docs/escala-de-tom.md`.

Números e citações vêm do banco (`uv run banxico context ...`); a interpretação é do Claude e
deve ser lida como tal.
