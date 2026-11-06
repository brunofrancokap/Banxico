# CLAUDE.md

Projeto de coleta e comparação de documentos oficiais do Banxico (comunicados de política
monetária, minutas, etc.). O usuário é da área de trading/macro; respostas em português.

## Comandos
- `uv sync` · `uv run pytest` · `uv run banxico <sources|discover|download|sync|extract|structure|decisions|show|status>`
- Comparação: `uv run banxico diff [data] [--vs data] [--open]` -> `data/reports/comunicados/*.html`;
  `banxico report` regenera todos + `index.html` (~15 s). `sync` já inclui o report.
  Para checar o visual: screenshot com Edge headless
  (`msedge --headless=new --screenshot=... --user-data-dir=<scratch> file:///...`).
- Dados por reunião: tabela `decisions` + `forecasts` (formato longo); CSVs em `data/exports/`.
  `uv run banxico decisions --since 2024 --checks` mostra a tabela com avisos de validação.
- Rodar sempre via `uv run` (o `python` global da máquina é 3.7 e não serve).
- Texto legível de cada comunicado: `data/text/comunicados/<ano>/<data>_<guid>.md`
  (ou `uv run banxico show <data>`). Dados consultáveis: tabela `segments` / view `v_paragraphs`.

## Dados de mercado (data/TIIE) — ATENÇÃO À EMENDA
- Fornecidos pelo usuário (Bloomberg, licenciados: nunca versionar). **Não** são atualizados
  diariamente; `banxico market` é manual e não roda no `sync`.
- `MPSW.csv` = swaps TIIE 28 (2007-04 → 2024-12-31). `MPSWF_combined.csv` = emenda feita pelo
  usuário: **antes de 2025 é TIIE 28 menos um spread fixo por prazo (−23,5 a −30 pb), níveis
  artificiais**; Fondeo real só a partir de 2025-01-01 (1m desde 2024-12-19). Snapshots
  `MPSWF_AAAAMMDD.csv` trazem Fondeo + Treasuries (só desde 2026-06).
- Regras: famílias `tiie28_*` e `fondeo_*` separadas no banco; nenhuma janela atravessa 2025-01-01;
  **nunca comparar níveis entre as famílias**; nível (priced/surprise_level) só na era Fondeo.
- Armadilha de ticker: no arquivo de TIIE 28, `MPSWF` é o swap de **6 meses**.
- Há prints errados na fonte (ex.: tiie28_1y em 2022-09-28); o filtro `is_bad_print` descarta o
  prazo e registra em `flags`. Movimentos reais da curva inteira (2020-03-20) são mantidos.

## Skills e análises
- Skills em `.claude/skills/banxico-*`: diff, resumo, dissidencias, busca, atualizar.
- Regra de ouro: números e citações só dos comandos JSON (`context`, `dissents`, `search`);
  aspas só para texto literal dos comunicados, conferido com `banxico verify-quotes <arquivo>`.
- Análises em `analyses/<tipo>/` (versionadas, cabeçalho YAML com notas de tom). Escala em
  `docs/escala-de-tom.md`. Surpresa só com base na curva (`context` → `market`); nunca "consenso".
- Filtro `--section` da busca usa o rótulo do parágrafo OU a classificação da frase (guidance de
  2016–2019 vem no meio de outros parágrafos). Ainda heurístico: comparar com a busca sem filtro.
- Ao mexer em `text/sections.py`: simular a mudança de rótulos em todo o corpus 2008+ e ler os
  casos que mudaram antes de aplicar (regras novas costumam "roubar" parágrafos de outra seção).

## Convenções
- Fontes são configuradas em `config/sources.toml`; parsers de listagem em `src/banxico/sources/`
  registrados em `PARSERS`. Não hardcode URLs no código.
- `data/` é gerado e gitignored. Arquivos em `data/raw/` são imutáveis (fonte da verdade);
  etapas derivadas (texto, diffs, scores) devem ser tabelas novas no SQLite ligadas a `documents.id`,
  com migração via `PRAGMA user_version` em `storage.py`.
- Espanhol é o idioma de referência para análise; inglês é tradução.
- Mudou regra em `src/banxico/text/`? Incrementar `EXTRACTOR_VERSION` e rodar `banxico extract`.
  Antes, validar em todo o corpus (não só em um PDF): os formatos variam muito entre eras.
- Mudou regra em `src/banxico/structured/`? Incrementar `STRUCT_VERSION`; `banxico structure`
  recalcula tudo. Meta: `n_warnings = 0` em 2008+ (teste `test_real_series_is_consistent`).
  Um aviso novo geralmente é bug de extração de texto, não do parser estruturado (ex.: v2 do
  extrator corrigiu "ciento." descartado como cabeçalho em 2013-03-08).
- O pacote `banxico` deve ser importado antes de `pymupdf` em scripts ad hoc: ele corrige o
  caminho `\\?\UNC\` do drive de rede, que impede carregar a DLL (ver `_winpath.py`).

## Peculiaridades do site do Banxico
- HTML declara utf-8 mas vem em cp1252 → usar `http.decode_html`.
- URLs de documentos têm GUID entre `{}`; escapar (`http.safe_url`). No curl, usar `-g`.
- A página de listagem de comunicados traz todo o histórico (2000→hoje) numa página só.
- Comunicados antigos (2000–2007) falam do "corto"; a tasa objetivo começa em 2008.

## Estrutura dos PDFs (aprendida na extração)
- 2000–2007: boletins com bullets, subtítulos, gráficos com texto vetorial (fonte pequena), listas
  `a)`/`i)`. A decisão costuma vir no FIM, após menções a decisões anteriores.
- 2008+: decisão no 1º parágrafo (negrito); cabeçalho data + "Comunicado de Prensa" em toda página.
- Votação: até ~2020 dentro do texto ("por unanimidad"/"por mayoría"); depois parágrafo
  "Votaron a favor..." com nomes e voto dissidente.
- Quadro de pronósticos (Actual vs Anterior, por trimestre) a partir de ~2021-08. A linha
  "Anterior" pode ter horizonte menor (valores alinhados à esquerda) e pode estar datada no
  Informe Trimestral, não na reunião anterior.
- Votos nominais só aparecem quando há dissidência; unanimidade em 2021+ = sem parágrafo "Votaron".
- Bboxes de linhas se sobrepõem (gap negativo): agrupar parágrafos por pitch de baseline, não gap.
