# Contratos

Os schemas canônicos vivem em `packages/contracts`, na branch da I1-001. Essa branch ainda não
está integrada em `main`, portanto não é possível importar ou gerar tipos sem adicionar arquivos
fora da área exclusiva desta tarefa. Os mocks usam `as const` e `MockEvent` é inferido diretamente
dos dados, evitando uma segunda definição manual do envelope.

Após a integração da I1-001, o próximo passo é adicionar o pacote como dependência workspace e
gerar `src/generated/contracts.ts` a partir de `packages/contracts/openapi/v1/openapi.yaml` (por
exemplo com `openapi-typescript`), substituindo o tipo inferido sem editar o contrato no painel.
