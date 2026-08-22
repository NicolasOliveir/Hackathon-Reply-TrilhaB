# Correção Orientada pelo QA

O retorno do QA é uma nova entrada da mesma story, não autorização para reinterpretar seu escopo. Preserve `story_id`, `story_hash` e a rastreabilidade até a revisão de implementação reprovada.

## Entrada mínima

```json
{
  "event_type": "QA_REJECTED",
  "story_id": "NC-003",
  "story_hash": "sha256:...",
  "implementation_revision": 1,
  "findings": [
    {
      "id": "QA-NC-003-01",
      "acceptance_criterion_id": "AC-2",
      "severity": "BLOCKER | MAJOR | MINOR",
      "expected": "",
      "actual": "",
      "reproduction_steps": [],
      "evidence": []
    }
  ]
}
```

Reprovação sem critério associado, resultado esperado, resultado observado ou reprodução suficiente deve ser devolvida como `QA_CLARIFICATION_REQUESTED`. Não presuma a intenção do QA.

## Fluxo de correção

1. Confirme que story, hash e revisão correspondem à entrega atual. Feedback obsoleto não deve ser aplicado sobre outra versão.
2. Classifique cada finding como `REPRODUCED`, `NOT_REPRODUCED`, `ALREADY_FIXED`, `OUT_OF_SCOPE` ou `BLOCKED` e anexe evidência.
3. Para findings reproduzidos, identifique a causa raiz antes de editar e crie uma task de correção vinculada ao finding e ao critério.
4. Faça a menor alteração que restaure o comportamento esperado sem relaxar o critério nem remover uma verificação válida.
5. Execute primeiro o teste de regressão específico e depois as verificações relacionadas que possam detectar efeitos colaterais.
6. Incremente `implementation_revision` e devolva o pacote de correção ao QA.

`OUT_OF_SCOPE` não encerra uma reprovação por decisão unilateral: emita `NEEDS_HUMAN` quando houver desacordo entre o relatório e a story.

## Saída da correção

```json
{
  "event_type": "CODE_REDELIVERED",
  "story_id": "NC-003",
  "story_hash": "sha256:...",
  "previous_implementation_revision": 1,
  "implementation_revision": 2,
  "remediations": [
    {
      "finding_id": "QA-NC-003-01",
      "acceptance_criterion_id": "AC-2",
      "status": "FIXED | NOT_REPRODUCED | ALREADY_FIXED | BLOCKED",
      "root_cause": "",
      "task_id": "NC-003-F1",
      "changed_files": [],
      "evidence": []
    }
  ],
  "regression_checks": [
    { "command": "", "exit_code": 0, "summary": "" }
  ],
  "known_limitations": [],
  "ready_for_qa": true
}
```

## Limite de iterações

Após três reprovações consecutivas do mesmo finding sem mudança de causa ou evidência nova, emita `NEEDS_HUMAN` com `RETRY_LIMIT_REACHED`. Findings novos iniciam sua própria contagem. Esse limite impede loop silencioso; ele não permite declarar a story aprovada.

## Verificação final

- Cada finding tem classificação e evidência.
- Cada correção está ligada a finding, task, critério e arquivos alterados.
- O teste que reproduzia a falha agora passa.
- Critérios anteriormente aprovados foram verificados contra regressão quando afetados.
- A nova entrega mantém exatamente o mesmo hash da story.
