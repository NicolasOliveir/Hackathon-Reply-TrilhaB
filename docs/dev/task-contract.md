# Contrato de Tasks e Entrega

Use estruturas serializáveis e IDs estáveis para que o event log consiga correlacionar planejamento, código, verificações e retorno do QA.

## Entrada mínima: story atribuída

```json
{
  "event_type": "STORY_ASSIGNED",
  "story": {
    "id": "NC-003",
    "version": 1,
    "frozen_hash": "sha256:...",
    "titulo": "",
    "narrativa": { "como": "", "quero": "", "para": "" },
    "criterios_aceite": [
      { "id": "AC-1", "texto": "", "verificavel_por": "ui | dados | api" }
    ],
    "restricoes_aplicaveis": [],
    "depende_de": []
  }
}
```

Ausência de `id`, `frozen_hash` ou critérios de aceite impede o desenvolvimento.

## Plano de tasks

```json
{
  "story_id": "NC-003",
  "story_hash": "sha256:...",
  "tasks": [
    {
      "id": "NC-003-T1",
      "titulo": "",
      "resultado": "Comportamento ou artefato concreto produzido",
      "criterios_cobertos": ["AC-1"],
      "depende_de": [],
      "areas_afetadas": ["frontend", "backend", "dados", "testes"],
      "verificacao": ["comando ou inspeção planejada"],
      "estado": "PENDING | IN_PROGRESS | DONE | BLOCKED"
    }
  ],
  "coverage": [
    { "acceptance_criterion_id": "AC-1", "task_ids": ["NC-003-T1"] }
  ],
  "riscos": [],
  "bloqueios": []
}
```

Uma task deve produzir um resultado verificável, não apenas atividades vagas como “fazer backend”. A cobertura é inválida se algum critério não possuir task associada.

## ADR técnica

Registre uma ADR quando a escolha afetar arquitetura, dados, segurança, dependências ou manutenção futura.

```json
{
  "event_type": "ADR_RECORDED",
  "story_id": "NC-003",
  "adr": {
    "id": "ADR-DEV-001",
    "titulo": "",
    "contexto": "",
    "opcoes_consideradas": [
      { "opcao": "", "vantagens": [], "desvantagens": [] }
    ],
    "decisao": "",
    "justificativa": "",
    "consequencias": []
  }
}
```

## Pacote de entrega ao QA

```json
{
  "event_type": "CODE_DELIVERED",
  "story_id": "NC-003",
  "story_hash": "sha256:...",
  "implementation_revision": 1,
  "tasks": [
    { "id": "NC-003-T1", "estado": "DONE", "arquivos_alterados": [] }
  ],
  "changes": [
    { "path": "", "summary": "", "task_ids": ["NC-003-T1"] }
  ],
  "acceptance_evidence": [
    {
      "acceptance_criterion_id": "AC-1",
      "evidence_type": "test | command | screenshot | inspection",
      "reference": "caminho, comando ou identificador",
      "result": "PASS | FAIL | NOT_RUN"
    }
  ],
  "verification_runs": [
    { "command": "", "exit_code": 0, "summary": "" }
  ],
  "adrs": [],
  "known_limitations": [],
  "ready_for_qa": true
}
```

`ready_for_qa` só pode ser `true` quando não há task obrigatória bloqueada e nenhuma evidência conhecida com resultado `FAIL`. `NOT_RUN` deve conter a razão em `known_limitations`.

## Evento de bloqueio

```json
{
  "event_type": "NEEDS_HUMAN",
  "story_id": "NC-003",
  "reason": "MISSING_PRODUCT_DECISION | CONTRADICTORY_ACCEPTANCE_CRITERIA | ENVIRONMENT_BLOCKED | RETRY_LIMIT_REACHED",
  "details": "",
  "options": [
    { "option": "", "impact": "" }
  ]
}
```
