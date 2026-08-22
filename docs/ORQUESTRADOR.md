# Arquitetura e backlog do orquestrador — MVP

> **Status:** decisões do MVP prontas para implementação
> **Última atualização:** 2026-08-22
> **Escopo:** plataforma que executa e torna auditável o fluxo PO → Dev → QA → runner.

Este documento e [FLOWCHART.txt](FLOWCHART.txt) são a referência arquitetural atual.
`DIAGRAMA.png` representa uma visão conceitual anterior à decisão de API única e precisa ser
regenerado antes de ser usado na demo.

## 1. Objetivo

Construir um plano de controle local que receba um briefing uma única vez, execute cada papel em
um container isolado, mantenha o fluxo determinístico e exponha toda comunicação em um painel
responsivo.

O orquestrador não é um chat entre três prompts. Ele é responsável por estado, contexto,
permissões, retries, isolamento, auditoria e transições. Os agentes produzem artefatos; somente o
orquestrador decide qual etapa pode executar em seguida.

## 2. Decisões do MVP

| Tema | Decisão |
|---|---|
| Backend e API | Python + FastAPI + Pydantic + SQLAlchemy + Alembic |
| Grafo | LangGraph, com transições determinísticas e LLM apenas dentro dos workers |
| Painel | React + TypeScript + Vite, consumindo REST e Server-Sent Events |
| Persistência | PostgreSQL único; colunas relacionais para invariantes e `JSONB` para payloads variáveis |
| Execução | Docker Compose para serviços fixos e Docker SDK for Python para containers efêmeros |
| Comunicação | Todos os agentes falam somente com a API central; não há chamada direta agente → agente |
| Veredito | Runner determinístico por exit code e resultados estruturados; o QA não se autoaprova |
| Escopo ao vivo | Híbrido: plataforma e scaffold são humanos; backlog, código da feature, testes e evidências são gerados ao vivo |
| Nuvem | Fora do MVP; uma interface de runtime permite trocar Docker local por ECS ou Kubernetes no futuro |

Não haverá MongoDB, Redis, RabbitMQ ou Kafka no MVP. PostgreSQL também funcionará como fila
durável de tarefas. Isso reduz infraestrutura, elimina sincronização entre bancos e ainda permite
escalar consumidores com `FOR UPDATE SKIP LOCKED` quando necessário.

## 3. Escopo

### 3.1 P0 — obrigatório para a demo

- receber o briefing por formulário e iniciar uma execução;
- executar PO, Dev e QA em containers separados;
- executar os testes em um runner não-LLM;
- garantir que cada papel receba apenas o contexto autorizado;
- persistir eventos append-only com correlação e causalidade;
- projetar backlog, tasks, ADRs, testes, evidências e estado atual;
- exibir o feed ao vivo no painel;
- reprovar uma entrega, retornar ao Dev e limitar o ciclo de correção;
- preservar logs e artefatos depois que o container terminar;
- subir todo o ambiente fixo com Docker Compose;
- operar o painel sem rolagem horizontal a partir de 320 px de largura.

### 3.2 P1 — somente se o P0 estiver estável

- cancelamento administrativo de uma execução;
- download agrupado das evidências;
- duas execuções simultâneas com limite configurável;
- preview da aplicação gerada acessível pelo painel;
- reconciliação automática de containers órfãos após reinício do Docker.

### 3.3 Fora do MVP

- AWS, ECS, EKS, Kubernetes ou Terraform;
- alta disponibilidade e escalonamento automático;
- execução simultânea de várias stories no mesmo workspace;
- MongoDB ou outro segundo banco;
- broker externo de mensagens;
- autenticação corporativa, multi-tenant ou RBAC completo;
- edição manual de story ou aprovação humana no meio do fluxo;
- modo offline/PWA;
- instalação livre de dependências durante a execução dos agentes;
- isolamento seguro para código hostil em ambiente multiusuário.

`NEEDS_HUMAN` continua existindo como estado terminal de exceção. Ele interrompe e explica a
execução; não vira uma etapa normal de aprovação durante a demo.

## 4. Topologia

### 4.1 Serviços fixos do Compose

| Serviço | Responsabilidade | Acessa PostgreSQL | Acessa Docker socket |
|---|---|---:|---:|
| `control-api` | REST/SSE, LangGraph, event log, scheduler, gateway de modelo | sim | sim |
| `control-panel` | painel React estático | não | não |
| `postgres` | estado, eventos, tarefas, projeções e checkpoints | — | não |

