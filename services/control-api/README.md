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

## Preparado para as próximas tarefas

- `agent_tasks` tem `available_at`, `locked_at` e `locked_by` para `I1-005`
  consumir com `FOR UPDATE SKIP LOCKED` sem alterar o schema;
- `agent_tasks.token_hash` guarda só o hash do token de tarefa;
- `EventStore.list_events(run_id, after_sequence=...)` é o contrato de retomada
  do SSE (`Last-Event-ID`) que `I1-006` vai usar;
- `app/main.py` registra routers sem que `I1-005` e `I1-006` precisem alterar
  mais que a linha de inclusão.
