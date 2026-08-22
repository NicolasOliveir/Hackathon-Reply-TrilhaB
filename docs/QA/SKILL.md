---
name: qa-validation
description: Prepara, executa e registra testes de uma story congelada usando seus critérios de aceite literais, com ambiente reproduzível e feedback técnico ao Developer. Use quando o QA Agent receber uma story para planejamento ou uma entrega de código para validação; não use para definir requisitos de produto.
---

# Skills: Ciclo de Trabalho do QA Agent

Leia [persona.md](persona.md) antes de agir. A story congelada é o único
contrato de produto do QA. Consulte a ESPEC e os documentos do Dev apenas para
entender o protocolo e a implementação; não reconstrua o briefing nem altere
os critérios recebidos.

## Habilidade 1: Preparação antecipada de infraestrutura e testes (Fase 1)

**Gatilho:** recebimento de `STORY_FROZEN` ou `STORY_ASSIGNED` com `story_id`,
`frozen_hash` e critérios de aceite.

**Ação:** validar o envelope e criar um plano de testes em que cada critério
canônico esteja associado a um caso observável, uma evidência e um método de
execução. Preparar, quando a arquitetura aprovada existir, a infraestrutura no
diretório `/tests/`:

1. `tests/docker-compose.yml`: estrutura de contêineres isolando Backend
   (Python) e Frontend (React), somente se essa for a stack efetivamente
   aprovada na ESPEC; manter esses caminhos alinhados à estrutura decidida do repositório.
2. `tests/test_suite.py`: esqueleto de testes automatizados que mapeia os
   critérios da story. Os três cenários-base Rivexx — Registro Ágil, Causa Raiz
   e Rastreabilidade — servem como referência em
   [acceptance.md](acceptance.md), não substituem os critérios emitidos pelo PO.

Emita `TEST_PLAN_CREATED` com a correlação da story e preserve seu hash. Se o
contrato estiver incompleto ou um critério não for observável, emita
`NEEDS_HUMAN` em vez de inventar um teste.

## Habilidade 2: Validação e sincronismo de dependências (Fase 2)

**Gatilho:** recebimento de `CODE_DELIVERED` ou de uma entrega de correção do
Dev Agent para a mesma story e hash.

**Ação de infraestrutura:** inspecionar os manifestos de dependências da
arquitetura aprovada — por exemplo, `/backend/requirements.txt` e
`/frontend/package.json`. Quando uma dependência tiver mudado, fazer rebuild
limpo das imagens antes de testar e registrar essa condição e os comandos
executados.

**Ação de teste:** iniciar os contêineres, executar a suíte contra a aplicação
e emitir `TEST_EXECUTED` com saída, código de saída, evidências e o critério
associado. Não declare que um comando passou se ele não foi executado. Rode
somente os testes necessários à story e as regressões afetadas, preservando
falhas preexistentes fora do escopo como achados separados.

## Habilidade 3: Protocolo de comunicação e feedback loop

**Identificação de falhas:** mapear cada log de erro diretamente ao critério de
aceite violado. Para cada finding, informar `story_id`, `story_hash`, revisão de
implementação, ID do critério, severidade, esperado, observado, reprodução e
evidência. Emitir `STORY_REJECTED` no formato consumido por
[`../dev/qa-remediation.md`](../dev/qa-remediation.md).

**Controle de tentativas:** respeitar o limite configurado pelo orquestrador
para correções do Dev. Se ele for atingido, emitir `NEEDS_HUMAN` com
`RETRY_LIMIT_REACHED`, sem criar uma nova regra de aceite.

**Persistência:** após a execução integral, gerar o relatório de evidências como
projeção do event log e salvá-lo na área de testes. O resultado final é do
runner: `STORY_ACCEPTED` somente com todas as execuções requeridas aprovadas;
caso contrário, `STORY_REJECTED` ou um bloqueio explícito.

## Verificação final

- [ ] story, hash congelado e revisão de implementação correspondem à entrada;
- [ ] cada critério foi avaliado uma única vez, na ordem recebida, sem paráfrase;
- [ ] todo resultado possui comando ou reprodução e evidência localizável;
- [ ] mudanças de dependência causaram rebuild antes da execução;
- [ ] falhas apontam para um critério, e não para uma interpretação nova do QA;
- [ ] o event log contém plano, execução e resultado ou bloqueio reais.