O `control-api` executa com um único processo de scheduler no MVP. Vários workers HTTP do
Uvicorn criariam múltiplos loops de despacho; separar API e scheduler será uma evolução, não uma
complexidade antecipada.

### 4.2 Containers efêmeros

| Papel | Ciclo de vida | Contexto | Workspace |
|---|---|---|---|
| `po-worker` | um container por briefing | briefing bruto + contratos do PO | nenhum código montado |
| `dev-worker` | um container por entrega ou correção | story congelada, ADRs e findings permitidos | leitura/escrita no workspace da execução |
| `qa-worker` | um container por entrega | story, diff, evidências do Dev e contratos do QA | código somente leitura; volume próprio para testes |
| `test-runner` | um container por suíte | plano e testes materializados | código e testes somente leitura |

Os três agentes podem compartilhar uma imagem-base Python, mas usam comandos, tokens, mounts e
permissões diferentes. O runner é uma imagem separada e não recebe credencial de modelo.

### 4.3 Redes e volumes

- `control_net`: somente `control-api` e `postgres`;
- `agent_net`: rede interna de `control-api` e containers efêmeros, sem acesso direto à internet;
- `public_net`: painel e `control-api`;
- volume `postgres_data`: dados do PostgreSQL;
- volume `run_workspaces`: código da aplicação por execução;
- volume `run_artifacts`: testes, logs, screenshots e relatórios.

O PostgreSQL não publica porta no host por padrão. Containers de agente não recebem
`DATABASE_URL`, não entram em `control_net` e nunca recebem o Docker socket.

O workspace não é um bind mount da raiz deste repositório. Ele nasce de um scaffold limpo que
exclui `docs/DESCRICAO-TAREFA.md` e qualquer outro arquivo com o briefing. Isso torna mecânico — e
demonstrável — que o Dev e o QA não conseguem recuperar o briefing pelo filesystem.

Dependências necessárias à demo ficam travadas no scaffold ou nas imagens. O gateway de modelo
é a única saída dos agentes para um serviço externo e permanece dentro do `control-api`.

## 5. Responsabilidades do `control-api`

O container central possui módulos lógicos separados, mesmo permanecendo um único deploy no MVP:

1. **API pública:** criação e consulta de execuções, projeções e stream de eventos.
2. **API interna de agentes:** contexto autorizado, heartbeat, invocação de modelo e submissão de saída.
3. **Máquina de estados:** transições permitidas, retries e limite de correções.
4. **Scheduler:** cria tarefas e despacha containers pendentes.
5. **Runtime Docker:** cria, observa, interrompe e remove containers efêmeros.
6. **Gateway de modelos:** mantém a credencial do provedor fora dos agentes e audita cada chamada.
7. **Event store:** grava eventos append-only e atualiza projeções na mesma transação.
8. **Artifact registry:** registra hash, tipo, caminho e produtor de cada artefato.

Interfaces internas obrigatórias:

```text
ContainerRuntime.start(task) -> execution_ref
ContainerRuntime.status(execution_ref) -> status
ContainerRuntime.stop(execution_ref) -> None
ModelGateway.invoke(request) -> model_response
EventStore.append(event) -> persisted_event
ArtifactStore.register(metadata) -> artifact_ref
```

Somente `ContainerRuntime` conhece o Docker SDK. Uma implementação futura pode usar ECS Tasks ou
Kubernetes Jobs sem alterar o grafo, os agentes ou o protocolo HTTP.

## 6. Fluxo de uma execução

1. O painel envia `POST /api/v1/runs` com o briefing.
2. A API cria `run`, grava `BRIEFING_RECEIVED` e agenda a tarefa do PO em uma transação.
3. O scheduler inicia `po-worker` com `run_id`, `task_id`, URL da API e token efêmero.
4. O worker busca seu contexto autorizado na API, executa o loop do agente e envia a saída.
5. A API valida o schema, persiste backlog/decisões/eventos e congela as stories.
6. Para cada story, de forma sequencial no MVP, o grafo agenda o Dev.
7. O Dev altera o workspace, registra tasks/ADRs/evidências e entrega uma revisão.
8. O QA recebe story congelada e entrega do Dev, cria o plano e materializa os testes.
9. O runner executa os testes. A API deriva o veredito dos resultados e do exit code.
10. Em caso de falha, a API envia findings estruturados ao Dev e incrementa a revisão.
11. Em caso de sucesso, a story é aceita e o grafo avança para a próxima.
12. Ao final, a API marca a execução como concluída; todas as views continuam disponíveis.

