# control-api

Plano de controle do squad. Nesta iteração entrega PostgreSQL, event store
append-only, API de runs (`I1-004`), despacho de containers (`I1-005`) e
streaming SSE (`I1-006`).

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
│   ├── api/runs/               endpoints públicos de execução
│   ├── api/events/             stream SSE e serialização do EventEnvelope
│   ├── api/internal/           contexto e callback autenticado dos workers
│   ├── orchestration/          scheduler e ciclo de despacho
│   └── runtime/                adapters Docker e fake
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

## Stream de eventos

`GET /api/v1/runs/{run_id}/events` envia cada `EventEnvelope` como uma mensagem
SSE com `id` igual ao `sequence`. Uma reconexão informa o último cursor no
header `Last-Event-ID`; a consulta usa `sequence > cursor`, evitando perda e
duplicação. Heartbeats são comentários SSE e não aparecem na timeline.

O stream abre sessões curtas por lote. A conexão HTTP pode permanecer aberta
sem reter transação ou conexão PostgreSQL enquanto espera um evento novo.

Para a demonstração web/mobile, CORS permite qualquer origem porque o MVP não
usa cookies nem autenticação do painel. Restrinja por ambiente quando necessário:

```bash
CONTROL_PANEL_ORIGINS=http://localhost:5173,http://192.168.1.20:5173
```

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
2. faz get-or-create de `agent_executions` por `(task_id, attempt)`;
3. apenas em execução nova, emite o token de tarefa e grava só o hash;
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

## Preparado para as próximas tarefas

- `EventStore.list_events(run_id, after_sequence=...)` implementa a retomada do
  SSE por `Last-Event-ID`;
- `agent_executions` guarda container, imagem, exit code, motivo e logs para o
  E2E de `I1-007`;
- `agent_tasks` usa `available_at`, `locked_at` e `locked_by` no consumo com
  `FOR UPDATE SKIP LOCKED`;
- `agent_tasks.token_hash` guarda só o hash do token de tarefa;
- o estado terminal revoga acesso ao contexto; o hash é retido até o timeout
  somente para reconhecer uma repetição idempotente do mesmo callback;
- `app/main.py` registra juntos os routers público, interno e SSE.
