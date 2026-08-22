# control-api

Plano de controle do squad. Nesta iteração entrega o que `I1-004` define:
PostgreSQL, event store append-only e a API de runs.

O `control-api` é o **único** serviço com credencial de banco. Containers de
agente não entram na `control_net` e nunca recebem `DATABASE_URL`.

## Estrutura

```text
services/control-api/
├── alembic.ini
├── docker-compose.test.yml     PostgreSQL só para teste (não substitui infra/)
├── migrations/                 schema control
├── app/
│   ├── main.py                 aplicação FastAPI
│   ├── config.py               settings via ambiente
│   ├── db.py                   engine e sessão async
│   ├── contracts/v1/           modelos GERADOS — não editar à mão
│   ├── persistence/            models, event store, idempotência, casos de uso
│   └── api/runs/               endpoints públicos de execução
└── tests/
```

## Contratos

Os modelos Pydantic em `app/contracts/v1/` são **gerados** de
`packages/contracts/schemas/v1/`. Nenhuma regra de validação — pattern, enum,
`minLength`, `required` — é reescrita em Python.

```bash
make contracts-codegen
```

`tests/test_contract_shape.py` faz round-trip dos exemplos versionados pelos
modelos gerados: se um schema mudar sem regenerar, o teste falha.

A máquina de estados tem o mesmo tratamento — `app/persistence/state_machine.py`
lê `packages/contracts/state-machine/v1.json` em vez de repetir as transições.

## Rodando

```bash
pip install -e ".[control-api-dev]"
make api-db-up
make api-migrate
make api-test
make api-run
```

Sem PostgreSQL alcançável, os testes de integração são **pulados com motivo
explícito**; os unitários e de contrato continuam rodando.

## Decisões desta entrega

**Append-only é do banco, não do código.** A migration instala um trigger que
recusa `UPDATE` e `DELETE` em `control.events`. Sem ele, "append-only" seria
apenas uma promessa: um `UPDATE` direto reescreveria a auditoria que o avaliador
vai inspecionar.

**A sequência vive na linha do run.** `runs.last_sequence` é incrementado com a
linha travada por `SELECT ... FOR UPDATE`. Isso serializa a numeração por
execução sem lock de tabela e sem retry otimista, e mantém
`uq_events_run_id_sequence` como rede de segurança.

**Transição é validada antes de gravar.** Como a tabela é append-only, um evento
que descreve uma transição impossível corromperia a auditoria de forma
permanente — não haveria como corrigir depois.

**O briefing bruto não entra no event log.** `BRIEFING_RECEIVED` carrega hash e
tamanho; o texto vive só em `runs.briefing`. O log é projetado no painel, e o
briefing precisa entrar em exatamente um nó.

**Idempotência tem escopo.** O mesmo header `Idempotency-Key` é exigido em
`POST /api/v1/runs` e em `POST /internal/v1/tasks/{task_id}/outputs`. A unique
key é `(scope, key)`, senão uma colisão entre os dois endpoints faria um comando
responder com o resultado do outro.

## Despacho de container (I1-005)

O scheduler (`app/orchestration/scheduler.py`) executa uma tentativa assim:

1. reivindica uma `agent_task` com `FOR UPDATE SKIP LOCKED`;
2. emite o token de tarefa e grava só o hash;
3. get-or-create de `agent_executions` por `(task_id, attempt)`;
4. `create` do container — o `container_id` precisa existir antes do `start`;
5. grava `AGENT_STARTED` e **commita**;
6. `start`, `wait`, registro do exit code, remoção do container.

**Por que `create` e `start` são separados.** `AGENT_STARTED` é gravado entre os
dois. Se o container subisse antes do evento, o callback do worker poderia
chegar antes do registro que o explica, e o log ficaria com um efeito sem causa.

**O veredito não é do container.** `FAKE_WORKER_COMPLETED` vem do callback
validado em `/internal/v1/tasks/{task_id}/outputs`; o exit code é evidência
complementar. Um container que sai com `0` sem ter chamado de volta **não**
conclui o run.

**O worker recebe quatro variáveis e nada mais.** `ContainerSpec` recusa
`DATABASE_URL`, `DOCKER_HOST` e `POSTGRES_PASSWORD` na construção — vazamento
vira exceção, não achado de revisão. O socket do Docker é tocado apenas por
`app/runtime/docker_runtime.py`.

**Idempotência por tentativa.** A unique `(task_id, attempt)` em
`agent_executions` impede que a retomada de um nó suba um segundo container
para a mesma tentativa.

### Runtime selecionável

