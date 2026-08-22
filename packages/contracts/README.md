# Contratos compartilhados

Fonte única dos envelopes trocados entre painel, API central, scheduler e workers. Os contratos
de domínio vivem como JSON Schema Draft 2020-12; o OpenAPI 3.1 apenas os referencia.

## Layout

```text
packages/contracts/
├── schemas/v1/          JSON Schemas canônicos
├── openapi/v1/          superfície HTTP da primeira iteração
├── state-machine/       estados e transições determinísticas
├── examples/v1/         casos válidos e inválidos
└── tests/               validação de schemas, exemplos, refs e transições
```

## Versão

`VERSION` usa versionamento semântico:

- patch: documentação ou exemplo sem mudança de validação;
- minor: campo opcional ou novo evento compatível;
- major: campo removido, obrigatório novo, enum restrito ou semântica alterada.

Cada run e evento informa `contract_version`. Consumidores devem rejeitar major incompatível em
vez de interpretar o payload parcialmente.

## Verificação

Instale as dependências opcionais e execute:

```bash
python3 -m pip install -e '.[contracts]'
make contracts-check
```

Os testes validam cada schema, todos os exemplos do manifesto, referências locais do OpenAPI e a
deterministicidade da máquina de estados.

## Consumo

- Python: carregar os schemas ou gerar modelos a partir de `openapi/v1/openapi.yaml`;
- TypeScript: gerar cliente/tipos a partir do mesmo OpenAPI;
- runtime: validar requests e callbacks contra o schema canônico antes de persistir eventos.

Modelos gerados podem existir dentro de cada consumidor, mas nunca são editados manualmente. Uma
mudança começa no JSON Schema/OpenAPI, atualiza exemplos e testes e só então regenera consumidores.

## Fluxo dos workers

Os handoffs reais usam os seguintes documentos imutáveis:

- `po-output`: backlog completo produzido a partir do briefing;
- `po-dev-handoff`: uma story pronta, o hash do backlog e os hashes das instruções;
- `dev-delivery`: commit, manifest, verificações e artefatos entregues;
- `qa-test-plan`: casos executáveis ligados aos critérios de aceite;
- `runner-result`: resultados e veredito derivados pelo runner não-LLM.

O servidor deve validar o JSON Schema e depois as invariantes de `worker_contracts.py`. O hash é
SHA-256 do JSON UTF-8 canônico (`sort_keys`, sem espaços e sem NaN), prefixado por `sha256:`. Só
stories `ready` geram handoff PO -> Dev. IDs, dependências, cobertura e ordem dos critérios são
validados antes de emitir `STORY_FROZEN`. Depois que todos os handoffs foram persistidos, a API
emite `PO_COMPLETED`; somente então a máquina libera `STORY_READY` para o Dev.

`state-machine/worker-flow-v1.json` congela o caminho PO -> Dev -> QA -> runner, incluindo a volta
determinística de `STORY_REJECTED` para `CODE_REDELIVERED`. Eventos grandes carregam apenas refs
de artefatos; conteúdo e evidências são conferidos pelos hashes dos envelopes.
