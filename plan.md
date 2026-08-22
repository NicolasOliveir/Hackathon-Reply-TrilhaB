# Plano de construção dos workers PO, Dev e QA

> Status: planejamento da Iteração 2
> Responsável pelo plano: Nicolau Codex
> Princípio: a plataforma gera N aplicações a partir do briefing. Rivexx é uma avaliação, nunca um produto hardcoded no orquestrador, nos prompts ou nos workers.

## 1. Resultado esperado

Ao receber um briefing, o plano de controle deve executar, sem intervenção humana intermediária:

```text
briefing
  -> PO Worker: backlog congelado e critérios observáveis
  -> Dev Worker: código, ADRs, commit e verificações
  -> QA Worker: plano e testes materializados
  -> Test Runner: execução determinística e evidências
  -> API: veredito, retry ou conclusão
```

A comunicação ocorre exclusivamente pela API central e deve aparecer na timeline com correlação, causalidade, hashes, contexto recebido e artefatos. Nenhum agente decide sozinho que uma story foi aceita.

## 2. Requisitos oficiais da Trilha B

O aceite final deve provar:

- no mínimo PO, Dev e QA com papéis distintos;
- colaboração explícita e auditável; uma aplicação final sem orquestração visível não atende;
- aplicação web local, responsiva e operável sem treinamento técnico;
- backlog gerado pelo PO;
- decisões técnicas justificadas pelo Dev;
- relatório do QA com casos executados e evidências;
- cadeia autônoma para registro ágil, causa raiz assistida e rastreabilidade de lote;
- registro auditável com data, responsável, turno e equipamento;
- rastreabilidade cobrindo matéria-prima, fornecedor, equipamento, turno, operadores e lotes correlatos.

Esses itens são a suíte de avaliação Rivexx. A generalidade será testada adicionalmente com briefings de domínios não industriais.

## 3. Estado atual e lacunas

A I1-008 fornece gateway auditável para Claude/Codex e um primeiro caminho `context -> modelo -> callback`. Ainda faltam:

- schemas executáveis de PO, Dev, QA, runner, artefatos e findings;
- projeções de backlog, ADRs e relatório QA;
- máquina de estados PO -> Dev -> QA -> runner com reprovação e reentrega;
- workspaces por execução e ArtifactStore;
- loop de ferramentas do Dev;
- QA planner e testes materializados;
- runner não-LLM e motor determinístico de veredito;
- ambiente efêmero da aplicação, healthchecks e browser;
- isolamento completo e evidências dos três cenários do hackathon.

O callback textual legado e `FAKE_WORKER_COMPLETED` não serão usados como contrato dos workers reais.

## 4. Ordem obrigatória

### Fase A - Fundação compartilhada

Congelar antes do paralelismo:

1. contratos JSON Schema/OpenAPI e exemplos válidos/inválidos;
2. eventos, estados, transições, retries e idempotência;
3. ArtifactStore e WorkspaceManager;
4. API de heartbeat, artifacts e failures;
5. perfis de ferramentas, mounts e rede do runtime.

Gate A: tipos Python/TypeScript gerados, testes de contrato aprovados e handoffs PO -> Dev -> QA -> runner imutáveis por hash.

### Fase B - Workers em paralelo

Depois do Gate A:

- PO Worker;
- Dev Worker e executor seguro de ferramentas;
- QA Worker e adapters de teste;
- runner determinístico e ambiente efêmero podem avançar junto ao QA, com área exclusiva separada.

### Fase C - Orquestração vertical

1. uma story completa até aceite;
2. reprovação real, finding, correção Dev e novo aceite;
3. múltiplas stories sequenciais;
4. retomada depois de reiniciar o control-api;
5. painel exibindo backlog, ADRs, testes, ferramentas e evidências.

### Fase D - Avaliação

1. três briefings neutros de domínios diferentes;
2. smoke real separado com Claude e Codex;
3. briefing Rivexx sem injetar os cenários da demo nos prompts;
4. auditoria independente contra este plano e o PDF.

## 5. PO Worker

### Contexto e limites

É o único agente que recebe o briefing bruto. Não recebe workspace, Git, shell, banco, Docker socket ou internet. Possui somente `context:read`, `model:invoke`, `heartbeat:write` e `output:write`.

### Saída

O schema versionado deve materializar `docs/PO/outputcontract.md`:

- stories, narrativa, prioridade e dependências;
- critérios binários, observáveis e ordenados;
- restrições, premissas, fora de escopo e cobertura;
- decisões e `needs_human`;
- hash congelado calculado pelo servidor.

### Pipeline

