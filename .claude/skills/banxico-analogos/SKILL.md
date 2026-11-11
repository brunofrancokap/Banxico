---
name: banxico-analogos
description: Encontra reuniões passadas do Banxico parecidas com uma reunião-alvo, no comunicado (sinalização de pausa/mais movimentos) e na reação da curva de swaps (surpresa, trajetória, inclinações 1s2s/2s5s/2s10s), e mostra o que o Banxico fez depois; salvo em analyses/analogos/. Use quando o usuário pedir precedentes, análogos, "quando foi parecido" ou invocar /banxico-analogos [data].
argument-hint: "[YYYY-MM-DD]"
---

# /banxico-analogos: precedentes no texto e no mercado

Argumentos recebidos: `$ARGUMENTS` (data; sem data = a reunião mais recente).

Princípio: **o código calcula, você interpreta.** Distâncias, números, datas e frases só do JSON.

## Passos

1. Na raiz do projeto:
   ```
   uv run banxico analogs [DATA]
   uv run banxico context [DATA]
   ```
   `analogs` traz:
   - `target`: decisão, `text_signal` (pausa | mais | misto | neutro, com as frases) e `market`;
   - `market_analogs`: reuniões anteriores com a **mesma ação**, ordenadas por `market_distance`
     (menor = mais parecido; métricas padronizadas) e `sign_matches`;
   - `text_analogs`: mesma ação e mesmo `text_signal`;
   - `both`: estão nas duas listas;
   - `aftermath` de cada candidato: próximas decisões, próximo movimento (meses depois) e Δ da taxa
     em 6 e 12 meses.
   Se `market` do alvo vier `null`, rode `uv run banxico market` (precisa de `data/TIIE`); se não houver
   dados, faça só a parte de texto e diga isso.
2. **Confira o texto dos candidatos principais** antes de afirmar semelhança: `text_signal` é
   heurístico. Para cada candidato que for citar, rode `uv run banxico show <data>` e leia a
   decisão e a sinalização. Descarte falsos positivos e explique.
3. Escolha 3–5 análogos e classifique cada um: **texto e mercado**, **só mercado** ou **só texto**.
   Um análogo de mercado com texto oposto (ou vice-versa) também é informativo: mostra o limite de
   ler só uma das fontes.
4. Escreva `analyses/analogos/<DATA>.md` com o modelo abaixo (sobrescreva se existir).
5. **Verifique as citações:** `uv run banxico verify-quotes analyses/analogos/<DATA>.md` até `missing`
   ficar vazio.
6. Responda no chat com o melhor análogo, a tabela compacta e o caminho do arquivo.

## Modelo do arquivo

```markdown
---
tipo: analogos
reuniao: YYYY-MM-DD
melhor_analogo: YYYY-MM-DD
gerado_em: YYYY-MM-DD
fonte: "uv run banxico analogs YYYY-MM-DD"
---

# Banxico DD/MM/AAAA: precedentes

## Hoje
<decisão, sinalização (frase literal), reação da curva: surpresa, trajetória, 1s2s, 2s5s, 2s10s>

## Análogos
| reunião | decisão | sinalização | surpresa | trajetória | 1s2s | 2s5s | 2s10s | distância | parece em |

## O melhor análogo
<por que (texto + curva), com citação literal; o que aconteceu depois (aftermath)>

## Os outros
<1–2 frases cada; o que cada um ensina>

## O que aconteceu depois dos análogos
| reunião | próximo movimento | meses depois | Δ taxa 6m | Δ taxa 12m |

## Leitura
<o que os precedentes sugerem para as próximas reuniões; diferenças relevantes vs. hoje
(votação, projeções, ciclo, cenário externo); nunca previsão determinística>

## Ressalvas
```

## Regras

- Português; citações literais em espanhol.
- Só variações de mercado são comparadas entre eras; **nunca níveis** entre TIIE 28 e Fondeo.
  Antes de 2025 a surpresa vem do 3m da TIIE 28 (mais ruidosa): diga isso quando comparar com hoje.
- Não use análogos posteriores à reunião-alvo (o JSON já filtra).
- "O que aconteceu depois" é histórico, não previsão: amostras pequenas, contextos diferentes.
- Votação nominal só desde 2021-08; não afirme divisão da Junta em análogos antigos.
