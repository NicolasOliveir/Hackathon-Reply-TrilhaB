# SPEC — Squad Autônomo de Agentes · Projeto Rivexx

> **Status do documento:** rascunho colaborativo
> **Última atualização:** 2026-08-22 — consolidação dos artefatos do PO Agent
> **Regra:** nada aqui é decidido até estar marcado `DECIDIDO`. Toda mudança em seção `DECIDIDO` vira ADR nova, não edição silenciosa.
> **Leitura do enunciado, superfície de ataque do avaliador e recomendações abertas:** [ENTENDIMENTO.md](ENTENDIMENTO.md) — análise, não decisão.

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
| `R1` | Aplicação responsiva (registro pelo celular no chão de fábrica) | `TODO` — definir viewport de teste |
| `R2` | Interface operável sem treinamento técnico | `TODO` — definir critério objetivo, não subjetivo |
| `R3` | Todo registro com evidência auditável (data, responsável, turno, equipamento) | `TODO` |
| `R4` | Rastreabilidade de lote em toda a cadeia produtiva | `TODO` |

> ⚠️ Restrição sem meio de verificação é decoração. Preencher a coluna direita é pré-requisito para o QA Agent existir de verdade.

O guia [acceptancecriteria.md](PO/acceptancecriteria.md) contém exemplos úteis para `R1`–`R4`,
mas eles são padrões de escrita, não metas de produto aprovadas. As verificações acima continuam
abertas até que seus valores objetivos sejam acordados e registrados nesta ESPEC.

---

## 2. O que estamos entregando

Mapeamento entregável → artefato no repo.

| Entregável exigido | Onde vive | Gerado por | Status |
|---|---|---|---|
| Squad funcional com comunicação visível | `/squad` | humano (plataforma) | `TODO` |
| Aplicação web rodando localmente, 3 cenários | `/app` | Dev Agent (features) | `TODO` |
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
| Dev Agent | persona, instruções e contrato operacional | `TODO` |
| QA Agent | persona, instruções e contrato operacional | `TODO` |

O [mapa dos artefatos do PO](PO/README.md) explicita a precedência entre esses documentos e a
ESPEC.

Enquanto ADR-003 estiver aberta, `docs/PO` é a fonte de design do agente. Quando o runtime for
criado, `/squad/agents/po` deverá carregar esses artefatos diretamente ou empacotá-los de forma
automatizada; não deve existir uma segunda cópia mantida manualmente.

---

## 3. Estrutura de repositório proposta

`ABERTO` — dono: `@quem` · prazo: `AAAA-MM-DD`

```
/
├── README.md                ← como rodar a demo (escrever por último)
├── /docs
│   ├── DESCRICAO-TAREFA.md  ← fonte do desafio; não editar
│   ├── ENTENDIMENTO.md      ← análise de avaliação; não contém decisões
│   ├── ESPEC.md             ← este documento; contrato entre agentes
│   ├── /PO                  ← persona e instruções operacionais do PO Agent
│   └── /adr                 ← decisões da equipe humana
├── /squad
│   ├── /agents
│   │   ├── po/              ← carregamento runtime dos contratos em docs/PO
│   │   ├── dev/
│   │   └── qa/
│   ├── /graph               ← máquina de estados, transições
│   ├── /bus                 ← event log append-only
│   ├── /schemas             ← contratos compartilhados (Zod/Pydantic)
│   └── /projections         ← backlog, ADRs, relatório QA, feed
├── /app                     ← aplicação Rivexx
│   ├── /platform            ← construído por humanos (scaffold)
│   └── /features            ← escrito pelo Dev Agent ao vivo
├── /tests                   ← escrito pelo QA Agent, executado pelo runner
└── /seeds                   ← dados sintéticos Rivexx
```

---

## 4. Decisões de arquitetura (ADRs da equipe humana)

> Não confundir com o log de ADRs do Dev Agent. Este é o nosso.

