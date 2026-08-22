# Infraestrutura local

O Compose mantém os serviços fixos do MVP e uma execução manual do `fake-worker`. O
`control-api` e o `control-panel` usam placeholders mínimos até as implementações próprias serem
integradas.

## Serviços fixos

```bash
docker compose -f infra/compose.yaml config
docker compose -f infra/compose.yaml up --build -d
docker compose -f infra/compose.yaml ps
```

- painel: <http://127.0.0.1:4173>;
- API stub: <http://127.0.0.1:8000/health>;
- PostgreSQL: acessível apenas por `control-api` na `control_net`.

Os valores padrão são exclusivamente locais. Defina `POSTGRES_PASSWORD`, `RUN_ID`, `TASK_ID` e
`TASK_TOKEN` no ambiente para substituí-los; não versione um arquivo `.env` real.

## Prova manual do worker

Com os serviços fixos saudáveis:

```bash
docker compose -f infra/compose.yaml --profile manual build fake-worker
docker compose -f infra/compose.yaml --profile manual run --rm fake-worker
docker compose -f infra/compose.yaml logs control-api
```

O worker busca seu contexto autorizado e envia `FakeWorkerOutput` ao endpoint central. Ele entra
somente na `agent_net`, recebe quatro variáveis de tarefa e não possui banco, Docker socket,
capabilities Linux ou execução como root.

Para encerrar e preservar os dados do PostgreSQL:

```bash
docker compose -f infra/compose.yaml down
```

Use `down --volumes` apenas quando quiser apagar explicitamente os dados locais.

## Verificações sem daemon Docker

```bash
python3 -m unittest discover -s infra/tests -p 'test_*.py' -v
python3 -m unittest discover -s services/agent-worker/tests -p 'test_*.py' -v
```

Os testes estáticos não substituem o smoke test com `docker compose`, mas validam a topologia,
as fronteiras de rede, os mounts e o conjunto de variáveis entregue ao worker.
