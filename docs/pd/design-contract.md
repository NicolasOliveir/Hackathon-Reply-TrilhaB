# Contrato de Design e Handoff

Use IDs estáveis e estruturas serializáveis para correlacionar story, critérios, telas, decisões e
implementação. O documento pode apontar para wireframes ou protótipos, mas não depende deles para
ser compreendido.

## Entrada mínima

```json
{
  "event_type": "STORY_ASSIGNED_TO_DESIGN",
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
  },
  "design_context": {
    "design_system_reference": null,
    "supported_viewports": [],
    "technical_constraints": []
  }
}
```

Ausência de `id`, `frozen_hash`, narrativa ou critérios impede o design. Ausência de design system
ou viewports não impede o trabalho: use o mínimo necessário e registre as hipóteses.

## Pacote de design

```json
{
  "event_type": "DESIGN_DELIVERED",
  "story_id": "NC-003",
  "story_hash": "sha256:...",
  "design_revision": 1,
  "experience_summary": {
    "user": "",
    "goal": "",
    "context": "mobile | tablet | desktop",
    "primary_action": ""
  },
  "flow": [
    {
      "step_id": "FLOW-1",
      "screen_id": "SCREEN-1",
      "trigger": "",
      "action": "",
      "result": "",
      "next_step_id": null
    }
  ],
  "screens": [
    {
      "id": "SCREEN-1",
      "name": "",
      "purpose": "",
      "acceptance_criteria": ["AC-1"],
      "content_hierarchy": [],
      "components": [
        {
          "id": "COMP-1",
          "type": "",
          "label": "",
          "properties": {},
          "states": ["default", "loading", "error", "disabled"],
          "accessibility": { "name": "", "description": "", "keyboard": "" }
        }
      ],
      "responsive_behavior": {
        "mobile": "",
        "tablet": "",
        "desktop": ""
      },
      "states": [
        { "name": "empty | loading | filled | validation | error | success", "trigger": "", "content": "", "available_action": "" }
      ]
    }
  ],
  "tokens": {
    "existing_references": [],
    "proposed": []
  },
  "assets": [],
  "design_decisions": [
    { "id": "DD-001", "context": "", "options": [], "decision": "", "consequence": "" }
  ],
  "criterion_coverage": [
    { "acceptance_criterion_id": "AC-1", "screen_ids": ["SCREEN-1"], "evidence_points": [] }
  ],
  "assumptions": [],
  "open_questions": [],
  "ready_for_development": true
}
```

`ready_for_development` só pode ser `true` quando todos os critérios possuem cobertura, nenhum
estado essencial está indefinido e `open_questions` não contém decisão de produto bloqueante.

## Handoff para Developer

O Developer deve receber a story congelada e o pacote de design correspondente ao mesmo
`story_hash`. Cada task visual ou de interação deve referenciar `screen_id`, `component_id` e os
critérios cobertos. Se o Developer precisar divergir por limitação técnica, deve registrar a
alternativa e devolver `DESIGN_CHANGE_REQUESTED`; não deve alterar silenciosamente o design.

## Evento de bloqueio

```json
{
  "event_type": "NEEDS_HUMAN",
  "story_id": "NC-003",
  "reason": "MISSING_PRODUCT_DECISION | CONTRADICTORY_ACCEPTANCE_CRITERIA | MISSING_CONTEXT | DESIGN_SYSTEM_CONFLICT",
  "details": "",
  "options": [
    { "option": "", "impact": "" }
  ]
}
```

## Verificação final

- Todos os critérios aparecem em `criterion_coverage`.
- Cada passo aponta para uma tela e cada componente interativo possui estados relevantes.
- Mobile, tablet e desktop têm comportamento descrito, não apenas dimensões.
- Acessibilidade está vinculada aos controles concretos.
- Hipóteses estão explícitas e não criam regras de negócio.
- Story e design preservam o mesmo `frozen_hash`.
