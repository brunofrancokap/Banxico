---
name: banxico-atualizar
description: Atualiza a base do Banxico (baixa e processa comunicados novos) e, se houver comunicado novo, já produz a análise de diferenças (/banxico-diff) de cada um. Use quando o usuário pedir para atualizar, checar se saiu comunicado novo do Banxico, ou invocar /banxico-atualizar.
---

# /banxico-atualizar: buscar novidades e analisar

## Passos

1. Na raiz do projeto, registre o estado atual:
   ```
   uv run banxico latest
   ```
2. Atualize (precisa de internet; leva segundos se não houver nada novo):
   ```
   uv run banxico sync
   ```
   O `sync` faz discover → download → extract → structure → report. Observe no log:
   "N documentos listados (M novos)" e eventuais `ERROR`/`WARNING`.
3. Rode `uv run banxico latest` de novo e compare com o passo 1.
4. **Se houver comunicado(s) novo(s):** para cada data nova, em ordem cronológica, siga as
   instruções de `.claude/skills/banxico-diff/SKILL.md` com essa data (gera
   `analyses/diff/<data>.md`). Responda com a manchete e o tom de cada um.
5. **Se não houver nada novo:** diga qual é o comunicado mais recente e verifique se existe
   `analyses/diff/<latest>.md`. Se não existir, pergunte se o usuário quer gerar a análise.
6. Se o `sync` registrar avisos de validação (`WARNING`) para a reunião nova, mencione-os:
   podem indicar mudança de formato do PDF que exige ajuste no extrator.

## Erros comuns

- Falha de rede ou site fora do ar: informe e não tente de novo em loop.
- "nenhum documento encontrado; o layout da página pode ter mudado": o site mudou; avise o
  usuário que o parser da listagem (`src/banxico/sources/banxico_table.py`) precisa de ajuste.
