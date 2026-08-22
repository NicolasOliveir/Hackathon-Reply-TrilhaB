# SPEC — Squad Autônomo de Agentes · Projeto Rivexx

> **Status do documento:** rascunho colaborativo
> **Última atualização:** 2026-08-22 — arquitetura do orquestrador MVP e divisão de trabalho
> **Regra:** nada aqui é decidido até estar marcado `DECIDIDO`. Toda mudança em seção `DECIDIDO` vira ADR nova, não edição silenciosa.
> **Leitura do enunciado, superfície de ataque do avaliador e estado das respostas:** [ENTENDIMENTO.md](ENTENDIMENTO.md) — análise, não decisão.

---

## Como trabalhar neste documento

| Marcador | Significado |
|---|---|
| `DECIDIDO` | Fechado. Só muda via ADR nova registrada na seção 4. |
| `ABERTO` | Precisa de decisão. Tem dono e prazo. |
| `BLOQUEADO` | Depende de outra decisão. Aponta a dependência. |
| `TODO` | Trabalho de escrita pendente, sem decisão envolvida. |

Convenção de PR: uma seção por PR. Título `spec: <seção>`. Discussão fica no PR, não em thread paralela.

---

## 1. Contexto

**Cliente da simulação:** Rivexx Componentes — indústria de componentes plásticos de alta precisão. 2 plantas, 480 colaboradores, 3 turnos, auditoria trimestral, fornecimento automotivo e eletroeletrônico.

**Problema declarado no briefing:** não conformidades disparam investigação manual; informação espalhada em papel, planilha e memória; reconstituição de histórico leva horas; causa raiz vira opinião; plano de ação não é monitorado; impossível responder rapidamente quais lotes foram afetados.

**O que se pede:** aplicação web interna com registro de NC, análise de causa raiz estruturada, planos de ação monitorados e rastreabilidade de lote ponta a ponta.

**Restrições do cliente (transversais, valem para toda story):**

| ID | Restrição | Como se verifica |
|---|---|---|
| `R1` | Aplicação responsiva (registro pelo celular no chão de fábrica) | em 320 px, fluxos P0 não têm rolagem horizontal e ações permanecem visíveis |
| `R2` | Interface operável sem treinamento técnico | fluxos P0 têm labels textuais, uma ação primária visível por etapa e erros junto ao campo, sem depender de manual externo |
| `R3` | Todo registro com evidência auditável (data, responsável, turno, equipamento) | persistência e tela exibem os quatro campos, que não podem ser alterados após salvar |
| `R4` | Rastreabilidade de lote em toda a cadeia produtiva | consulta do lote seed retorna matéria-prima, fornecedor, equipamento, turno, operadores e lotes correlatos |

> ⚠️ Restrição sem meio de verificação é decoração. Preencher a coluna direita é pré-requisito para o QA Agent existir de verdade.

As verificações acima são os alvos objetivos do MVP. O guia
[acceptancecriteria.md](PO/acceptancecriteria.md) orienta como o PO deve transcrevê-las para
critérios canônicos das stories aplicáveis.

---

## 2. O que estamos entregando

Mapeamento entregável → artefato no repo.

| Entregável exigido | Onde vive | Gerado por | Status |
|---|---|---|---|
| Squad funcional com comunicação visível | `/services` + `/apps/control-panel` | humano (plataforma) | `TODO` |
| Aplicação web rodando localmente, 3 cenários | `/workspace-template` + volume da execução | Dev Agent (features) | `TODO` |
| Backlog do PO Agent | projeção do event log | PO Agent | `TODO` |
| Log de decisões técnicas | projeção do event log | Dev Agent | `TODO` |
| Relatório de QA com evidências | projeção do event log | QA Agent + runner | `TODO` |

**Princípio:** os três últimos são *views* sobre o mesmo event log. Não são arquivos mantidos à mão.

### 2.1 Artefatos de definição dos agentes

O contrato entre agentes pertence a esta especificação. Prompts, personas e instruções
operacionais ficam próximos de cada agente e devem implementar esse contrato, sem redefini-lo.

