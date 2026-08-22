# Fake agent worker

Worker efêmero da primeira fatia distribuída. Ele conhece somente sua tarefa e a API central:

- `RUN_ID`;
- `TASK_ID`;
- `CONTROL_API_URL`;
- `TASK_TOKEN`.

O processo consulta `/internal/v1/tasks/{task_id}/context`, verifica se o contexto pertence à
execução esperada e envia um `FakeWorkerOutput` para
`/internal/v1/tasks/{task_id}/outputs`. A chave de idempotência deriva do `task_id` e do hash do
contexto recebido.

A imagem usa UID/GID `10001`, não instala dependências durante a execução e não contém segredo,
credencial de banco ou cliente Docker. Limites adicionais são definidos pelo Compose.

Consulte [infra/README.md](../../infra/README.md) para executar o fluxo completo.