Validar contexto -> invocar structured output -> validar schema -> normalizar -> executar invariantes -> calcular hashes -> persistir backlog/eventos atomicamente -> criar tasks Dev apenas para stories prontas.

São permitidas até duas tentativas de reparo de JSON, sempre com erros por JSON Pointer. O PO não escolhe tecnologia, não escreve testes e não declara aceite.

### Gates PO

- isolamento do briefing e ausência de fixture embutida;
- schema, invariantes, dependências acíclicas e cobertura completos;
- callback idempotente e persistência atômica;
- resultados coerentes para três domínios neutros;
- convergência semântica para os três cenários Rivexx em três execuções.

## 6. Dev Worker

### Contexto e workspace

Recebe somente story congelada, critérios, instruções versionadas, ADRs autorizadas e findings da revisão atual. Nunca recebe briefing bruto.

Cada story/revisão usa workspace efêmero RW em `/workspace`, criado de snapshot imutável. Registra base hash, branch local, commit, diff e manifest. Não monta o checkout do host e não possui push, force push, `reset --hard`, Docker socket, banco ou credenciais.

### Ferramentas obrigatórias

- leitura e busca: `rg`, listagem e leitura limitada;
- edição estruturada: patch com bloqueio de path traversal e symlink escape;
- shell por argv estruturado, cwd confinado, timeout e limite de saída;
- Git local: status, diff, log, add e commit; publicação como artefato;
- Node/TypeScript: Node, Corepack, npm/pnpm, TypeScript, Vite e test runner declarado;
- Python: Python, ambiente isolado, pytest e ferramentas declaradas no projeto;
- build, lint, typecheck, testes unitários e integração;
- Playwright/Chromium para smoke de UI em 320 px e desktop;
- artefatos de stdout/stderr, screenshots, trace, manifest, patch e commit.

Dependências são instaladas de lockfile por registry/proxy allowlisted e auditado. Ferramentas de sistema não são instaladas durante o run.

### Loop

Validar story/hash -> detectar stack pelos manifests -> criar plano AC->task->verificação -> executar tool calls limitadas -> revisar diff -> build/test -> commit -> publicar `CODE_DELIVERED`. Reentrega começa do commit reprovado e referencia os findings.

O Dev registra ADR apenas para decisão arquitetural, com contexto, opções, escolha e consequência. Falha ou `NOT_RUN` nunca vira entrega pronta para QA.

### Gates Dev

- commit/patch reproduzível e confinado ao workspace;
- cada critério ligado a task e verificação;
- comandos, exit codes, duração e hashes auditados;
- build e testes reais nas stacks suportadas;
- nenhuma credencial, briefing, banco, socket ou acesso ao host;
- QA recebe exatamente o commit/manifest entregue, em leitura somente.

## 7. QA Worker e runner

### Separação de responsabilidades

O QA usa LLM para elaborar plano e materializar testes. O runner, sem LLM, executa comandos allowlisted. Somente a API deriva `ACCEPTED`, `REJECTED` ou `NEEDS_HUMAN`.

O QA recebe story congelada, revisão imutável, diff, manifests e verificações do Dev. Código é RO; testes e evidências usam volumes próprios. Não recebe briefing, banco, Docker, chaves ou workspace mutável do Dev.

### Ferramentas QA/runner

- Python: pytest, coverage, ruff/mypy quando declarados, Bandit e pip-audit;
- JS/TS: Vitest/Jest, ESLint, TypeScript e auditoria de dependências;
- API/contrato: httpx/pytest ou Newman e validação de schemas;
- E2E: Playwright Chromium, screenshots, trace, console e rede;
- mobile: 320, 375 e 390 px, portrait/landscape, overflow, ação primária e alvos de 44 x 44 px;
- acessibilidade: axe-core, teclado, foco, nomes/labels e contraste verificável;
- segurança: autorização, isolamento, XSS/injection, headers, secrets e dependências;
- healthchecks, logs, JUnit, coverage, axe/audit e hashes de artefatos.

Ferramenta ausente, stack desconhecida ou ambiente inconclusivo gera `NEEDS_HUMAN`, nunca PASS.

### Matriz e veredito

Cada critério gera ao menos um caso, preservando texto, ordem e hash:

```text
AC -> caso -> comando -> resultado -> evidence_ref
```

PASS exige healthchecks, hashes corretos, todos os casos obrigatórios executados uma vez, exit code zero, nenhuma falha/erro/timeout/skip obrigatório e evidências válidas. Um rerun é permitido apenas para classificar flakiness; passar somente no rerun continua bloqueado.

### Gates QA