O container pode terminar a qualquer momento. Seu resultado só existe oficialmente depois de
validado e persistido pela API.

## 7. Máquina de estados

```text
RECEIVED
  -> PO_QUEUED -> PO_RUNNING -> BACKLOG_FROZEN
  -> DEV_QUEUED -> DEV_RUNNING -> DELIVERY_READY
  -> QA_QUEUED -> QA_RUNNING -> TESTS_READY
  -> RUNNER_QUEUED -> RUNNER_RUNNING
       -> STORY_ACCEPTED -> próxima story ou COMPLETED
       -> STORY_REJECTED -> DEV_QUEUED
       -> NEEDS_HUMAN quando o limite de correções for atingido
```

Estados terminais: `COMPLETED`, `FAILED`, `CANCELED`, `NEEDS_HUMAN`.

Regras:

- transição inválida retorna conflito e gera evento de tentativa rejeitada;
- cada comando possui `idempotency_key`;
- uma story executa no máximo uma tarefa ativa por papel;
- cada finding admite até três reprovações consecutivas sem evidência nova;
- timeout ou container perdido permite retry automático até o limite configurado;
- efeitos externos do nó LangGraph usam get-or-create por `task_id`, pois um nó pode ser retomado.

## 8. Comunicação pela API central

Não existe barramento de mensagens entre agentes. A comunicação auditável ocorre assim:

```text
Agente A -> saída estruturada -> API -> evento + projeção -> nova tarefa -> Agente B
```

### 8.1 Credencial de tarefa

Cada container recebe um bearer token aleatório, armazenado apenas como hash, com:

- `task_id`, `run_id` e papel fixos;
- escopos mínimos (`context:read`, `model:invoke`, `output:write`, `heartbeat:write`);
- validade curta e revogação no término;
- impedimento de consultar outra tarefa ou outro papel.

### 8.2 Endpoints públicos

| Método e rota | Uso |
|---|---|
| `POST /api/v1/runs` | recebe o briefing e retorna `202` + `run_id` |
| `GET /api/v1/runs/{run_id}` | estado e etapa atual |
| `GET /api/v1/runs/{run_id}/events` | stream SSE retomável pelo último `sequence` |
| `GET /api/v1/runs/{run_id}/backlog` | projeção do PO |
| `GET /api/v1/runs/{run_id}/decisions` | ADRs do Dev |
| `GET /api/v1/runs/{run_id}/qa-report` | plano, execuções, findings e evidências |
| `GET /api/v1/runs/{run_id}/artifacts` | metadados e download autorizado |
| `POST /api/v1/runs/{run_id}/cancel` | P1 administrativo; não participa do fluxo normal |

### 8.3 Endpoints internos dos agentes

| Método e rota | Uso |
|---|---|
| `GET /internal/v1/tasks/{task_id}/context` | envelope filtrado pelo papel |
| `POST /internal/v1/tasks/{task_id}/heartbeat` | sinal de vida e progresso resumido |
| `POST /internal/v1/tasks/{task_id}/model-invocations` | chamada ao LLM via gateway central |
| `POST /internal/v1/tasks/{task_id}/outputs` | saída final validada por schema e hash |
| `POST /internal/v1/tasks/{task_id}/artifacts` | registro de artefato produzido |
| `POST /internal/v1/tasks/{task_id}/failures` | falha técnica reproduzível |

Agentes não escrevem eventos arbitrários. Eles submetem saídas de domínio; a API valida a
transição e emite os eventos correspondentes. Isso impede um agente de se declarar aprovado.

### 8.4 Isolamento de contexto

| Contexto | PO | Dev | QA | Runner |
|---|---:|---:|---:|---:|
| Briefing bruto | sim | não | não | não |
| Story congelada | produz | sim | sim | IDs e critérios necessários |
| Código da aplicação | não | leitura/escrita | leitura | leitura |
| ADRs do Dev | não | sim | sim | não |
| Entrega/diff do Dev | não | sim | sim | não |
| Plano e testes do QA | não | após reprovação | produz | leitura |
| Saída do runner | resumo | findings da revisão | sim | produz |

