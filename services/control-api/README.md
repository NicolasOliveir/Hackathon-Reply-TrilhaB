# control-api — I1-004

PostgreSQL, event store append-only e API de runs. Implementa a parte de persistência e
`/api/v1/runs` do [ORQUESTRADOR.md](../../docs/ORQUESTRADOR.md); o scheduler e o
`ContainerRuntime` são de `I1-005`, e o SSE é de `I1-006`.

## O que está aqui

| Caminho | Responsabilidade |
|---|---|
| `app/contracts/models.py` | Modelos Pydantic espelhando os JSON Schemas de `packages/contracts` |
| `app/contracts/state_machine.py` | Interpreta `state-machine/v1.json` — as transições não são reescritas em Python |
| `app/persistence/tables.py` | Schema `control`: `runs`, `events`, `agent_tasks`, `idempotency_keys` |
| `app/persistence/event_store.py` | Append com sequência por run, sem buraco e sem repetição |
| `app/persistence/idempotency.py` | Deduplicação de comando por `Idempotency-Key` |
| `app/services/run_service.py` | Transação única: run + 3 eventos + primeira tarefa |
| `app/api/runs.py` | `POST /api/v1/runs` (202) e `GET /api/v1/runs/{run_id}` |
| `migrations/` | Alembic; revisão `0001_initial` |

## Decisões

**SQLAlchemy async.** O `control-api` hospeda API, SSE (`I1-006`) e o loop do scheduler
(`I1-005`) no mesmo processo, conforme `ORQUESTRADOR.md` §4.1. Driver síncrono exigiria
threadpool para não bloquear o event loop do SSE.

**Sequência alocada por `UPDATE ... RETURNING` em `runs.last_sequence`.** Trava a linha da
run pelo resto da transação e serializa appends concorrentes sem tabela de contador
separada. Garante sequência sem buraco — requisito para a retomada por `Last-Event-ID`.

**Append-only garantido por trigger, não por convenção.** `control.events` recusa `UPDATE`
e `DELETE` no banco, valendo para qualquer cliente, inclusive `psql` manual. O log é o
artefato que o avaliador inspeciona; convenção de código não protege isso.

**As transições vêm do contrato, não do código.** `state_machine.py` lê
`packages/contracts/state-machine/v1.json`. Mudar a máquina de estados é mudar o contrato,
e o teste falha se divergirem.

**Briefing não entra no event log.** `BRIEFING_RECEIVED` grava `briefing_hash` e
`briefing_length`; o texto fica só em `runs.briefing`. O log é exibido no painel, e o
briefing só pode chegar ao nó do PO.

**Quatro tabelas, não dez.** As outras seis de `ORQUESTRADOR.md` §9.3 entram quando o fluxo
real PO → Dev → QA existir. Tabela vazia versionada antes do uso é schema não validado.

## Cadeia de causalidade de `POST /api/v1/runs`

```text
RUN_CREATED (seq 1, causation null)
   └─> BRIEFING_RECEIVED (seq 2)
          └─> TASK_QUEUED (seq 3, task_id) ──> RECEIVED → WORKER_QUEUED
```

`TASK_QUEUED` é o único dos três que move estado. `RUN_CREATED` e `BRIEFING_RECEIVED` são
registro — não aparecem como gatilho de transição no contrato.

## Rodar

```bash
python -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
```

Migrations, com o PostgreSQL de pé:

```bash
CONTROL_API_DATABASE_URL=postgresql+asyncpg://control:control@localhost:5432/control alembic upgrade head
```

API:

```bash
uvicorn app.main:app --reload --port 8000
```

## Testes

Contrato e máquina de estados rodam sem banco:

```bash
pytest tests/test_contract_models.py tests/test_state_machine.py
```

Integração exige PostgreSQL real, conforme o critério de conclusão de `I1-004`. Sem a
variável, os testes são **pulados com motivo explícito** — nunca passam em falso:

```bash
CONTROL_API_TEST_DATABASE_URL=postgresql+asyncpg://control:control@localhost:5432/control_test pytest
```

## Variáveis

| Variável | Padrão | Uso |
|---|---|---|
| `CONTROL_API_DATABASE_URL` | `postgresql+asyncpg://control:control@localhost:5432/control` | DSN do PostgreSQL — só o `control-api` recebe |
| `CONTROL_API_PUBLIC_BASE_URL` | `http://localhost:8000` | Base de `links.self` e `links.events` |
| `CONTROL_API_TASK_TIMEOUT_SECONDS` | `300` | Timeout gravado na tarefa enfileirada |
| `CONTRACTS_DIR` | resolvido pelo caminho do pacote | Sobrescreve a raiz de `packages/contracts` |

## Pendências para quem pegar I1-005 e I1-006

- `agent_tasks.token_hash` fica `NULL` até o despacho: o token efêmero só é emitido quando
  o container sobe.
- `event_store.list_events(after_sequence=...)` já suporta a retomada do SSE.
- `GET /health` não está no OpenAPI v1 de propósito — é sonda operacional do Compose, não
  superfície de agente. Se for para o contrato, entra por `I1-001`.