| Artefato atual | Responsabilidade | Status |
|---|---|---|
| [`docs/PO/persona.md`](PO/persona.md) | missão, autoridade e limites de contexto do PO | rascunho avançado |
| [`docs/PO/SKILL.md`](PO/SKILL.md) | procedimento de decomposição do briefing | rascunho avançado |
| [`docs/PO/acceptancecriteria.md`](PO/acceptancecriteria.md) | regras para critérios de aceitação verificáveis | rascunho avançado |
| [`docs/dev/persona.md`](dev/persona.md) | missão, autoridade e limites de contexto do Dev | rascunho avançado |
| [`docs/dev/SKILL.md`](dev/SKILL.md) | implementação de story e entrada de remediação | rascunho avançado |
| [`docs/dev/task-contract.md`](dev/task-contract.md) | tasks, ADR e pacote de entrega | rascunho avançado |
| [`docs/dev/qa-remediation.md`](dev/qa-remediation.md) | protocolo de correção após reprovação | rascunho avançado |
| [`docs/QA/persona.md`](QA/persona.md) | missão, autoridade e limites de contexto do QA | rascunho avançado |
| [`docs/QA/SKILL.md`](QA/SKILL.md) | planejamento, execução e feedback de validação | rascunho avançado |
| [`docs/QA/acceptance.md`](QA/acceptance.md) | referência inicial dos três cenários Rivexx | rascunho avançado |

Os artefatos do PO implementam o contrato desta ESPEC; em caso de divergência, a ESPEC prevalece.

`docs/PO` e `docs/dev` são as fontes de design dos agentes. O runtime deverá carregar esses
artefatos diretamente ou empacotá-los de forma automatizada; não deve existir uma segunda cópia
mantida manualmente.

---

## 3. Estrutura de repositório

`DECIDIDO` — monorepo Python + TypeScript, detalhado em [ORQUESTRADOR.md](ORQUESTRADOR.md).

```
/
├── README.md
├── /apps
│   └── /control-panel       ← React + TypeScript + Vite
├── /services
│   ├── /control-api         ← FastAPI, grafo, scheduler, persistência
│   ├── /agent-worker        ← runtime base dos papéis PO / Dev / QA
│   └── /test-runner         ← execução determinística sem LLM
├── /packages
│   └── /contracts           ← OpenAPI e JSON Schemas versionados
├── /workspace-template      ← scaffold limpo entregue ao Dev; sem briefing
├── /infra
│   └── compose.yaml         ← serviços fixos, redes e volumes locais
├── /docs
│   ├── DESCRICAO-TAREFA.md  ← fonte do desafio; não editar
│   ├── ENTENDIMENTO.md      ← análise de avaliação; não contém decisões
│   ├── ESPEC.md             ← contrato entre agentes
│   ├── ORQUESTRADOR.md      ← arquitetura e backlog técnico do MVP
│   ├── /PO                  ← definição operacional do PO
│   ├── /dev                 ← definição operacional do Dev
│   └── /qa                  ← definição operacional do QA, a criar
├── /tests                   ← escrito pelo QA Agent, executado pelo runner
└── /seeds                   ← dados sintéticos Rivexx
```

---

## 4. Decisões de arquitetura (ADRs da equipe humana)

> Não confundir com o log de ADRs do Dev Agent. Este é o nosso.

As cinco decisões estruturais foram fechadas para o MVP. Arquitetura operacional, limites e
evolução futura estão em [ORQUESTRADOR.md](ORQUESTRADOR.md). Os alvos verificáveis de `R1`–`R4`
também foram fixados na §1 e devem aparecer nos critérios das stories aplicáveis.

### ADR-001 — Escopo do que o squad gera ao vivo
**Status:** `DECIDIDO` em 2026-08-22
**Contexto:** geração live completa é frágil na demo; replay pré-gravado é desonesto e detectável.
**Opções:** (a) live puro · (b) replay · (c) híbrido — plataforma humana + features geradas ao vivo.
**Decisão:** híbrido. Control plane, painel, contratos, imagens-base, scaffold e seeds são a
plataforma humana. PO gera backlog, Dev implementa a feature, QA cria os testes e runner produz
o veredito durante a execução.
**Consequência:** a demo deve distinguir visualmente plataforma preexistente de artefato produzido
pelo squad e continuar funcionando com briefing novo.

### ADR-002 — Topologia de orquestração
**Status:** `DECIDIDO` em 2026-08-22
**Opções:** (a) supervisor LLM roteando · (b) chat livre entre agentes · (c) grafo de estados determinístico com LLM só dentro dos nós.
**Decisão:** grafo determinístico em LangGraph; cada papel executa como tarefa externa em container
efêmero e se comunica apenas pela API central.
**Consequência:** agentes não roteiam o fluxo nem falam diretamente entre si. Toda transição é
validada, persistida e retomável por checkpoint.

