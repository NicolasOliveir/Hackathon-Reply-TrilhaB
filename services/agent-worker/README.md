# Agent worker

Worker efêmero do orquestrador. Ele conhece somente sua tarefa e a API central:

- `RUN_ID`;
- `TASK_ID`;
- `CONTROL_API_URL`;
- `TASK_TOKEN`.

O processo consulta `/internal/v1/tasks/{task_id}/context`, verifica se o contexto pertence à
execução esperada e, para os papéis `llm`, `po`, `dev` e `qa`, chama
`/internal/v1/tasks/{task_id}/model-invocations`. Essa chamada chega ao provedor pelo
`control-api`; o worker nunca recebe chave de Claude/Codex nem acesso direto à internet.

Ao terminar, envia o resultado para
`/internal/v1/tasks/{task_id}/outputs`. A chave de idempotência deriva do `task_id` e do hash do
contexto recebido.

O papel `fake` permanece disponível somente para CI e diagnóstico local. Quando
`MODEL_PROVIDER` é diferente de `echo`, o primeiro papel passa automaticamente a `po`; também é
possível selecionar explicitamente com `INITIAL_TASK_ROLE`.

A imagem usa UID/GID `10001`, não instala dependências durante a execução e não contém segredo,
credencial de banco ou cliente Docker. Limites adicionais são definidos pelo Compose.

Consulte [infra/README.md](../../infra/README.md) para executar o fluxo completo.
