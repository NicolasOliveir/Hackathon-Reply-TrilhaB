# PO worker

Container efêmero, non-root e sem workspace. Recebe exclusivamente o briefing pela API central,
invoca o gateway com `po-output.schema.json`, permite no máximo dois reparos e submete o backlog
com chave idempotente. Não contém regras ou entidades de um domínio específico.

Build a partir da raiz:

```bash
docker build -f services/po-worker/Dockerfile -t reply/po-worker:local .
```