`RUNTIME_BACKEND=docker` (padrão) ou `fake`. O runtime fake reproduz allowlist,
proibição de variável de plano de controle, `container_id` antes do start e
simulação de saída não-zero, timeout e callback — o que permite testar o
despacho inteiro sem daemon.

### Variáveis

| Variável | Padrão | Uso |
|---|---|---|
| `RUNTIME_BACKEND` | `docker` | `docker` ou `fake` |
| `FAKE_WORKER_IMAGE` | `rivexx/fake-worker:local` | imagem do worker |
| `RUNTIME_IMAGE_ALLOWLIST` | — | imagens extras permitidas |
| `AGENT_NETWORK` | `rivexx-squad_agent_net` | rede interna dos agentes |
| `INTERNAL_BASE_URL` | `http://control-api:8000` | URL que o worker recebe |
| `SCHEDULER_ENABLED` | desligado | sobe o laço junto com a aplicação |
| `WORKER_MEMORY_LIMIT` / `WORKER_CPU_LIMIT` / `WORKER_PIDS_LIMIT` | `128m` / `0.5` / `64` | limites do container |

O laço fica **desligado por padrão**: um scheduler que sobe em cada worker do
Uvicorn criaria vários consumidores competindo pela mesma fila.

## Gateway de modelo (I1-008)

Implementa `LLM-01` do `ORQUESTRADOR.md:424` — *"chave fica só na API e uso gera
metadados no evento"*.

**Por que o gateway é obrigatório, não estilístico.** A `agent_net` é
`internal: true`: o container de agente **não alcança** a internet nem o
provedor. A única saída é `POST /internal/v1/tasks/{task_id}/model-invocations`,
e a credencial vive só neste processo. É a forma mecânica de cumprir o
`ORQUESTRADOR.md §16` — *"agentes não acessam diretamente internet ou provedor
LLM"*.

### Provedores

| Provedor | Como fala | Credencial |
|---|---|---|
| `anthropic` | SDK oficial `anthropic` (`AsyncAnthropic`), `claude-opus-5`, pensamento adaptativo | `ANTHROPIC_API_KEY` ou perfil `ant auth login` |
| `codex` | binário `codex exec --output-schema`, sandbox `read-only` | sessão do ChatGPT em `~/.codex/` |
| `echo` | determinístico, sem rede | nenhuma |

Os três implementam a mesma porta (`app/model_gateway/base.py`). Trocar de
provedor não muda o gateway, a auditoria nem o contrato do agente.

O `echo` não é mock de conveniência: respeita o contrato inteiro, inclusive
`output_schema` e contabilidade de uso. É o que roda em CI, que não pode depender
de credencial nem gastar token.

### Roteamento por papel

Cada papel tem exigência diferente: o QA julga critério contra evidência —
errar ali libera código quebrado — enquanto o `fake` só ecoa. `MODEL_ROUTES`
sobrescreve por papel, e a rota escolhida entra na auditoria em vez de ficar
escondida em configuração.

```bash
MODEL_PROVIDER=anthropic
MODEL_PROVIDERS=anthropic,codex
MODEL_ROUTES='{"qa":{"provider":"anthropic","model":"claude-opus-5","effort":"xhigh"}}'
```

### Auditoria

`control.model_invocations` guarda provedor, modelo, esforço, tokens, latência,
motivo da rota e erro — **inclusive das invocações que falharam**, porque uma
invocação sem linha na auditoria seria um gasto invisível.

O **prompt não é persistido em claro**: ele pode conter o briefing, e a tabela é
projetada no painel. Fica o hash e o tamanho — mesma regra que mantém o briefing
fora do event log.

O agregado por tarefa entra no `meta` do evento de conclusão, que é o campo que
o `EventEnvelope` já reserva para `model`, `tokens_in`, `tokens_out` e
`latency_ms`.

### Escopo `model:invoke`

Concedido por papel em `ROLE_SCOPES` (`app/config.py`), não por padrão. O papel
`fake` **não** o recebe e leva 403 no gateway. Emissor de token e endpoint leem
da mesma tabela, então um papel nunca recebe token com escopo que o endpoint
depois recusa.

## Preparado para as próximas tarefas

- `EventStore.list_events(run_id, after_sequence=...)` é o contrato de retomada
  do SSE (`Last-Event-ID`) que `I1-006` vai usar;
- `agent_executions` guarda container, imagem, exit code, motivo e logs para o
  E2E de `I1-007`;
- `app/main.py` registra routers sem que `I1-006` precise alterar mais que a
  linha de inclusão.
