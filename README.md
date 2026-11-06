# Banxico — comunicados oficiais

Coleta, estruturação e (próximas etapas) comparação de documentos oficiais do Banco de México:
comunicados de política monetária, minutas, informes, discursos.

## Setup

Requer [uv](https://docs.astral.sh/uv/) (Python 3.12+ é instalado/selecionado automaticamente).

```powershell
uv sync
uv run pytest
```

> Drive de rede (G:): os launchers do venv resolvem o caminho para `\\?\UNC\...`, de onde o
> Windows não carrega a DLL do PyMuPDF. O pacote corrige `sys.path` ao ser importado
> (`src/banxico/_winpath.py`).

## Uso

```powershell
uv run banxico sources                     # fontes configuradas (on/off)
uv run banxico sync                        # descobre + baixa + extrai texto + dados estruturados
uv run banxico decisions --since 2024      # tabela de decisões (--checks mostra avisos)
uv run banxico diff --open                 # último comunicado vs anterior, em HTML no navegador
uv run banxico diff 2026-11-05 --vs 2024-03-21 --open   # qualquer par de reuniões
uv run banxico report --open               # todas as comparações t vs t-1 + índice
uv run banxico structure                   # recalcula decisões/votos/riscos/pronósticos + CSVs
uv run banxico sync -s comunicados --since 2018-01-01
uv run banxico download --limit 5          # só os 5 mais recentes pendentes
uv run banxico extract --force             # reextrai tudo (após mudar regras de extração)
uv run banxico show 2026-11-05             # parágrafos rotulados de um comunicado (--all p/ tabelas/notas)
uv run banxico status                      # contagens por fonte/status e extração
```

Os comandos são idempotentes: rodar `sync` de novo só baixa/extrai o que é novo, o que falhou
ou o que foi extraído com uma versão anterior do extrator.

## Skills do Claude Code (análise interpretada)

No Claude Code, dentro desta pasta:

| comando | o que faz | salva em |
|---|---|---|
| `/banxico-atualizar` | `sync` + análise de cada comunicado novo | `analyses/diff/` |
| `/banxico-diff [data] [--vs data]` | o que mudou vs. reunião anterior (ou outra), com tom relativo −2…+2 | `analyses/diff/` |
| `/banxico-resumo [data]` | briefing da reunião no contexto do ciclo, com postura e tom | `analyses/resumo/` |
| `/banxico-dissidencias [membro]` | histórico de votos dissidentes e padrões | `analyses/dissidencias/` |
| `/banxico-busca "frase" [--section s]` | quando uma expressão apareceu/sumiu | `analyses/busca/` |

As skills seguem o princípio **o código calcula, o Claude interpreta**: os números vêm dos
comandos JSON abaixo, e toda citação é conferida com `verify-quotes` (precisa existir literalmente
num comunicado). Escala de tom: `docs/escala-de-tom.md`. As análises ficam versionadas em `analyses/`.

Comandos JSON usados pelas skills (também úteis para scripts):

```powershell
uv run banxico context 2026-11-05 [--vs DATA]   # decisão, votos, riscos, pronósticos, diff, ciclo
uv run banxico dissents [--member heath]        # dissidências nominais com direção vs. maioria
uv run banxico search "tiempo prolongado"       # linha do tempo de uma expressão
uv run banxico latest                           # comunicado mais recente
uv run banxico verify-quotes analyses/diff/2026-11-05.md
```

## Texto extraído

Cada PDF vira uma sequência de **segmentos** (tabela `segments` no SQLite e um `.md` legível em
`data/text/<fonte>/<ano>/`):

| kind | conteúdo |
|---|---|
| `paragraph` | texto corrido, com `section` heurística |
| `heading` | subtítulos (boletins antigos), títulos de quadros |
| `table` | quadro de pronósticos, uma linha visual por linha |
| `footnote` | `1/ ...`, `Fuente: ...`, `Nota: ...` |
| `figure` | texto de gráficos (fonte pequena): ruído, mantido só por completude |

Seções (`section`, só para `paragraph`, era 2008+): `decision · global · markets · domestic ·
inflation · forecast · assessment · guidance · vote · other`. É um rótulo por palavras-chave na
primeira frase (`text/sections.py:classify`): regras de função (voto, guidance, avaliação,
pronóstico) têm prioridade; entre temas (global, mercados, doméstico, inflação) vence o que aparece
primeiro na frase. Cobertura 2008+: ~51 de 1.131 parágrafos ficam `other`; guidance identificado em
todos os comunicados desde 2016 (inclusive quando vem no meio de outro parágrafo: o campo
`decisions.guidance` e o filtro `search --section` olham também a frase). Na era 2000–2007 só
`decision` é rotulada; o resto fica `other`.

Consulta de exemplo (`sqlite3 data/banxico.db`):

```sql
SELECT doc_date, text FROM v_paragraphs WHERE section = 'guidance' ORDER BY doc_date DESC LIMIT 5;
```

## Dados estruturados

`banxico structure` gera, para cada reunião, uma linha em `decisions` e os pontos do quadro de
pronósticos em `forecasts`. Também exporta `data/exports/comunicados_decisions.csv` e
`comunicados_forecasts.csv` (UTF-8 com BOM, abrem direto no Excel).

| campo | conteúdo | cobertura |
|---|---|---|
| `instrument`, `action`, `change_bp` | tasa/corto; hike/cut/hold; pb | todas (pb do corto só quando há "condiciones monetarias") |
| `rate` / `corto_mn` | tasa objetivo após a decisão / nível do corto | 2008+ / 2000–2007 |
| `effective_date` | "con efectos a partir del..." | ~2020+ |
| `vote_type`, `n_for`, `n_against`, `dissent_summary` | unânime/maioria; dissidentes e o que preferiam | texto 2017+, nominal 2021-08+ |
| `infl_bias`/`infl_change`, `growth_bias`/`growth_change` | balanço de riscos doméstico (+ frase em `*_evidence`) | parcial; melhor 2017+ |
| `guidance` | parágrafo(s) de forward guidance | onde a seção foi rotulada |
| `forecasts` | inflação geral/subjacente a/a e t/t saar, vintage atual e anterior | ~2021-08+ |

**Validações** (avisos em `checks`, contagem em `n_warnings`):
- PDF vs. título da listagem do site (ação, pb, nível);
- continuidade: `rate_t − rate_{t−1}` bate com ação/pb (quando o PDF não traz os pb, eles são derivados);
- votos nominais somam 5 e a maioria é maioria;
- pronósticos: a vintage "Anterior" do comunicado t repete a "Actual" do t−1.

Hoje há 1 aviso em 239 reuniões: 2005-08-26, onde o PDF diz relaxamento de 25pb e o título do
site diz só "el corto se mantiene sin cambio" (inconsistência da fonte, não do parser).

## Reação de mercado (swaps de TIIE)

Dados Bloomberg em `data/TIIE/` (fora do git por licença; carga manual, não roda no `sync`):

```powershell
uv run banxico market                  # carrega data/TIIE, calcula reações e regenera os HTML
uv run banxico reactions --since 2025  # tabela: surpresa, precificado, Δ1a/2a/10a, inclinação
```

| arquivo | conteúdo | uso |
|---|---|---|
| `MPSW.csv` | swaps TIIE 28, 2007-04 → 2024-12 | família `tiie28_*` |
| `MPSWF_combined.csv` | emenda: antes de 2025 = TIIE 28 − spread fixo (níveis artificiais) | só a parte Fondeo real (2025+, 1m desde 2024-12-19) |
| `MPSWF_AAAAMMDD.csv` | snapshots: Fondeo + Treasuries | família `fondeo_*` e `ust_*` (mais recente prevalece) |

Para cada decisão: Δ por prazo no dia (fechamento t−1 → t) e em 2 dias; **surpresa** = Δ do prazo
mais curto (1m Fondeo; antes de 2025, 3m TIIE 28, mais ruidoso); na era Fondeo também o
**precificado** na véspera (1m − tasa) e a surpresa por nível; **trajetória** = Δ1a − surpresa;
**inclinação** = Δ10a − Δ2a; Treasuries no mesmo dia como controle. Regras da emenda: famílias
separadas, nenhuma janela atravessa 2025-01-01, níveis nunca comparados entre famílias. Prints
isolados errados na fonte são descartados por prazo (`flags`).

Aparece no HTML (seção "Reação de mercado"), no `banxico context` (chave `market`) e nas skills
`/banxico-diff` e `/banxico-resumo`, que passam a poder afirmar surpresa **com base na curva**.

## Relatórios de comparação (HTML)

`data/reports/comunicados/<data>.html` compara cada comunicado com o da reunião anterior
(`index.html` lista todos). Pares arbitrários: `<data>_vs_<data>.html`. Cada relatório traz:

- **cartões**: decisão, votação (com dissidentes e o que preferiam), balanço de riscos e % do texto
  alterado, com "mudou" destacado;
- **quadro de pronósticos**: atual vs. reunião anterior, com Δ por trimestre;
- **redline** alinhado parágrafo → frase → palavra. Frases reescritas aparecem como removida +
  nova (não como sopa de palavras). Parágrafos sem mudança ficam ocultos (caixa para mostrar).

Parâmetros de alinhamento em `src/banxico/compare/diff.py` (`PARA_THRESHOLD`, `SECTION_BONUS`,
`SENT_THRESHOLD`).

Limitações conhecidas: reuniões extraordinárias só são marcadas quando o texto diz que *esta*
decisão foi tomada em reunião extraordinária (2016-02-17 sim; 2020-03-20 não); o balanço de riscos
fica vazio quando o comunicado não usa a expressão "balance de riesgos".

## Estrutura

```
config/sources.toml        fontes (URL de listagem, tipo, idioma, parser) + config HTTP
src/banxico/
  config.py                caminhos e leitura do TOML
  models.py                DocumentRef (documento descoberto)
  http.py                  sessão com retry/throttle; corrige encoding cp1252 do site
  sources/                 parsers de páginas de listagem (registro PARSERS)
    banxico_table.py       layout de tabela do CMS (comunicados, minutas, ...)
  storage.py               SQLite (data/banxico.db) + arquivos; migrações por PRAGMA user_version
  pipeline.py              etapas discover / download / extract
  text/                    PDF -> segmentos (EXTRACTOR_VERSION em text/__init__.py)
    extract.py             linhas com layout; remove cabeçalhos; marca tabelas e fonte pequena
    segment.py             agrupa linhas em parágrafos (inclusive entre páginas)
    sections.py            rótulo heurístico de seção
    sentences.py           divisão em frases (base do diff)
    render.py              exporta .md
  structured/              segmentos -> dados (STRUCT_VERSION em structured/__init__.py)
    decision.py            decisão do PDF e do título da listagem
    votes.py               votação (nominal / por texto)
    risks.py               balanço de riscos
    forecasts.py           quadro de pronósticos -> formato longo
    validate.py            validações de série (taxa, vintages)
  compare/                 comparação entre comunicados
    align.py               alinhamento monotônico por programação dinâmica
    diff.py                diff parágrafo -> frase -> palavra
    report.py              HTML autocontido (relatório + índice)
  context.py               saídas JSON para análise (context, dissents, search, verify-quotes)
  market/                  dados de mercado (data/TIIE) e reação às decisões
    loader.py              leitura dos CSVs Bloomberg; tratamento da emenda TIIE 28 -> Fondeo
    events.py              janelas de evento, surpresa, trajetória, filtro de prints errados
  cli.py                   comando `banxico`
.claude/skills/            skills /banxico-* (instruções para o Claude Code)
docs/escala-de-tom.md      critérios da escala de tom −2…+2
analyses/                  análises interpretadas (versionadas)
data/                      (gitignored) banxico.db, raw/ (PDFs), text/ (.md)
tests/
```

### Adicionar uma fonte nova
1. Se a página usa a mesma tabela do CMS: só adicionar `[sources.<id>]` em `config/sources.toml`.
2. Se o layout é outro: criar `src/banxico/sources/<parser>.py` retornando `list[DocumentRef]`,
   registrar em `sources/__init__.py:PARSERS` e referenciar no TOML.

## Roadmap

1. ✅ Scraper de comunicados de PM (histórico desde 2000)
2. ✅ Extração de texto (PyMuPDF) → `segments` + segmentação por parágrafo/seção
3. ✅ Extração estruturada (decisão, taxa, votos/dissidências, projeções, riscos, guidance)
4. ✅ Diff comunicado t vs t-1 → relatório HTML (redline + mudanças estruturadas)
5. Minutas (fonte já configurada, `enabled = false`)
6. ✅ Skills do Claude Code (`.claude/skills/`) para análise e comparação