**Ordem de resolução** (derivada dos bloqueios abaixo, detalhada em [ENTENDIMENTO.md](ENTENDIMENTO.md) §5):
ADR-003 e ADR-001 destravam a estrutura do repo e o cronograma → ADR-002 e ADR-004 fecham o contrato do QA → ADR-005 corre em paralelo (é local ao app).
A coluna "como se verifica" de `R1`–`R4` na §1 bloqueia o contrato do QA sem estar numerada como ADR.

### ADR-001 — Escopo do que o squad gera ao vivo
**Status:** `ABERTO` · dono `@quem`
**Contexto:** geração live completa é frágil na demo; replay pré-gravado é desonesto e detectável.
**Opções:** (a) live puro · (b) replay · (c) híbrido — plataforma humana + features geradas ao vivo.
**Decisão:** `TODO`
**Consequência:** `TODO`

### ADR-002 — Topologia de orquestração
**Status:** `ABERTO` · dono `@quem`
**Opções:** (a) supervisor LLM roteando · (b) chat livre entre agentes · (c) grafo de estados determinístico com LLM só dentro dos nós.
**Decisão:** `TODO`
**Consequência:** `TODO`

### ADR-003 — Stack do orquestrador
**Status:** `ABERTO` · dono `@quem`
**Opções:** (a) LangGraph/Python — melhor em grafo, checkpoint, resume · (b) TypeScript no monorepo — tipos compartilhados com o app, uma linguagem só.
**Trade-off central:** qualidade do grafo vs. atrito de duas linguagens.
**Decisão:** `TODO`

### ADR-004 — Fonte do veredito de aceite
**Status:** `ABERTO` · dono `@quem`
**Questão:** quem declara uma story aprovada — o QA Agent (LLM) ou o test runner?
**Nota:** se for o LLM, ele é o elo fraco da avaliação e o ponto óbvio de ataque do avaliador.
**Decisão:** `TODO`

### ADR-005 — Persistência e modelo de rastreabilidade
**Status:** `ABERTO` · dono `@quem`
**Opções:** (a) Postgres + CTE recursiva sobre tabela de arestas · (b) grafo dedicado (Neo4j) · (c) closure table.
**Decisão:** `TODO`

### ADR-00N — `TODO`

---

## 5. Arquitetura do squad

### 5.1 Topologia
`BLOQUEADO` por ADR-002. Preencher depois.

### 5.2 Event log
`TODO`

Envelope proposto — revisar em grupo:

```json
{
  "event_id": "uuid",
  "ts": "ISO-8601",
  "actor": "po | dev | qa | runner | system",
  "type": "STORY_CREATED",
  "correlation_id": "NC-003",
  "causation_id": "event_id do evento que disparou este",
  "payload": {},
  "meta": { "model": "", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0 }
}
```

**Tipos de evento** — lista inicial, completar:

| Tipo | Emissor | Payload |
|---|---|---|
| `BRIEFING_RECEIVED` | system | `TODO` |
| `STORY_CREATED` | po | story completa |
| `BACKLOG_PRIORITIZED` | po | ordem + justificativas |
| `PO_DECISION_RECORDED` | po | título, tipo, justificativa, alternativa descartada |
| `PREMISSA_ASSUMIDA` | po | lacuna, premissa, risco |
| `CAPACIDADE_ADIADA` | po | capacidade, origem, motivo do corte |
| `BACKLOG_COVERAGE_CHECKED` | po | capacidade/restrição → story + critério ou decisão |
| `STORY_FROZEN` | po | id, hash dos critérios |
| `STORY_ASSIGNED` | system | `TODO` |
| `ADR_RECORDED` | dev | `TODO` |
| `CODE_COMMITTED` | dev | `TODO` |
| `TEST_PLAN_CREATED` | qa | `TODO` |
| `TEST_EXECUTED` | runner | `TODO` |
| `STORY_REJECTED` | runner | `TODO` |
| `STORY_ACCEPTED` | runner | `TODO` |
| `NEEDS_HUMAN` | qualquer | motivo, estado |

