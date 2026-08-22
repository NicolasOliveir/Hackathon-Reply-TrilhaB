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
