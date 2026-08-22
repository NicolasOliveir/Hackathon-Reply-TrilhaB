# Quadro de tarefas — Iteração 1

> **Branch oficial:** `main`
> **Objetivo da iteração:** provar a comunicação distribuída briefing → fake worker em container
> → API central → PostgreSQL/event log → timeline React, ainda sem depender de LLM.
> **Regra:** nenhuma implementação começa antes de nome, branch e horário da reserva estarem
> publicados neste arquivo em `origin/main`.

Leia [AGENTS.md](AGENTS.md) antes de reservar ou alterar qualquer item.

## Estados

| Estado | Significado |
|---|---|
| `LIVRE` | disponível para reserva |
| `EM_ANDAMENTO` | reservada e em implementação |
| `EM_REVISAO` | branch publicada e pronta para revisão |
| `BLOQUEADA` | impedimento explícito registrado |
| `CONCLUIDA` | integrada em `main` e verificada |

## Quadro de reserva

Edite somente a linha que você está reservando ou atualizando. `Responsável` deve conter o nome
do desenvolvedor; `Branch` deve existir no remoto enquanto a tarefa estiver ativa.

| ID | Entrega | Status | Responsável | Branch | Início | Dependências | Área exclusiva | Atualização |
|---|---|---|---|---|---|---|---|---|
| `I1-001` | Contratos e scaffold do monorepo | `CONCLUIDA` | MatheusSchimieguelSilva | `task/I1-001-contracts` | 2026-08-22 12:55 -03:00 | — | `packages/contracts/**` e manifests raiz acordados | Integrada na `main` em `3f59cd5`; 4 testes de contrato aprovados em 2026-08-22 14:26 -03:00 |
| `I1-002` | Compose, redes e fake worker | `CONCLUIDA` | MatheusSchimieguelSilva | `task/I1-002-compose-worker` | 2026-08-22 14:26 -03:00 | — | `infra/**`, `services/agent-worker/**` | Integrada na `main` em `2cd3c65`; revisão em 2026-08-22 17:40 -03:00 com `docker compose config` válido, três serviços fixos `healthy`, `agent_net`/`control_net` internas, worker manual `exit 0` com callback `202`, 9 testes de infra/worker aprovados e testes negativos provando uid 10001, sem resolução de `postgres` e sem Docker socket. |
| `I1-003` | Painel React responsivo com mocks | `CONCLUIDA` | Nicolau Codex | `task/I1-003-painel-react` | 2026-08-22 14:05 -03:00 | — | `apps/control-panel/**` | Integrada na `main` em `0b3c6bc`; viewport mobile corrigido, 12 testes e build aprovados. |
| `I1-004` | PostgreSQL, event store e API de runs | `CONCLUIDA` | Arthur Monteiro | `task/I1-004-persistence-runs-api` | 2026-08-22 15:09 -03:00 | `I1-001` | `services/control-api/app/persistence/**`, `api/runs/**`, migrations | Integrada na `main` em `141be1a`; migration limpa corrigida em `d4bc54c`, 30 testes da API com PostgreSQL real, 13 regressões e codegen reproduzível em 2026-08-22 15:17 -03:00. |
| `I1-005` | ContainerRuntime e despacho do fake worker | `CONCLUIDA` | Arthur Monteiro | `task/I1-005-container-runtime` | 2026-08-22 15:23 -03:00 | `I1-001`, `I1-002`, `I1-004` | `services/control-api/app/runtime/**`, `orchestration/**` | Integrada na `main` em `4ac6d41` após revisão independente; 82 testes API/PostgreSQL, 18 do painel, typecheck/build e 15 de contratos/infra/worker com 21 subtestes aprovados. Fluxo Docker real concluiu o run, persistiu 6 eventos e removeu o worker efêmero em 2026-08-22 16:19 -03:00. |
| `I1-006` | SSE e integração da timeline | `CONCLUIDA` | MatheusSchimieguelSilva | `task/I1-006-sse-timeline` | 2026-08-22 15:26 -03:00 | `I1-003`, `I1-004` | endpoint SSE e integração de eventos no painel | Integrada na `main` em `d0b355d` após revisão independente; 39 testes API/PostgreSQL, 18 do painel, typecheck, build, 4 contratos e 9 worker/infra aprovados em 2026-08-22 16:07 -03:00. |
| `I1-007` | E2E da fatia distribuída e isolamento | `CONCLUIDA` | MatheusSchimieguelSilva | `task/I1-007-e2e-distributed-slice` | 2026-08-22 16:20 -03:00 | `I1-002`, `I1-005`, `I1-006` | `tests/e2e/**`, roteiro e wiring final em `infra/**`/container do painel | Integrada na `main` em `051661a` após aprovação; `./tests/e2e/run.sh` aprovado 2x em instalação isolada, com Chromium 390x844, seis eventos causais, retry sem duplicação, retomada SSE 4/5/6 e probe sem PostgreSQL/socket. Regressão: 82 API, 18 painel, typecheck/build e 17 contratos/infra/worker com 21 subtestes. |
| `I1-008` | Gateway real Claude/Codex e primeiro worker LLM | `EM_REVISAO` | Nicolau Codex | `task/I1-008-model-gateway` | 2026-08-22 16:21 -03:00 | `I1-005` | `services/control-api/app/model_gateway/**`, `api/internal/model-invocations`, worker LLM | Commit `ed142cc`; 123 testes do control-api + 4 do worker aprovados com PostgreSQL real; Claude/Codex selecionáveis por ambiente. |
| `I2-001` | Plano dos workers PO, Dev e QA | `EM_REVISAO` | Nicolau Codex | `task/I2-001-workers-plan` | 2026-08-22 16:34 -03:00 | `I1-008` | `plan.md` e detalhamento das tarefas I2 no quadro | Commit `2407789`; PO, Dev, QA, runner, toolchains, isolamento, gates e validação Trilha B especificados por subagentes. |