Toda resposta de contexto inclui um `context_manifest` com IDs, tipos e hashes das fontes. O
painel pode mostrar esse manifesto para provar o que cada agente realmente recebeu.

## 9. Persistência: PostgreSQL, não MongoDB

### 9.1 Por que relacional

- transições e unicidade exigem constraints e transações;
- stories, critérios, tasks, revisões, findings e artefatos têm relações explícitas;
- o event log precisa de ordenação total por execução e causalidade verificável;
- uma fila em tabela precisa de locking concorrente e idempotência;
- rastreabilidade de lote é naturalmente uma tabela de arestas consultada com CTE recursiva;
- `JSONB` absorve payloads de modelos sem perder o núcleo relacional.

MongoDB seria considerado apenas se documentos sem schema se tornassem a carga dominante e as
relações/transações deixassem de ser centrais. Usar ambos agora exigiria sincronização, backup,
observabilidade e recuperação em dois sistemas sem benefício para a demo.

### 9.2 Organização

Uma única instância PostgreSQL, acessível somente pelo `control-api`, com schemas lógicos:

- `control`: execução do squad, eventos, tarefas, checkpoints e projeções;
- `product`: dados estáveis da aplicação Rivexx, caso compartilhe a mesma API no scaffold.

Os schemas têm roles distintas. Containers dos agentes não recebem nenhuma role do banco.

### 9.3 Tabelas mínimas do schema `control`

| Tabela | Finalidade |
|---|---|
| `runs` | briefing bruto, estado atual e timestamps |
| `events` | log append-only com `sequence`, ator, tipo, correlação, causa e `payload JSONB` |
| `stories` | projeção versionada do backlog e hash congelado |
| `acceptance_criteria` | texto canônico e ordem de avaliação |
| `agent_tasks` | fila durável, papel, tentativa, timeout, token hash e estado |
| `agent_executions` | container, imagem, início/fim, exit code e motivo |
| `technical_decisions` | projeção das ADRs do Dev |
| `test_executions` | runner, comando, resultado e evidência |
| `artifacts` | produtor, tipo, hash, tamanho e localização |
| `idempotency_keys` | deduplicação de comandos e callbacks |

Checkpoints do LangGraph usam tabelas próprias no mesmo banco. Eles servem para retomada técnica;
`events` continua sendo a fonte auditável exibida ao avaliador.

## 10. Runtime Docker

O `control-api` usa Docker SDK for Python e monta `/var/run/docker.sock`. Isso atende ao MVP
local e dá ao container poder equivalente ao daemon Docker; portanto:

- somente o módulo `ContainerRuntime` acessa o socket;
- endpoints internos não são expostos diretamente fora da rede do Compose;
- nomes não vêm de input livre; usam IDs validados e labels `run_id`, `task_id`, `role`;
- imagens são allowlisted e referenciadas por digest quando possível;
- workers executam como usuário não-root, com `cap_drop: ALL`, `no-new-privileges`, limite de CPU,
  memória, PIDs e timeout;
- código e testes entram como mounts somente leitura no runner; `/tmp` e o destino de evidências
  são os únicos espaços graváveis;
- workers nunca recebem o socket;
- o scheduler remove containers concluídos depois de persistir logs e exit code;
- um reconciliador compara tarefas ativas com containers rotulados ao reiniciar.

Para AWS, `DockerContainerRuntime` será substituído por `EcsTaskRuntime`; banco, API, contratos e
grafo permanecem. Não será implementado código AWS no MVP.

## 11. Painel React e experiência mobile

O painel é observabilidade e operação, não um editor de código.

### 11.1 Telas P0

1. **Nova execução:** textarea do briefing, confirmação de envio único e estado de criação.
2. **Execução:** etapa atual, duração, container ativo e falha mais recente.
3. **Timeline:** eventos ao vivo, ator, horário, causa e payload expandível.
4. **Backlog:** stories, prioridade, critérios, hash e estado.
5. **Decisões:** ADRs do Dev com contexto, opções e consequência.
6. **QA:** critérios na ordem, casos executados, PASS/FAIL e evidências.
7. **Contexto do agente:** manifesto real entregue a cada execução.

### 11.2 Regras mobile

