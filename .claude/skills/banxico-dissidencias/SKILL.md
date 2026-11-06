---
name: banxico-dissidencias
description: Analisa o histórico de votos dissidentes da Junta de Gobierno do Banxico (quem dissentiu, quando, em que direção, padrões por membro), salvo em analyses/dissidencias/. Use quando o usuário perguntar sobre votos, dissidências, divisão da Junta ou posição de um membro específico, ou invocar /banxico-dissidencias [membro].
argument-hint: "[nome do membro]"
---

# /banxico-dissidencias: quem discorda e para que lado

Argumentos recebidos: `$ARGUMENTS` (opcional: nome ou parte do nome de um membro, sem acento).

Princípio: **o código calcula, você interpreta.** Contagens e datas só do JSON.

## Passos

1. Na raiz do projeto:
   ```
   uv run banxico dissents [--member NOME]
   uv run banxico decisions --since 2017
   uv run banxico latest
   ```
   `dissents` traz os votos dissidentes nominais (desde 2021-08) com a direção relativa à maioria
   (`relative_stance`). `decisions` dá o contexto (decisões, votos "por maioria" sem nomes de
   2017–2021). `latest` diz até quando vão os dados.
2. Analise:
   - por membro: nº de dissidências, direção (mais hawkish/dovish), período, e se votam juntos
     (mesma data e mesma alternativa);
   - linha do tempo: em que fases do ciclo surgiram as divisões (ex.: início/fim de ciclo);
   - situação atual: última votação dividida, quem está em minoria e há quantas reuniões;
   - se filtrado por membro: trajetória completa dele e o que preferia em cada caso.
3. Escreva `analyses/dissidencias/<LATEST>.md` (com membro: `analyses/dissidencias/<LATEST>_<membro>.md`,
   membro em minúsculas, sem acento, com hífen).
4. **Verifique as citações:** `uv run banxico verify-quotes analyses/dissidencias/<arquivo>.md` até
   `missing` ficar vazio. Aspas só para texto literal dos comunicados; termos e expressões suas vão
   sem aspas ou em itálico.
5. Responda no chat com o resumo e o caminho do arquivo.

## Modelo do arquivo

```markdown
---
tipo: dissidencias
dados_ate: YYYY-MM-DD
membro: "<nome ou todos>"
gerado_em: YYYY-MM-DD
---

# Dissidências na Junta de Gobierno (até DD/MM/AAAA)

## Resumo
## Por membro
| membro | dissidências | direção | primeira | última |
## Linha do tempo
| data | decisão da maioria | votação | dissidente(s) → preferência |
## Padrões e leitura
## Limitações
- Votos nominais só desde 2021-08; de ~2017 a 2021 só *por mayoría* / *por unanimidad*; antes, não informado.
- Unanimidade não lista nomes: a composição da Junta só aparece em reuniões divididas.
```

## Regras

- Português; nomes como aparecem no comunicado.
- Não infira a composição atual da Junta além do que os votos nominais mostram; se precisar, diga
  que é inferência a partir da última votação nominal.
