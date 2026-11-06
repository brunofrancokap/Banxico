---
name: banxico-resumo
description: Resume uma reunião de política monetária do Banxico no contexto do ciclo (taxa, pb acumulados, votos, guidance, riscos, projeções), com postura absoluta e tom relativo de −2 a +2, salvo em analyses/resumo/. Use quando o usuário pedir um resumo ou briefing de uma decisão do Banxico ou invocar /banxico-resumo [data].
argument-hint: "[YYYY-MM-DD]"
---

# /banxico-resumo: briefing de uma reunião

Argumentos recebidos: `$ARGUMENTS` (data; sem data = a reunião mais recente).

Princípio: **o código calcula, você interpreta.** Números e citações só do que os comandos devolvem.

## Passos

1. Na raiz do projeto:
   ```
   uv run banxico context [DATA]
   uv run banxico show [DATA]
   ```
   `context` traz decisão, votos, riscos, projeções, ciclo e o diff vs. a reunião anterior;
   `show` traz o texto completo do comunicado por seção (para citar o que ele *diz*, não só o que mudou).
   Se não houver dados, rode `uv run banxico sync`.
2. Leia `docs/escala-de-tom.md`.
3. Atribua **duas notas**: `postura` (nível, no contexto do ciclo) e `tom_relativo` (vs. reunião anterior).
4. Escreva `analyses/resumo/<DATA>.md` com o modelo abaixo (sobrescreva se existir).
5. **Verifique as citações:** `uv run banxico verify-quotes analyses/resumo/<DATA>.md` até
   `missing` ficar vazio (corrija a citação ou tire as aspas de paráfrases/traduções).
6. Responda no chat com o "Em 30 segundos" e os caminhos dos arquivos.

## Modelo do arquivo

```markdown
---
tipo: resumo
reuniao: YYYY-MM-DD
postura: -1               # nível, -2..+2
tom_relativo: +1          # vs reunião anterior, -2..+2
decisao: "..."
gerado_em: YYYY-MM-DD
---

# Banxico DD/MM/AAAA: <manchete>

## Em 30 segundos
- <decisão, votação, nível da taxa>
- <mensagem central do guidance>
- <viés de riscos e projeção de convergência>
- **Postura: −1 (dovish)** · **Tom relativo: +1 (levemente mais hawkish)**. <por quê, 1 frase>

## Onde estamos no ciclo
<direção, início, pb acumulados, taxa antes do ciclo, reuniões desde o último movimento;
tabela curta das últimas decisões (data, ação, nível, votação, dissidência)>

## Decisão e votação
## O que o comunicado diz
<por seção: global, mercados, atividade, inflação, previsões e riscos, avaliação, guidance;
1–3 frases cada, com citações literais em espanhol nos pontos-chave>
## Projeções de inflação
<trajetória atual e trimestre de convergência à meta; revisões vs. anterior>
## Reação de mercado
<se `market` existir no JSON: surpresa (prazo, ranking), precificado (era Fondeo), trajetória e
inclinações 1s2s, 2s5s e 2s10s; se confirma a leitura do texto. Senão: "Sem dados de mercado para esta data.">
## O que observar na próxima reunião
## Pontos de atenção
```

## Regras de redação

- Português; citações literais em espanhol, entre aspas.
- Fato ≠ leitura. Surpresa só com base em `market` (curva de swaps), com os números; nunca
  "consenso de analistas". Mesmos cuidados da skill banxico-diff (TIIE 28 vs Fondeo, fechamento diário).
- Se a reunião for da era do "corto" (antes de 2008), adapte: não há tasa objetivo, votos nem quadro
  de pronósticos; diga isso em vez de deixar seções vazias.