- viewport mínimo de 320 px sem rolagem horizontal da página;
- navegação e ações principais com alvos mínimos de 44 × 44 px;
- tabelas viram cards no mobile;
- timeline usa resumo de uma linha e detalhe expansível;
- payloads e logs quebram linha dentro do card, com cópia explícita;
- reconexão SSE usa o último `sequence` para não perder eventos;
- envio do briefing informa erro sem apagar o texto digitado;
- PWA e operação offline ficam fora do MVP.

## 12. Observabilidade e auditabilidade

Cada evento possui:

```json
{
  "event_id": "uuid",
  "sequence": 42,
  "run_id": "uuid",
  "actor": "system | po | dev | qa | runner",
  "type": "STORY_ASSIGNED",
  "correlation_id": "NC-003",
  "causation_id": "uuid",
  "task_id": "uuid ou null",
  "ts": "ISO-8601",
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

Logs técnicos podem ser truncados na tela, mas o artefato integral recebe hash. Segredos e o
conteúdo integral do briefing não aparecem em logs de infraestrutura.

## 13. Estratégia de entrega em fatias

1. **Fatia zero — contrato:** OpenAPI, schemas Pydantic/JSON Schema, estados e eventos.
2. **Fatia um — prova distribuída:** briefing → `fake-po-worker` em container → evento persistido
   → timeline React. Ainda sem LLM.
3. **Fatia dois — PO real:** gateway de modelo, backlog validado e projeção.
4. **Fatia três — uma story completa:** Dev → QA → runner → aceite.
5. **Fatia quatro — reprovação real:** runner falha, Dev corrige e runner aprova.
6. **Fatia cinco — demo Rivexx:** backlog completo e três cenários.

Cada fatia deve rodar via Compose e terminar com um teste de integração. A primeira fatia reduz o
maior risco arquitetural sem depender da qualidade do modelo.

## 14. Backlog técnico

O planejamento abaixo define o backlog arquitetural. Reservas, responsáveis e estado da primeira
iteração são controlados exclusivamente no [quadro compartilhado](../TASKS.md) publicado em
`origin/main`.

| ID | Entrega | Dependências | Critério de conclusão | Faixa |
|---|---|---|---|---|
| `ARC-01` | contratos de estados, eventos e outputs dos papéis | — | schemas versionados e exemplos válidos/inválidos testados | comum |
| `INF-01` | Compose, redes, volumes e healthchecks | — | painel, API e Postgres sobem com um comando | runtime |
| `DB-01` | migrations e repositórios do schema `control` | `ARC-01` | grava run/event/task atomicamente e rejeita duplicata | backend |
| `API-01` | criar/consultar run e projeções | `DB-01` | briefing gera `run_id` e primeiro evento | backend |
| `API-02` | SSE retomável por `sequence` | `DB-01` | desconexão e reconexão não perdem nem duplicam eventos | backend |
| `SEC-01` | token efêmero e filtro de contexto por papel | `API-01` | Dev não obtém briefing nem contexto de outra task | backend |
| `RT-01` | interface `ContainerRuntime` + fake runtime | `ARC-01` | grafo testável sem Docker | runtime |
| `RT-02` | implementação Docker e reconciliação básica | `INF-01`, `RT-01` | container rotulado executa, reporta exit code e é removido | runtime |
| `AG-01` | cliente base do worker: contexto, heartbeat, output | `SEC-01`, `RT-02` | fake worker conclui tarefa somente via API | runtime |
| `LLM-01` | gateway de modelo auditável | `API-01` | chave fica só na API e uso gera metadados no evento | backend |
| `ORQ-01` | grafo PO → Dev → QA → runner | `DB-01`, `RT-01` | transições inválidas são recusadas e retomada é idempotente | backend |
| `AG-PO-01` | adaptar contratos existentes do PO ao worker | `AG-01`, `LLM-01` | briefing produz backlog válido e congelado | agentes |
| `AG-DEV-01` | worker Dev com workspace isolado | `AG-01`, `ORQ-01` | entrega referencia story, tasks, ADRs, diff e evidências | agentes |
| `AG-QA-01` | worker QA e materialização de testes | `AG-DEV-01` | cada critério gera caso e evidência rastreável | agentes |
| `RUN-01` | runner determinístico | `AG-QA-01` | exit code e resultados geram aceite/reprovação sem julgamento LLM | runtime |
| `FE-01` | shell responsivo, rotas e cliente OpenAPI | `ARC-01` | funciona em 320 px e estados de loading/erro estão visíveis | frontend |
| `FE-02` | criação e resumo da execução | `API-01`, `FE-01` | usuário envia uma vez e acompanha a etapa atual | frontend |
| `FE-03` | timeline SSE e contexto recebido | `API-02`, `FE-01` | feed atualiza e exibe causalidade/context manifest | frontend |
| `FE-04` | backlog, ADRs e QA report | `API-01`, `FE-01` | os três entregáveis são navegáveis em desktop e mobile | frontend |
| `E2E-01` | happy path com fake agents | todas P0 básicas | execução termina sem acesso direto ao banco pelos workers | integração |
| `E2E-02` | reprovação e correção | `RUN-01`, `ORQ-01` | falha real retorna ao Dev e respeita limite de três ciclos | integração |
| `DEMO-01` | roteiro, seeds e evidências Rivexx | `E2E-01`, `E2E-02` | os três cenários e uma reprovação são demonstráveis | integração |

## 15. Divisão entre desenvolvedores

### 15.1 Equipe com dois devs

**Dev A — control plane:** `ARC-01`, `DB-01`, `API-01`, `API-02`, `SEC-01`, `LLM-01`, `ORQ-01`.

**Dev B — runtime e experiência:** `INF-01`, `RT-01`, `RT-02`, `AG-01`, `RUN-01`, `FE-01` a
`FE-04`.

Os adaptadores `AG-PO-01`, `AG-DEV-01` e `AG-QA-01` são divididos depois que `AG-01` estabilizar.
Dev A assume PO; Dev B assume Dev/QA. `E2E-*` exige revisão cruzada.

### 15.2 Equipe com três devs

- **Dev A — API e dados:** `ARC-01`, `DB-01`, `API-*`, `SEC-01`, `LLM-01`;
- **Dev B — orquestração e runtime:** `INF-01`, `RT-*`, `AG-*`, `RUN-01`, `ORQ-01`;
- **Dev C — painel e integração:** `FE-*`, `E2E-*`, `DEMO-01`.

### 15.3 Regras para evitar conflito

- OpenAPI e JSON Schemas são fechados em `ARC-01` antes das implementações paralelas;
- frontend usa cliente gerado e mocks do contrato, sem esperar a API ficar pronta;
- runtime depende de `ContainerRuntime`, não de imports internos do scheduler;
- cada frente possui diretório próprio e migrations têm um único responsável por vez;
- integração acontece por fatia vertical curta, não por merge único no final.

## 16. Definition of Done do orquestrador MVP

- `docker compose up --build` sobe os serviços fixos;
- um briefing dispara containers reais de PO, Dev e QA sem intervenção intermediária;
- nenhuma imagem de agente contém credencial de banco ou Docker;
- agentes não acessam diretamente internet ou provedor LLM;
- Dev e QA não conseguem obter o briefing pela API nem pelo workspace;
- painel mostra eventos persistidos com `causation_id` e contexto real recebido;
- runner quebrado de propósito reprova a story;
- retry não duplica story, task, evento de domínio nem artefato;
- reiniciar `control-api` permite continuar do último checkpoint;
- toda story concluída aparece no backlog, nas ADRs e no relatório de QA;
- painel permanece operável em viewport de 320 px.

## 17. Decisões adiadas, com default

Estas escolhas não bloqueiam o scaffold:

| Tema | Default até decisão explícita |
|---|---|
| Provedor e modelo LLM | adapter configurado por variável de ambiente; nenhum provider hardcoded no domínio |
| Armazenamento de artefatos | volume Docker local + metadados/hash no PostgreSQL; S3 fica para depois |
| Concorrência | uma execução e uma story ativa por vez |
| Retenção | manter todos os artefatos da demo; política automática fica para depois |
| Autenticação do painel | ambiente local sem login; endpoints internos protegidos por token de tarefa |

## 18. Referências técnicas

- [Persistência e checkpoints do LangGraph](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Server-Sent Events no FastAPI](https://fastapi.tiangolo.com/tutorial/server-sent-events/)
- [Docker Engine security](https://docs.docker.com/engine/security/)
- [Docker SDK for Python — containers](https://docker-py.readthedocs.io/en/stable/containers.html)
- [PostgreSQL — tipos JSON](https://www.postgresql.org/docs/current/datatype-json.html)
- [PostgreSQL — queries recursivas](https://www.postgresql.org/docs/current/queries-with.html)
- [PostgreSQL — `SKIP LOCKED`](https://www.postgresql.org/docs/current/sql-select.html)