`G0` contrato e manifest; `G1` rebuild e healthchecks; `G2` lint/typecheck/unit; `G3` integração/contrato; `G4` E2E; `G5` mobile; `G6` acessibilidade; `G7` segurança/isolamento; `G8` rastreabilidade/evidências; `G9` critérios completos do hackathon.

## 8. Segurança e recursos

Todos os containers são non-root, `cap_drop: ALL`, `no-new-privileges`, filesystem base RO, tmpfs limitado e quotas de CPU, RAM, PIDs, disco, tempo, tool calls, tokens e artefatos. Imagens são allowlisted e, quando possível, fixadas por digest.

O runtime bloqueia dispositivos, setuid, traversal, symlink escape, metadados cloud, host network, banco e Docker socket. Segredos nunca entram no modelo, workspace ou logs. Egress é negado por padrão; apenas API central e proxy de dependências explicitamente permitido.

## 9. Eventos e evidências mínimas

Timeline obrigatória:

- `STORY_FROZEN`;
- `DEV_TASK_PLAN_CREATED`;
- `ADR_RECORDED`;
- `TOOL_EXECUTED` com resumo sanitizado;
- `CODE_DELIVERED` ou `CODE_REDELIVERED`;
- `TEST_PLAN_CREATED`;
- `TEST_EXECUTED` pelo runner;
- `FINDING_RECORDED` quando houver;
- `STORY_ACCEPTED`, `STORY_REJECTED` ou `NEEDS_HUMAN`.

Artefatos grandes ficam fora do evento e são referenciados por tipo, URI autorizada, tamanho, MIME e SHA-256. Logs integrais são sanitizados.

## 10. Backlog de implementação e designação

| Ordem | Tarefa | Responsável designado | Dependências | Resultado verificável |
|---|---|---|---|---|
| 1 | `I2-002` Contratos, projeções e grafo dos workers | subagente `worker-contracts` | I1-008 revisada | schemas/codegen, estados, eventos e handoffs congelados |
| 2 | `I2-003` ArtifactStore, WorkspaceManager e runtime de ferramentas | subagente `worker-runtime` | I2-002 | mounts, quotas, executor seguro e testes de isolamento |
| 3 | `I2-004` PO Worker real | subagente `po-worker` | I2-002 | backlog válido, congelado, genérico e auditável |
| 4 | `I2-005` Dev Worker real | subagente `dev-worker` | I2-002, I2-003 | aplicação alterada, commitada, buildada e testada |
| 5 | `I2-006` QA Worker e adapters | subagente `qa-worker` | I2-002, I2-003 | plano/testes/evidências por critério |
| 6 | `I2-007` Test runner e motor de veredito | subagente `test-runner` | I2-002, I2-003, I2-006 | execução não-LLM determina aceite/reprovação |
| 7 | `I2-008` Orquestração, painel e ciclo de correção | subagente `worker-integration` | I2-004 a I2-007 | fluxo visível, retry e retomada |
| 8 | `I2-009` Validação Trilha B e auditoria independente | subagente `hackathon-audit` | I2-008 | relatório de conformidade e evidências dos três cenários |

Cada subagente só começa após reserva publicada no `TASKS.md`, usa branch `task/<ID>-<slug>` e respeita a área exclusiva definida. Contratos compartilhados não podem ser alterados pelas frentes PO/Dev/QA depois do Gate A sem coordenação explícita.

## 11. Subagentes usados neste planejamento

- `po_worker_design`: contrato, invariantes, generalidade e gates do PO;
- `dev_worker_design`: workspace, tool loop, toolchains, Git, build e segurança;
- `qa_worker_design`: matriz de critérios, adapters, browser/mobile/a11y/security e veredito.

Esses subagentes concluíram somente o desenho. Os subagentes de implementação da seção 10 serão criados depois que a tarefa correspondente estiver oficialmente reservada.

## 12. Definition of Done global

- `docker compose up --build` sobe o plano de controle;
- briefing dispara PO, Dev, QA e runner sem intervenção intermediária;
- os workers funcionam para briefings genéricos e não contêm entidades Rivexx;
- Dev produz código/ADRs e QA produz casos/evidências reais;
- runner quebrado de propósito reprova e retorna findings ao Dev;
- retry não duplica stories, tasks, eventos, commits ou artefatos;
- reinício do control-api retoma do último estado persistido;
- nenhum agente acessa banco, Docker socket, credencial de modelo ou contexto de outro papel;
- painel em 320 px mostra backlog, decisões, QA e timeline auditável;
- a aplicação gerada roda localmente e cobre os três cenários da Trilha B;
- uma auditoria independente confirma cada requisito com evento, teste e evidence_ref.