### ADR-003 — Stack do orquestrador
**Status:** `DECIDIDO` em 2026-08-22
**Opções:** (a) LangGraph/Python — melhor em grafo, checkpoint, resume · (b) TypeScript no monorepo — tipos compartilhados com o app, uma linguagem só.
**Trade-off central:** qualidade do grafo vs. atrito de duas linguagens.
**Decisão:** Python com FastAPI, Pydantic, SQLAlchemy, Alembic e LangGraph no backend; React,
TypeScript e Vite no painel; OpenAPI/JSON Schema como contrato entre linguagens; Docker Compose e
Docker SDK for Python no runtime local.
**Consequência:** monorepo com duas linguagens e clientes TypeScript gerados a partir do contrato,
sem duplicar tipos manualmente.

### ADR-004 — Fonte do veredito de aceite
**Status:** `DECIDIDO` em 2026-08-22
**Questão:** quem declara uma story aprovada — o QA Agent (LLM) ou o test runner?
**Nota:** se for o LLM, ele é o elo fraco da avaliação e o ponto óbvio de ataque do avaliador.
**Decisão:** o QA cria plano e testes; um runner sem LLM executa e a API deriva o veredito de
resultados estruturados e exit code.
**Consequência:** nenhum agente possui permissão para emitir `STORY_ACCEPTED`; quebrar um teste de
propósito produz reprovação auditável.

### ADR-005 — Persistência e modelo de rastreabilidade
**Status:** `DECIDIDO` em 2026-08-22
**Opções:** (a) Postgres + CTE recursiva sobre tabela de arestas · (b) grafo dedicado (Neo4j) · (c) closure table.
**Decisão:** uma instância PostgreSQL, com modelo relacional para invariantes e relações, `JSONB`
para payloads de agente e CTE recursiva sobre tabela de arestas para genealogia de lote. MongoDB
não participa do MVP.
**Consequência:** somente a API central recebe credencial de banco. Schemas lógicos `control` e
`product` separam orquestração e Rivexx sem introduzir um segundo datastore.

### ADR-00N — `TODO`

---

## 5. Arquitetura do squad

### 5.1 Topologia

