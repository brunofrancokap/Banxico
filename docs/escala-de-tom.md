# Escala de tom (usada pelas skills `/banxico-diff` e `/banxico-resumo`)

Dois números distintos, sempre de −2 a +2, sempre acompanhados de justificativa:

| valor | rótulo |
|---|---|
| +2 | claramente mais hawkish / muito hawkish |
| +1 | levemente mais hawkish / hawkish |
| 0 | neutro / sem mudança relevante |
| −1 | levemente mais dovish / dovish |
| −2 | claramente mais dovish / muito dovish |

## Tom relativo (`tom_relativo`): comunicado t vs. comunicado de referência

Mede a **mudança** de postura entre os dois textos, não o nível. Um corte pode ter tom relativo
positivo (ex.: corta, mas sinaliza pausa longa: "hawkish cut").

Pesos, do maior para o menor:

1. **Forward guidance**: frases sinalizando próximos passos que entram, saem ou mudam
   (ex.: "mantener la tasa por un tiempo prolongado" entrando → hawkish; "evaluar recortes
   adicionales" entrando → dovish).
2. **Decisão e votação vs. a anterior**: aceleração ou desaceleração do ritmo; dissidentes e a
   direção deles (dissidente pedindo manter durante cortes = pressão hawkish no colegiado).
3. **Balanço de riscos para a inflação**: viés que muda ("al alza" → "equilibrado"), lista de riscos
   que cresce de um lado.
4. **Pronósticos**: revisões das projeções (Δ em p.p.), especialmente no horizonte de 4–6 trimestres e
   o trimestre de convergência à meta.
5. **Diagnóstico**: adjetivação de inflação, atividade e câmbio ("persistente", "holgura").

Regras:
- **0** se as mudanças forem só atualização de dados (datas, números observados) sem mudança de mensagem.
- **±2** exige pelo menos dois sinais fortes na mesma direção (ex.: guidance + votação).
- Sinais em direções opostas: diga isso explicitamente e pondere pelos pesos acima.

## Postura absoluta (`postura`): o comunicado sozinho, no contexto do ciclo

Mede o **nível** da postura: quão inclinada a Junta parece a apertar (+) ou afrouxar (−)
nas próximas reuniões, dados o ciclo, o guidance e o balanço de riscos.

## Tom (texto) vs. reação de mercado

A nota de tom é **sobre o texto** e não deve ser ajustada para coincidir com o mercado. A reação da
curva (`banxico context` → `market`) é um teste independente:

| sinal no texto | confirmação típica na curva |
|---|---|
| mais hawkish (guidance de pausa/alta, dissidência hawkish) | `path_bp` > 0 e/ou inclinações (`slope_1s2s_bp`, `slope_2s5s_bp`, `slope_2s10s_bp`) > 0 com Treasuries estáveis/caindo |
| mais dovish | `path_bp` < 0, ponta curta caindo além da surpresa |

Divergência entre texto e curva é informação: registre-a, não a esconda.

## O que a escala NÃO mede

- **Surpresa**: vem só da curva (`market.surprise_bp`), nunca do texto. Sem `market`, não afirmar.
- Expectativa de analistas/consenso: o projeto não tem pesquisas de mercado.
- Opinião sobre se a decisão foi correta.