## Detalhamento e critérios de conclusão

### I1-001 — Contratos e scaffold do monorepo

Entrega:

- criar a estrutura mínima `apps/`, `services/`, `packages/`, `infra/` e `tests/` sem implementar
  as features das outras tarefas;
- versionar OpenAPI/JSON Schemas para `CreateRunRequest`, `RunResponse`, `EventEnvelope`,
  `AgentTaskContext` e `FakeWorkerOutput`;
- definir estados e transições usados nesta iteração;
- disponibilizar exemplos válidos e inválidos testáveis.

Concluída quando os schemas validam os exemplos, frontend e backend conseguem gerar/consumir o
mesmo contrato e nenhuma regra existe duplicada manualmente em Python e TypeScript.

### I1-002 — Compose, redes e fake worker

Entrega:

- criar serviços fixos `control-api`, `control-panel` e `postgres` no Compose, mesmo que API e
  painel ainda usem placeholders;
- declarar `public_net`, `control_net`, `agent_net`, healthchecks e volumes;
- criar imagem não-root do fake worker que recebe apenas `RUN_ID`, `TASK_ID`, URL e token;
- impedir o fake worker de receber `DATABASE_URL` ou Docker socket.

Concluída quando `docker compose config` é válido, PostgreSQL fica saudável e o fake worker pode
ser iniciado manualmente e chamar um endpoint stub da API pela `agent_net`.

### I1-003 — Painel React responsivo com mocks

Entrega:

- scaffold React + TypeScript + Vite;
- tela de envio único do briefing;
- resumo de execução e timeline usando mocks tipados do contrato;
- estados de carregamento, vazio, erro e reconexão;
- layout mobile-first.

Concluída quando build e testes do frontend passam e, em viewport de 320 px, não existe rolagem
horizontal da página; briefing, etapa atual e eventos permanecem legíveis.

### I1-004 — PostgreSQL, event store e API de runs

Entrega:

- migrations mínimas para `runs`, `events`, `agent_tasks` e `idempotency_keys`;
- transação que cria run, `BRIEFING_RECEIVED` e primeira task sem duplicação;
- `POST /api/v1/runs` e `GET /api/v1/runs/{run_id}`;
- persistência append-only e testes de idempotência;
- PostgreSQL acessível somente pelo `control-api`.

Concluída quando criar um run retorna `202`, repetir a idempotency key não duplica dados, eventos
possuem sequência/correlação/causa e os testes de integração passam em PostgreSQL real.

### I1-005 — ContainerRuntime e despacho do fake worker

Entrega:

- interface `ContainerRuntime` e implementação fake para testes do scheduler;
- implementação Docker SDK com allowlist de imagem, labels e limites básicos;
- scheduler que encontra task pendente, inicia fake worker e registra execução/exit code;
- callback autenticado do worker, validação do output e limpeza do container;
- side effects idempotentes por `task_id`.

Concluída quando uma task persistida inicia exatamente um container, o callback gera evento, um
retry não cria segunda execução ativa e o worker nunca recebe banco ou socket.

### I1-006 — SSE e integração da timeline

Entrega:

- `GET /api/v1/runs/{run_id}/events` em SSE;
- retomada usando o último `sequence` recebido;
- cliente real no painel para criação, resumo e timeline;
- reconexão sem perder ou duplicar eventos visíveis.

Concluída quando o painel acompanha um run real, uma desconexão simulada retoma do ponto correto e
frontend/backend passam em testes de contrato.

### I1-007 — E2E da fatia distribuída e isolamento

Entrega:

- teste ponta a ponta que envia briefing, cria task, lança fake worker, persiste callback e exibe
  o evento no painel;
- teste negativo provando que worker não alcança banco nem Docker socket;
- teste de retry/idempotência;
- instrução de execução local da fatia.

Concluída quando uma instalação limpa executa o fluxo com um comando documentado, todas as
evidências são reproduzíveis e a timeline prova a causalidade da execução.

## Ordem e paralelismo sugeridos

Primeira onda, em paralelo:

- uma pessoa em `I1-001`;
- uma pessoa em `I1-002`;
- havendo terceira pessoa, ela assume `I1-003`.

Segunda onda:

- `I1-004` começa após o contrato de `I1-001`;
- `I1-003` pode continuar em paralelo usando mocks;
- quem concluiu `I1-002` prepara `I1-005`, mas só implementa a integração depois de `I1-004`.

Terceira onda:

- `I1-005` e `I1-006` avançam em paralelo;
- `I1-007` integra a fatia e não deve absorver correções que pertencem às tarefas anteriores.

## Fora desta iteração

- chamadas reais a provedor LLM;
- workers reais de PO, Dev e QA;
- LangGraph completo do ciclo de stories;
- aplicação Rivexx gerada;
- autenticação do painel;
- AWS, MongoDB, Redis ou broker de mensagens.

Esses itens entram somente depois que `I1-007` provar a base distribuída.
