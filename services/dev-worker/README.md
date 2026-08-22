# Dev Worker local

Consome uma tarefa Dev já despachada pela API, chama o Codex de plano somente
através do gateway, materializa a aplicação em workspace isolado e publica
source/manifest e `dev-delivery`. Não recebe briefing e não executa testes.

```powershell
$env:RUN_ID='<uuid>'; $env:TASK_ID='<uuid>'; $env:TASK_TOKEN='<token>'
$env:CONTROL_API_URL='http://localhost:8000'
python services/dev-worker/dev_worker.py
```

O código gerado fica em `.generated-workspaces/<run>/<task>`. Os comandos
sugeridos pelo modelo são registrados no manifesto para execução exclusiva do QA.
