# Contrato do Plano de Testes do QA

Este contrato complementa a projeção `STORY_FROZEN` do
[PO](../PO/outputcontract.md#4-projeção-story_frozen) e a entrega
`CODE_DELIVERED` do [Dev](../dev/task-contract.md#pacote-de-entrega-ao-qa).
Ele respeita a arquitetura definida em [ORQUESTRADOR.md](../ORQUESTRADOR.md):
workers falam somente com a API; somente a API acessa PostgreSQL e decide
transições de estado.

## Fluxo

```text
PO -> API: STORY_FROZEN
Dev -> API: CODE_DELIVERED | CODE_REDELIVERED
API -> QA: contexto filtrado (story + entrega + manifestos autorizados)
QA -> API: configuração JSON + TEST_PLAN_CREATED + findings, se houver
API -> ArtifactStore / banco: arquivo, hash, metadados e evento
API / ContainerRuntime -> ambiente isolado: rivexx-api + rivexx-web + healthchecks
API -> runner: endpoints internos, plano e testes materializados, somente leitura
Runner -> API: TEST_EXECUTED
API -> sistema: STORY_ACCEPTED | STORY_REJECTED
```

Em uma redelivery, a API entrega ao QA o código da nova revisão e o plano JSON
anterior como artefato de referência. O QA cria uma nova revisão de plano
somente se os critérios, o ambiente ou a implementação exigirem isso; a story e
seu `frozen_hash` nunca mudam durante esse ciclo.

## Entrada autorizada do QA

O contexto interno da tarefa contém a projeção plana do PO, sem briefing,
`origem`, narrativa ou decisões de negócio. A API inclui a revisão do Dev e um
`context_manifest` com os hashes das fontes recebidas.

```json
{
  "story_id": "US-001",
  "version": 1,
  "frozen_hash": "sha256:...",
  "criterios_aceite": [
    {
      "id": "AC-1",
      "texto": "critério canônico do PO",
      "verificavel_por": "ui",
      "verifica_restricao": "R1"
    }
  ],
  "code_delivery": {
    "event_type": "CODE_DELIVERED",
    "implementation_revision": 1,
    "ready_for_qa": true,
    "changes": [],
    "verification_runs": []
  },
  "previous_test_configuration": null,
  "context_manifest": []
}
```

O QA bloqueia a preparação com `NEEDS_HUMAN` se faltar `story_id`, `version`,
`frozen_hash`, um critério, a revisão da entrega ou se os hashes do manifesto
não conferirem. Não consulta o banco diretamente.

## Arquivo de configuração de testes

Para cada plano, o QA produz um arquivo JSON em
`tests/config/<story-id>.v<version>.r<implementation-revision>.json`. O arquivo
é um artefato de configuração, não código Python, JavaScript ou shell. O runner
o interpreta com seus adaptadores permitidos e executa apenas os testes
materializados a partir dele.

O template válido está em
[../../tests/test-plan.template.json](../../tests/test-plan.template.json).
Cada critério da story deve gerar exatamente um item em
`acceptance_criteria`, preservando ID, texto e ordem. Um item pode ter um ou
mais `test_cases`, mas nenhum caso pode apontar para critério inexistente.

```json
{
  "schema_version": "1.0",
  "kind": "QA_TEST_CONFIGURATION",
  "test_plan_id": "QA-US-001-V1-R1",
  "story_id": "US-001",
  "story_version": 1,
  "frozen_hash": "sha256:...",
  "implementation_revision": 1,
  "acceptance_criteria": [
    {
      "id": "AC-1",
      "text": "critério canônico do PO",
      "mode": "ui",
      "test_cases": [
        {
          "id": "TC-US-001-AC-1-01",
          "preconditions": [],
          "steps": [],
          "expected": "resultado observável",
          "evidence_types": ["screenshot"]
        }
      ]
    }
  ],
  "environment": {
    "rebuild_on_manifest_change": true,
    "manifest_paths": [],
    "runner_profile": "default"
  }
}
```

Antes de submeter o arquivo, o QA confere que os IDs e a ordem de
`acceptance_criteria` são idênticos aos de `criterios_aceite` recebidos. A API
calcula e persiste o `test_plan_hash`, registra o artefato e só então aceita a
saída de domínio `TEST_PLAN_CREATED`.

## Saída do QA e do runner

O QA submete `TEST_PLAN_CREATED` e, se houver falha de comportamento observada,
findings técnicos vinculados ao critério. Ele não submete `TEST_EXECUTED`,
`STORY_ACCEPTED` nem `STORY_REJECTED`.

Após persistir o plano, a API manda o `ContainerRuntime` subir o frontend e
backend da revisão e aguardar seus healthchecks. O runner recebe os endpoints
internos desse ambiente, o arquivo JSON e os testes materializados como mounts
somente leitura. Ele submete `TEST_EXECUTED` com `story_id`, `version`,
`frozen_hash`, `implementation_revision`, `test_plan_id`, `test_plan_hash`, exit
code, resultado por caso e referências de evidência. A API deriva o aceite ou a
reprovação a partir dessa saída estruturada e encerra o ambiente efêmero.
