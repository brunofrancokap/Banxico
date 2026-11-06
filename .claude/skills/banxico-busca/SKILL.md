---
name: banxico-busca
description: Procura uma expressão em todo o histórico de comunicados de política monetária do Banxico (2000–hoje) e mostra quando apareceu, sumiu ou voltou, com trechos e leitura; salvo em analyses/busca/. Use quando o usuário perguntar desde quando o Banxico usa uma frase, quando ela saiu, ou invocar /banxico-busca "frase" [--section s] [--since data].
argument-hint: "\"frase\" [--section guidance] [--since YYYY-MM-DD]"
---

# /banxico-busca: linha do tempo de uma expressão

Argumentos recebidos: `$ARGUMENTS`
- Frase (em espanhol; a busca ignora acentos e maiúsculas).
- `--section`: decision | global | markets | domestic | inflation | forecast | assessment | guidance | vote
- `--since`: data inicial.

Princípio: **o código calcula, você interpreta.** Datas, contagens e trechos só do JSON.

## Passos

1. Na raiz do projeto:
   ```
   uv run banxico search "FRASE" [--section S] [--since DATA]
   ```
2. Se vier 0 resultado ou poucos, tente **variações** (singular/plural, tempo verbal, sinônimo
   comum, trecho mais curto) e informe quais buscas fez. Se o usuário escreveu em português,
   traduza para a expressão que o Banxico usaria em espanhol e diga isso.
   **Se o usuário filtrou por seção, rode também sem `--section`** e compare. O filtro considera o
   rótulo do parágrafo e a classificação da própria frase, mas ambos são heurísticos. Se as contagens
   divergirem, veja os trechos que só aparecem sem filtro e diga se são ou não da seção pedida.
3. Analise: `first`, `last`, `runs` (sequências contínuas de reuniões com a frase),
   `in_latest_meeting`, e os trechos (`hits`). Destaque a primeira aparição, a última, cada
   interrupção/retorno e como a frase variou em torno (o que vinha antes/depois na mesma frase).
4. Se ajudar a interpretar, rode `uv run banxico decisions --since <first>` para relacionar
   aparições com o ciclo (ex.: frase surge na reunião que inicia cortes).
5. Escreva `analyses/busca/<slug>.md` (slug = frase em minúsculas, sem acento, com hífens,
   até 60 caracteres; acrescente `_<secao>` se houver filtro).
6. **Verifique as citações:** `uv run banxico verify-quotes analyses/busca/<slug>.md` até
   `missing` ficar vazio. A própria frase buscada também vai entre aspas: se ela não existir
   literalmente, escreva-a sem aspas (ex.: em itálico).
7. Responda no chat com a linha do tempo resumida e o caminho do arquivo.

## Modelo do arquivo

```markdown
---
tipo: busca
frase: "..."
filtros: "section=..., since=..."
reunioes_com_frase: N
primeira: YYYY-MM-DD
ultima: YYYY-MM-DD
presente_na_ultima: true
gerado_em: YYYY-MM-DD
---

# "<frase>" nos comunicados do Banxico

## Resumo
## Linha do tempo
| período | reuniões | contexto (decisões no período) |
## Trechos-chave
<primeira aparição, mudanças de redação, última aparição: citações literais com data>
## Leitura
## Buscas realizadas
```
