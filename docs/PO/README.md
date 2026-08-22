# PO Agent — mapa dos artefatos

Esta pasta detalha como o PO Agent cumpre o contrato compartilhado definido na
[ESPEC §6.1](../ESPEC.md).

| Arquivo | Papel |
|---|---|
| [persona.md](persona.md) | missão, autoridade, limite de contexto e critério de conclusão |
| [SKILL.md](SKILL.md) | procedimento para decompor briefing em backlog vertical e auditável |
| [acceptancecriteria.md](acceptancecriteria.md) | forma canônica dos critérios que o QA deverá verificar |

## Precedência

1. [DESCRICAO-TAREFA.md](../DESCRICAO-TAREFA.md) é a fonte do desafio e não deve ser editada.
2. [ESPEC.md](../ESPEC.md) define o contrato entre PO, Dev, QA, runner e orquestrador.
3. Os arquivos desta pasta implementam o comportamento interno do PO sem ampliar sua autoridade.
4. [ENTENDIMENTO.md](../ENTENDIMENTO.md) registra análise e recomendações, não decisões.

Em caso de divergência, a ESPEC prevalece sobre os artefatos operacionais. Se a divergência
envolver uma seção marcada `DECIDIDO`, a correção exige uma nova ADR, conforme a regra da ESPEC.

## Saída esperada

O PO recebe sozinho o briefing bruto e produz o envelope estruturado definido na ESPEC: stories
priorizadas, decisões explícitas e uma matriz de cobertura. Cada critério tem uma string canônica
congelada, que o QA deve reproduzir sem paráfrase e avaliar exatamente uma vez.

Estes arquivos são definição do agente, não backlog pré-fabricado da Rivexx. O backlog real deve
ser gerado durante a execução e projetado a partir do event log auditável.

Quando o orquestrador existir, sua configuração do PO deverá ler estes artefatos diretamente ou
empacotá-los de forma automatizada. Uma cópia manual em `squad/agents/po` criaria duas fontes de
verdade e não é permitida.