### 5.3 Protocolo de comunicação
`TODO` — decidir entre artefatos estruturados validados por schema vs. mensagens em texto livre. Registrar o porquê.

### 5.4 Isolamento de contexto

Matriz do que cada agente pode ler. **Preencher em conjunto — é aqui que os papéis viram reais ou viram teatro.**

| | briefing bruto | story + AC | repositório / diff | ADRs do Dev | saída do runner |
|---|---|---|---|---|---|
| PO | sim | sim | não | não | resumo apenas |
| Dev | `TODO` | `TODO` | `TODO` | `TODO` | `TODO` |
| QA | `TODO` | `TODO` | `TODO` | `TODO` | `TODO` |

> O briefing entra em exatamente um nó (PO). Isso é requisito do enunciado, não estilo. Vale ter uma forma de *demonstrar* na demo que o prompt do Dev não contém o briefing.

---

## 6. Contratos de agente

### 6.1 PO Agent — `RASCUNHO AVANÇADO · ARTEFATOS CRIADOS`

**Artefatos operacionais:** [mapa](PO/README.md) · [persona](PO/persona.md) ·
[decomposição de backlog](PO/SKILL.md) · [critérios de aceitação](PO/acceptancecriteria.md).
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

### 6.2 Dev Agent — `TODO`

**Contrato em uma frase:** `TODO`

**Funções:** `TODO`

**Limites duros:** `TODO`
> Fronteira mais escorregadia a resolver: ADR técnica vs. decisão de produto. Onde termina "escolhi Postgres porque X" e começa "decidi que o campo de foto é opcional"? A segunda é do PO.

**Schema de saída (ADR):** `TODO`

**Limitações operacionais:** `TODO`

---

### 6.3 QA Agent — `TODO`

**Contrato em uma frase:** `TODO`

**Funções:** `TODO`

**Limites duros:** `TODO`
> Depende de ADR-004. Se o veredito vier do runner, o QA escreve o teste e não julga o resultado.

**Schema de saída (plano de teste):** `TODO`

**Política de reprovação:** `TODO` — teto de iterações antes de `NEEDS_HUMAN`.

---

## 7. Aplicação Rivexx

### 7.1 Modelo de domínio
`TODO` — entidades candidatas: Lote (MP / processo / acabado), Ordem de Produção, Equipamento, Turno, Operador, Fornecedor, Não Conformidade, Análise de Causa, Plano de Ação, Ação, Evidência.

### 7.2 Rastreabilidade
`BLOQUEADO` por ADR-005.

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
| `TODO` | | | | |

---

## 10. Perguntas em aberto

Mover para a seção correspondente assim que resolvida. Não deixar apodrecer aqui.

Q1–Q4 têm recomendação de partida (não decidida) em [ENTENDIMENTO.md](ENTENDIMENTO.md) §6.

| # | Pergunta | Bloqueia | Dono | Prazo |
|---|---|---|---|---|
| Q1 | Stack do orquestrador — Python ou TS? | ADR-003, todo o `/squad` | `@quem` | `AAAA-MM-DD` |
| Q2 | Quanto do app é scaffold humano? | ADR-001, cronograma | `@quem` | `AAAA-MM-DD` |
| Q3 | Como tornar `R2` (sem treinamento) verificável? | contrato do QA | `@quem` | `AAAA-MM-DD` |
| Q4 | Volume e realismo dos seeds | cenário 2 e 3 | `@quem` | `AAAA-MM-DD` |
| Q5 | `TODO` | | | |

---

## 11. Divisão de trabalho

| Frente | Dono | Revisor |
|---|---|---|
| Orquestrador + event log | `@quem` | `@quem` |
| PO Agent | `@quem` | `@quem` |
| Dev Agent | `@quem` | `@quem` |
| QA Agent + runner | `@quem` | `@quem` |
| Plataforma do app + seeds | `@quem` | `@quem` |
| Projeções e feed da demo | `@quem` | `@quem` |
