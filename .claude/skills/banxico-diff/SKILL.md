---
name: banxico-diff
description: Compara um comunicado de política monetária do Banxico com o da reunião anterior (ou com outra data) e escreve uma análise interpretada em português, com tom relativo de −2 a +2, salva em analyses/diff/. Use quando o usuário pedir para comparar comunicados do Banxico, perguntar o que mudou na última decisão, ou invocar /banxico-diff [data] [--vs data].
argument-hint: "[YYYY-MM-DD] [--vs YYYY-MM-DD]"
---

# /banxico-diff: o que mudou entre dois comunicados

Argumentos recebidos: `$ARGUMENTS`
- Sem data → o comunicado mais recente vs. a reunião anterior.
- `DATA` → esse comunicado vs. a reunião anterior a ele.
- `DATA --vs OUTRA` → par arbitrário (ex.: início vs. fim de um ciclo).

Princípio: **o código calcula, você interpreta.** Todo número e toda citação vêm do JSON. Nunca
invente números, datas, nomes ou frases. Se algo não está no JSON, diga que não está disponível.

## Passos

1. Na raiz do projeto, rode (acrescente `DATA` e `--vs OUTRA` conforme os argumentos):
   ```
   uv run banxico context [DATA] [--vs OUTRA]
   uv run banxico diff [DATA] [--vs OUTRA]
   ```
   O primeiro devolve o JSON com tudo; o segundo gera o HTML (caminho em `report_html`).
   Se o comando falhar por falta de dados, rode `uv run banxico sync` e tente de novo.
2. Leia `docs/escala-de-tom.md` (critérios e pesos do tom relativo).
3. Analise o JSON:
   - `decision` / `votes`: atual vs. anterior; dissidentes e a direção deles.
   - `text_diff.paragraphs`: foque nos `status` = modified/added/removed. Para cada seção,
     o que entrou (`added`), saiu (`removed`) e mudou (`edited` old→new). `guidance` primeiro.
   - `risk_balance`, `forecasts` (use `delta`; `basis` diz contra o que se compara).
   - `cycle`: onde a decisão se encaixa (direção, pb acumulados, reuniões desde o último movimento).
   - `validation_warnings`: se houver, mencione na seção "Pontos de atenção".
   - `market` (pode ser `null`): reação da curva à decisão **desta** reunião. `surprise_bp` (Δ do
     prazo mais curto no dia; `surprise_tenor` diz qual), `surprise_abs_rank_in_family`, `priced_bp`
     e `surprise_level_bp` (só era Fondeo), `path_bp` (Δ1a − surpresa), inclinações `slope_1s2s_bp` (Δ2a−Δ1a), `slope_2s5s_bp` (Δ5a−Δ2a), `slope_2s10s_bp` (Δ10a−Δ2a),
     `d1_bp`/`d2_bp` por prazo, `ust_d1_bp` (Treasuries no mesmo dia, quando houver), `flags` e `notes`.
4. Atribua o **tom relativo** (−2…+2) seguindo a escala, **pelo texto**. Justifique com os sinais
   concretos. Depois compare com o mercado: a curva confirma ou contradiz sua leitura (ex.: tom
   hawkish + `path_bp`/`slope` positivos = confirma)? Diga isso; não ajuste a nota para "acertar" o mercado.
5. Escreva o arquivo `analyses/diff/<DATA>.md` (par arbitrário: `analyses/diff/<DATA>_vs_<OUTRA>.md`)
   com o modelo abaixo. Se já existir, sobrescreva (a análise é regenerável).
6. **Verifique as citações:** `uv run banxico verify-quotes analyses/diff/<arquivo>.md`. Toda
   citação entre aspas precisa existir literalmente num comunicado. Se algo aparecer em `missing`,
   corrija (copie do JSON) ou tire as aspas (paráfrase/tradução não vai entre aspas) e rode de novo
   até `missing` ficar vazio.
7. Responda no chat com: manchete, tom relativo com justificativa curta, 3–5 bullets das mudanças
   mais importantes e os caminhos do `.md` e do HTML.

## Modelo do arquivo

```markdown
---
tipo: diff
reuniao: YYYY-MM-DD
comparada_com: YYYY-MM-DD
tom_relativo: +1          # -2..+2, ver docs/escala-de-tom.md
decisao: "corte de 25 pb para 6,25% (3x2)"
gerado_em: YYYY-MM-DD
fonte: "uv run banxico context ..."
---

# Banxico DD/MM/AAAA vs DD/MM/AAAA: <manchete curta>

**Tom relativo: +1 (levemente mais hawkish).** <1–2 frases com os sinais que definem o tom.>

## Decisão e votação
<ação, pb, nível; comparação com a anterior; quem dissentiu e o que queria; posição no ciclo>

## Forward guidance
<o que entrou / saiu / mudou, com citação literal em espanhol entre aspas e tradução curta se útil>

## Balanço de riscos e pronósticos
<viés atual vs anterior; riscos que entraram/saíram; tabela compacta dos Δ não nulos de projeção>

## Diagnóstico
<mudanças relevantes na descrição de inflação, atividade, mercados e cenário externo>

## Reação de mercado
<só se `market` não for null: surpresa (quanto, em qual prazo, posição no ranking), quanto estava
precificado (era Fondeo), trajetória e inclinações (1s2s, 2s5s, 2s10s); Treasuries no dia se houver; se a curva confirma
ou contradiz a leitura do texto. Se `market` for null: "Sem dados de mercado para esta data.">

## Leitura
<o que o conjunto sinaliza para as próximas reuniões; sinais conflitantes; o que observar>

## Pontos de atenção
<avisos de validação, limitações (ex.: seções heurísticas), "sem dados de mercado">

Fontes: relatório `<report_html>` · PDFs: <url atual> · <url comparado>
```

## Regras de redação

- Português; citações do comunicado **literais em espanhol**, entre aspas.
- Separe fato (o que o texto diz) de leitura (sua interpretação). Use "sugere", "sinaliza".
- **Surpresa só com base em `market`**, com o número ("surpresa de −15,5 pb no 1m"). Sem `market`,
  não afirme surpresa. Nunca afirme expectativa de analistas/consenso: o projeto só tem a curva.
- Cuidados com `market`: fechamento diário mistura outras notícias (cite os Treasuries se houver);
  antes de 2025 a série é TIIE 28 e a surpresa vem do 3m (inclui expectativa da reunião seguinte);
  nunca compare níveis entre TIIE 28 e Fondeo. Prazos com `flags` de cotação suspeita foram excluídos.
- Para pares arbitrários (`--vs`), `market` refere-se só à reunião mais recente do par.
- Mudanças cosméticas (datas, números atualizados sem mudança de mensagem) não merecem destaque.
- Seja direto: o leitor é um profissional de mercado.