`DECIDIDO` — `control-api` é API, scheduler e grafo no MVP. Ele lança `po-worker`, `dev-worker`,
`qa-worker` e `test-runner` efêmeros pelo Docker Engine. Workers não acessam banco, Docker socket
ou outros workers. Ver [topologia completa](ORQUESTRADOR.md#4-topologia) e
[fluxo em texto](FLOWCHART.txt).

### 5.2 Event log

`DECIDIDO` — PostgreSQL append-only. O event log é a fonte auditável; backlog, ADRs e relatório
de QA são projeções. Checkpoints do LangGraph servem apenas para retomada técnica.

Envelope mínimo:

```json
{
  "event_id": "uuid",
  "sequence": 42,
  "run_id": "uuid",
  "ts": "ISO-8601",
  "actor": "po | dev | qa | runner | system",
  "type": "STORY_CREATED",
  "correlation_id": "NC-003",
  "causation_id": "event_id do evento que disparou este",
  "task_id": "uuid ou null",
  "payload": {},
  "meta": {
    "model": "",
    "tokens_in": 0,
    "tokens_out": 0,
    "latency_ms": 0,
    "container_id": ""
  }
}
```

**Tipos de evento** — lista inicial, completar:

| Tipo | Emissor | Payload |
|---|---|---|
| `RUN_CREATED` | system | run, estado inicial |
| `BRIEFING_RECEIVED` | system | run, briefing hash, tamanho |
| `STORY_CREATED` | po | story completa |
| `BACKLOG_PRIORITIZED` | po | ordem + justificativas |
| `PO_DECISION_RECORDED` | po | título, tipo, justificativa, alternativa descartada |
| `PREMISSA_ASSUMIDA` | po | lacuna, premissa, risco |
| `CAPACIDADE_ADIADA` | po | capacidade, origem, motivo do corte |
| `BACKLOG_COVERAGE_CHECKED` | po | capacidade/restrição → story + critério ou decisão |
| `STORY_FROZEN` | po | id, hash dos critérios |
| `TASK_QUEUED` | system | task, papel, tentativa, timeout |
| `AGENT_STARTED` | system | task, papel, container, image digest |
| `STORY_ASSIGNED` | system | task, story id, versão, frozen hash |
| `TASKS_PLANNED` | dev | story, tasks e cobertura dos critérios |
| `ADR_RECORDED` | dev | story e ADR estruturada |
| `CODE_DELIVERED` | dev | revisão, alterações, evidências e limitações |
| `CODE_REDELIVERED` | dev | revisão anterior, nova revisão e remediações |
| `TEST_PLAN_CREATED` | qa | story, casos e critérios cobertos |
| `TEST_EXECUTED` | runner | comando, exit code, resultados e evidências |
| `STORY_REJECTED` | system | story, revisão e findings derivados do runner |
| `STORY_ACCEPTED` | system | story, revisão e test execution id |
| `AGENT_FAILED` | system | task, tentativa, erro sanitizado e retry |
| `NEEDS_HUMAN` | qualquer | motivo, estado |

### 5.3 Protocolo de comunicação

`DECIDIDO` — REST interno com artefatos estruturados, Pydantic/JSON Schema, idempotency key e
token efêmero por tarefa. Saída em texto livre pode existir dentro do payload, mas nunca controla
transição. O painel recebe atualizações por SSE. Contrato em
[ORQUESTRADOR.md §8](ORQUESTRADOR.md#8-comunicação-pela-api-central).

### 5.4 Isolamento de contexto

Matriz do que cada agente pode ler. **Preencher em conjunto — é aqui que os papéis viram reais ou viram teatro.**

| | briefing bruto | story + AC | repositório / diff | ADRs do Dev | saída do runner |
|---|---|---|---|---|---|
| PO | sim | sim | não | não | resumo apenas |
| Dev | não | story atribuída | leitura/escrita no workspace limpo | sim | findings da revisão atual |
| QA | não | story atribuída | leitura do código e diff; escrita no volume de testes | sim | sim |

> O briefing entra em exatamente um nó (PO). Isso é requisito do enunciado, não estilo. Vale ter uma forma de *demonstrar* na demo que o prompt do Dev não contém o briefing.

---

## 6. Contratos de agente

### 6.1 PO Agent — `RASCUNHO AVANÇADO · ARTEFATOS CRIADOS`

**Artefatos operacionais:** [persona](PO/persona.md) · [decomposição de backlog](PO/SKILL.md) ·
[critérios de aceitação](PO/acceptancecriteria.md) · [contrato de saída](PO/outputcontract.md).
Esta seção é o contrato compartilhado; os artefatos operacionais detalham como o PO o cumpre.

**Contrato em uma frase:** traduz prosa de cliente em obrigações verificáveis. Único nó que lê o briefing. Único que cria e prioriza trabalho. Nunca decide *como*. Nunca declara pronto.

**Funções:**

1. Interpretar o briefing e separar requisitos declarados, suposições e adiamentos.
2. Ancorar cada capacidade e restrição em um trecho identificável do briefing.
3. Decompor o trabalho na menor sequência de stories verticais `como / quero / para`.
4. Fazer a primeira story provar o laço ponta a ponta do produto.
5. Escrever critérios de aceite binários e reproduzíveis em uma linha, com meio de verificação declarado.
6. Priorizar por dependência, redução de risco e valor, registrando justificativa por posição.
7. Declarar fora de escopo e cortes deliberados; corte silencioso é inválido.
8. Anexar as restrições transversais `R1`–`R4` aplicáveis a cada story.
9. Verificar que toda capacidade está coberta, adiada ou assumida exatamente uma vez.
10. Congelar a story ao movê-la para `READY`.

**Limites duros:**

- ❌ Não especifica solução técnica.
- ❌ Não escreve casos de teste. *Critério de aceite é o contrato; caso de teste é a verificação.*
- ❌ Não aprova entrega — não existe transição de estado para `ACCEPTED` disponível a ele.
- ❌ Não altera critério de story fora de `DRAFT`. Congelamento mecânico, não instrução de prompt.
- ❌ Não cria requisito sem origem citável no briefing. Sem citação → vira premissa com flag.
- ❌ Não duplica um resultado observável em duas stories; isso tornaria o veredito do QA ambíguo.
- ❌ Não altera a redação canônica de um critério depois do congelamento. O QA deve reproduzi-la literalmente.

**Rubrica de priorização:** `ABERTO` — dono `@quem`

**Envelope mínimo de saída:**

```json
{
  "stories": [
    {
      "id": "NC-003",
      "titulo": "",
      "narrativa": { "como": "", "quero": "", "para": "" },
      "origem": ["trecho literal ou paráfrase próxima do briefing"],
      "prioridade": 1,
      "justificativa_prioridade": "",
      "depende_de": [],
      "restricoes_aplicaveis": ["R1", "R3"],
      "criterios_aceite": [
        {
          "id": "AC-1",
          "texto": "Dado ..., quando ..., então ...",
          "verificavel_por": "ui | dados | api"
        }
      ],
      "fora_de_escopo": [],
      "estado": "DRAFT | READY | FROZEN"
    }
  ],
  "decisions": [
    {
      "titulo": "",
      "tipo": "SUPOSICAO | ADIAMENTO | SKILL",
      "justificativa": "",
      "alternativa_descartada": ""
    }
  ],
  "cobertura": [
    {
      "item": "capacidade, restrição ou suposição",
      "origem": "trecho do briefing ou null",
      "estado": "COBERTA | ADIADA | ASSUMIDA",
      "story_id": "NC-003 ou null",
      "criterio_id": "AC-1 ou null",
      "decision_titulo": "título da decisão ou null"
    }
  ]
}
```

`criterios_aceite[].texto` é a representação canônica congelada. Pode usar
`Dado / Quando / Então` ou afirmação direta, mas contém um único fato observável. O QA recebe e
reporta essa string sem paráfrase, uma vez e na ordem declarada.

**Limitações operacionais:**

| Parâmetro | Valor | Status |
|---|---|---|
| Teto de stories na primeira release | `TODO` (sugestão: 8–10) | `ABERTO` |
| Temperature | `TODO` | `ABERTO` |
| Retries em falha de schema | `TODO` | `ABERTO` |
| Timeout por chamada | `TODO` | `ABERTO` |
| Idempotência (mesmo briefing → backlog equivalente) | como garantir? | `ABERTO` |

**Risco crítico a testar cedo:** os três cenários da demo estão no enunciado do avaliador, **não** no briefing da Rivexx. Não devem ser injetados no PO — estão implícitos no texto do cliente. Se o PO os derivar sozinho em execuções repetidas, é o momento mais forte da demo. Se não derivar, o problema está na rubrica de priorização.

- [ ] Teste de convergência: 3 execuções, o PO chega nos 3 cenários? · dono `@quem`

---

### 6.2 Dev Agent — `RASCUNHO AVANÇADO · ARTEFATOS CRIADOS`

**Artefatos operacionais:** [persona](dev/persona.md) · [implementação de story](dev/SKILL.md) ·
[contrato de tasks e entrega](dev/task-contract.md) · [remediação de QA](dev/qa-remediation.md).

**Contrato em uma frase:** transforma uma story congelada em incremento funcional, tasks técnicas,
ADRs e evidências sem ler o briefing ou alterar a decisão de produto.

**Funções:** decompor, implementar, verificar, entregar evidências e corrigir findings reproduzidos
do QA. Cada critério deve estar ligado a task e evidência.

**Limites duros:** não lê briefing; não altera story; não aprova a própria entrega; não esconde
teste falho; não transforma decisão técnica em regra de produto.

**Schemas de saída:** definidos em [task-contract.md](dev/task-contract.md). Após três reprovações
consecutivas do mesmo finding sem evidência nova, emite `NEEDS_HUMAN`.

---

### 6.3 QA Agent — `RASCUNHO AVANÇADO · ARTEFATOS CRIADOS`

**Artefatos operacionais:** [persona](QA/persona.md) · [ciclo de validação](QA/SKILL.md) ·
[contrato do plano de testes](QA/test-contract.md) · [referência de aceite](QA/acceptance.md).

**Contrato em uma frase:** converte critérios congelados em casos executáveis, coleta evidências e
devolve findings técnicos sem ler briefing, alterar requisito ou declarar aprovação por opinião.

**Funções:** planejar antecipadamente, materializar testes, garantir ambiente reproduzível, mapear
cada resultado ao critério literal e produzir feedback reproduzível ao Dev.

**Limites duros:** não lê briefing; não reescreve critério; não aprova por julgamento LLM; não
oculta falha ou verificação impedida. ADR-004 reserva o resultado final ao runner.

**Schema de saída:** o QA submete `TEST_PLAN_CREATED`, artefatos JSON e `NEEDS_HUMAN` conforme
o [contrato do plano de testes](QA/test-contract.md). O runner submete `TEST_EXECUTED`; a API
deriva `STORY_REJECTED` ou `STORY_ACCEPTED` conforme o event log.

**Política de reprovação:** máximo de três reprovações consecutivas do mesmo finding sem nova
causa ou evidência; depois disso, `NEEDS_HUMAN` com `RETRY_LIMIT_REACHED`.

---

## 7. Aplicação Rivexx

### 7.1 Modelo de domínio
`TODO` — entidades candidatas: Lote (MP / processo / acabado), Ordem de Produção, Equipamento, Turno, Operador, Fornecedor, Não Conformidade, Análise de Causa, Plano de Ação, Ação, Evidência.

### 7.2 Rastreabilidade

`DECIDIDO` por ADR-005 — PostgreSQL com tabela de arestas entre lotes e CTE recursiva. O modelo
físico e os critérios de profundidade/ciclo ainda devem ser detalhados junto dos seeds.

Duas queries a especificar:
- **Genealogia:** dado um lote de produto acabado, subir até fornecedor e descer até expedição.
- **Lotes correlatos:** mesma matéria-prima **ou** mesmo equipamento na mesma janela de turno. *Esta é a pergunta que o cliente faz quando reclama.*

### 7.3 Auditabilidade do produto
`TODO` — append-only, sem hard delete, toda escrita carrega responsável / turno / equipamento / timestamp.

### 7.4 Mobile e usabilidade sem treinamento
`TODO` — wizard guiado, alvos de toque grandes, captura de foto, leitura de código de lote. Offline/PWA: dentro ou fora do escopo?

### 7.5 Sugestão de causas baseada em histórico
`TODO` — cenário 2 pede "sugestão baseada no histórico". Definir: similaridade sobre NCs anteriores? Regra? LLM? Precisa de seeds com volume suficiente.

---

## 8. Cenários da demo

| # | Cenário | Story(ies) | Critérios | Evidência esperada | Dono |
|---|---|---|---|---|---|
| 1 | Registro ágil — defeito dimensional na linha 4 | `TODO` | `TODO` | `TODO` | `@quem` |
| 2 | Causa raiz assistida + plano de ação | `TODO` | `TODO` | `TODO` | `@quem` |
| 3 | Rastreabilidade de lote | `TODO` | `TODO` | `TODO` | `@quem` |

**Roteiro da demo:** `TODO` — incluir layout de tela (feed do squad vs. app rodando), tempo alvo, ponto de parada em caso de falha.

---

## 9. Riscos

| Risco | Impacto | Mitigação | Dono | Status |
|---|---|---|---|---|
| Loop infinito de QA reprovando | demo trava | teto de iterações → `NEEDS_HUMAN` | `@quem` | `TODO` |
| Código gerado quebra o app | demo morre | branch por story + typecheck como gate | `@quem` | `TODO` |
| Latência de LLM mata o ritmo | avaliador perde interesse | streaming do feed, pré-aquecimento | `@quem` | `TODO` |
| PO não converge nos 3 cenários | requisito não coberto | teste de convergência antecipado | `@quem` | `TODO` |
| Orquestração parece teatro | reprovação direta pelo enunciado | isolamento de contexto demonstrável | `@quem` | `TODO` |
| Comprometimento do Docker socket | acesso equivalente ao daemon/host | socket só no `control-api`, imagens allowlisted e workers sem socket | Dev B | mitigado para ambiente local |
| Worker acessa briefing ou banco | papéis deixam de ser reais | token com escopo, redes separadas e workspace sem docs | Dev A | coberto por `SEC-01` |
| `TODO` | | | | |

---

## 10. Perguntas em aberto

Mover para a seção correspondente assim que resolvida. Não deixar apodrecer aqui. Stack, escopo
live e persistência foram resolvidos nas ADRs 001–005.

| # | Pergunta | Bloqueia | Dono | Prazo |
|---|---|---|---|---|
| Q4 | Volume e realismo dos seeds | cenário 2 e 3 | `@quem` | `AAAA-MM-DD` |
| Q5 | Qual provedor/modelo LLM será usado na demo? | integração do gateway; não bloqueia scaffold | `@quem` | `AAAA-MM-DD` |

---

## 11. Divisão de trabalho

Backlog, dependências e divisão para duas ou três pessoas estão detalhados em
[ORQUESTRADOR.md §§14–15](ORQUESTRADOR.md#14-backlog-técnico).

| Frente | Dono | Revisor |
|---|---|---|
| API, PostgreSQL, event log e grafo | Dev A | Dev B |
| Docker runtime, workers e runner | Dev B | Dev A |
| Painel React responsivo | Dev B com 2 pessoas; Dev C com 3+ | Dev A |
| Adaptação PO / Dev / QA | dividir após contrato `AG-01` | revisão cruzada |
| Integração e demo | equipe | equipe |
