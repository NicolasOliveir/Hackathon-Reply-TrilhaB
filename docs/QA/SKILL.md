---
name: qa-validation
description: Prepara, executa e registra testes de uma story congelada usando seus critérios de aceite literais, com ambiente reproduzível e feedback técnico ao Developer. Use quando o QA Agent receber uma story para planejamento ou uma entrega de código para validação; não use para definir requisitos de produto.
---

# Skills: Ciclo de Trabalho do QA Agent

Leia [persona.md](persona.md) e o [contrato do plano de testes](test-contract.md)
antes de agir. A story congelada é o único contrato de produto do QA. Consulte
a ESPEC e os documentos do Dev apenas para entender o protocolo e a
implementação; não reconstrua o briefing nem altere os critérios recebidos.

## Habilidade 1: Preparação antecipada de infraestrutura e testes (Fase 1)

**Gatilho:** tarefa de QA recebida da API, contendo `STORY_FROZEN`,
`CODE_DELIVERED` ou `CODE_REDELIVERED`, `implementation_revision` e o manifesto
de contexto autorizado.

**Ação:** validar o contexto e criar a configuração JSON
`tests/config/<story-id>.v<version>.r<revision>.json`. Cada critério canônico
deve estar associado a um item na mesma ordem, casos observáveis, evidências e
método de execução. Registrar o arquivo como artefato pela API e submeter a
saída `TEST_PLAN_CREATED`; o worker não grava no banco. Preparar, quando a
arquitetura aprovada existir, a infraestrutura no diretório `/tests/`:

1. `tests/docker-compose.yml`: estrutura de contêineres isolando Backend
   (Python) e Frontend (React), somente se essa for a stack efetivamente
   aprovada na ESPEC; manter esses caminhos alinhados à estrutura decidida do repositório.
2. `tests/config/<story-id>.v<version>.r<revision>.json`: arquivo de
   configuração serializável consumido pelo runner. Seu formato está em
   [test-contract.md](test-contract.md); não substituir esse arquivo por código
   de configuração em outra linguagem. Os três cenários-base Rivexx em
   [acceptance.md](acceptance.md) são referência, não critérios adicionais.

Submeta `TEST_PLAN_CREATED` com a correlação da story e preserve o hash que a
API devolver. Se o contrato estiver incompleto ou um critério não for
observável, submeta `NEEDS_HUMAN` em vez de inventar um teste.

## Habilidade 2: Validação e sincronismo de dependências (Fase 2)

**Gatilho:** após a API validar o plano JSON e disponibilizar os testes
materializados para o runner.

**Ação de infraestrutura:** inspecionar os manifestos de dependências da
arquitetura aprovada — por exemplo, `/backend/requirements.txt` e
`/frontend/package.json`. Quando uma dependência tiver mudado, fazer rebuild
limpo obrigatório no campo `environment` da configuração JSON e registrar os
manifestos afetados. O runner executa o rebuild e registra os comandos e seus
resultados.

**Ação de teste:** fornecer ao runner a configuração JSON e os testes
materializados. O runner inicia o ambiente e emite `TEST_EXECUTED` com saída,
código de saída, evidências e critério associado. O QA não pode alegar que um
comando passou sem a evidência do runner. Preserve falhas preexistentes fora do
escopo como achados separados.

## Habilidade 3: Protocolo de comunicação e feedback loop

**Identificação de falhas:** mapear cada log de erro diretamente ao critério de
aceite violado. Para cada finding, informar `story_id`, `story_hash`, revisão de
implementação, ID do critério, severidade, esperado, observado, reprodução e
evidência. O QA submete os findings; a API deriva `STORY_REJECTED` no formato
consumido por [`../dev/qa-remediation.md`](../dev/qa-remediation.md).

**Controle de tentativas:** respeitar o limite configurado pelo orquestrador
para correções do Dev. Se ele for atingido, emitir `NEEDS_HUMAN` com
`RETRY_LIMIT_REACHED`, sem criar uma nova regra de aceite.

**Persistência:** após a execução integral, a API projeta o relatório de
evidências do event log. O runner produz `TEST_EXECUTED`; a API deriva
`STORY_ACCEPTED` somente quando todas as execuções requeridas aprovam, ou
`STORY_REJECTED`/bloqueio explícito nos demais casos.

## Verificação final

- [ ] story, hash congelado e revisão de implementação correspondem à entrada;
- [ ] a configuração JSON preserva IDs, texto e ordem dos critérios recebidos;
- [ ] o hash do plano retornado pela API corresponde ao artefato submetido;
- [ ] cada critério foi avaliado uma única vez, na ordem recebida, sem paráfrase;
- [ ] todo resultado possui comando ou reprodução e evidência localizável;
- [ ] mudanças de dependência causaram rebuild antes da execução;
- [ ] falhas apontam para um critério, e não para uma interpretação nova do QA;
- [ ] o event log contém plano, execução e resultado ou bloqueio reais.
