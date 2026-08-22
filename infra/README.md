# Infraestrutura local

O Compose mantém os serviços fixos do MVP e a imagem do `fake-worker`. O
`control-api` executa a aplicação real, aplica as migrations e usa o Docker do
host para criar workers efêmeros; `control-panel` serve o build React real em
Nginx.

## Serviços fixos

```bash
docker compose -f infra/compose.yaml config
docker compose -f infra/compose.yaml --profile manual build fake-worker
docker compose -f infra/compose.yaml up --build -d
docker compose -f infra/compose.yaml ps
```

- painel: <http://127.0.0.1:4173>;
- API: <http://127.0.0.1:8000/health>;
- PostgreSQL: acessível apenas por `control-api` na `control_net`.

Os valores padrão são exclusivamente locais. Defina `POSTGRES_PASSWORD`, `RUN_ID`, `TASK_ID` e
`TASK_TOKEN` no ambiente para substituí-los; não versione um arquivo `.env` real.

## Despacho do worker

Com os serviços fixos saudáveis, criar um run gera a task que o scheduler
consome. O `control-api` cria o container a partir da imagem já construída,
entrega somente as quatro variáveis autorizadas e recebe o callback pela
`agent_net`:

```bash
curl -i -X POST http://127.0.0.1:8000/api/v1/runs \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: local-demo-0001' \
  -d '{"contract_version":"1.0.0","briefing":"Validar a primeira fatia distribuída do orquestrador."}'
docker compose -f infra/compose.yaml logs control-api
```

O worker busca seu contexto autorizado e envia `FakeWorkerOutput` ao endpoint central. Ele entra
somente na `agent_net`, recebe quatro variáveis de tarefa e não possui banco, Docker socket,
capabilities Linux ou execução como root.

O mount `/var/run/docker.sock` concede ao `control-api` autoridade equivalente
à do daemon no host. Esta é uma decisão local explícita do MVP; o mount nunca é
propagado aos workers. Em uma evolução para AWS, este adapter será substituído
por uma API de execução gerenciada.

## Prova E2E isolada

Na raiz do repositório, `./tests/e2e/run.sh` constrói e testa toda a fatia em
um projeto Compose separado. Consulte `tests/README.md` para as evidências
verificadas.

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
