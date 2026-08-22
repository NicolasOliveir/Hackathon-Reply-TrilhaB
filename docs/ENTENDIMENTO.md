# ENTENDIMENTO — leitura do enunciado e estado das decisões

> **Natureza deste documento:** análise, não decisão. Nada aqui vincula ninguém.
> Recomendação registrada aqui só vale quando virar `DECIDIDO` na [ESPEC](ESPEC.md) §4.
> **Última atualização:** 2026-08-22 · derivado de [DESCRICAO-TAREFA.md](DESCRICAO-TAREFA.md) e [ESPEC.md](ESPEC.md)
> **Para que serve:** dar ao time um ponto de partida sobre o que está sendo avaliado, onde o
> avaliador vai atacar e como as decisões atuais respondem a esses ataques.

---

## 1. O que está sendo avaliado

**O entregável não é o app da Rivexx. É o squad.**

O enunciado é explícito no critério de reprovação:

> "Um output final sem orquestração visível não será considerado."

Ou seja: a orquestração auditável **é** o produto avaliado. O app da Rivexx é a *evidência* de que
o squad funcionou. Um app impecável com orquestração invisível reprova; um app modesto com
cadeia PO → Dev → QA visível e íntegra passa.

Consequência prática para priorização: quando houver conflito entre polir o app e tornar a
orquestração mais legível/auditável, a orquestração ganha.

**Segunda leitura do enunciado:** o humano entra **uma vez**, com o briefing. Tudo depois disso
é do squad. Qualquer intervenção humana no meio da cadeia durante a demo é uma falha
observável, não um detalhe de execução.

---

## 2. Mapa enunciado → entregável

Cinco entregáveis exigidos. A ESPEC §2 já os mapeia para artefatos; o ponto a não perder é o
princípio embutido nesse mapeamento:

| # | Entregável exigido | Natureza |
|---|---|---|
| 1 | Squad funcional com comunicação visível entre agentes | sistema |
| 2 | Aplicação web rodando localmente, cobrindo os 3 cenários | sistema |
| 3 | Backlog gerado pelo PO Agent | **projeção** do event log |
| 4 | Log de decisões técnicas do Dev Agent | **projeção** do event log |
| 5 | Relatório de QA com casos executados e evidências | **projeção** do event log |

**Os entregáveis 3–5 não são arquivos mantidos à mão.** São views sobre o mesmo log
append-only. Isso não é preferência de arquitetura — é a única forma de os três serem
verdadeiros ao mesmo tempo e resistirem a inspeção. Backlog escrito à mão e log de ADR
escrito à mão são indistinguíveis de teatro, e é justamente isso que o enunciado rejeita.

---

## 3. Fronteiras dos papéis

O enunciado define os três papéis com fronteiras que são o coração da avaliação. Papel sem
fronteira dura vira "três prompts com nomes diferentes".

O PO já possui [persona e instruções operacionais](PO/README.md). Elas detalham a decomposição
do briefing, mas permanecem subordinadas ao contrato compartilhado da ESPEC §6.1.

| Agente | É o único que | Nunca |
|---|---|---|
| **PO** | lê o briefing bruto; cria e prioriza trabalho; define critério de aceite | especifica solução técnica; escreve caso de teste; aprova entrega |
| **Dev** | decide arquitetura; escreve código; registra ADR com justificativa | lê o briefing; declara sua própria entrega aprovada |
| **QA** | escreve e executa casos de teste contra os critérios do PO | inventa critério novo; libera o que não passou |

Duas fronteiras merecem atenção porque são as escorregadias:

- **ADR técnica vs. decisão de produto** (já anotada na ESPEC §6.2). "Escolhi Postgres porque X"
  é do Dev. "Decidi que o campo de foto é opcional" é do PO. Se o Dev decide a segunda, ele
  virou PO e a cadeia perdeu sentido.
- **Critério de aceite vs. caso de teste.** O critério é o contrato (PO); o caso de teste é a
  verificação (QA). Se o PO escreve o teste, o QA é decorativo. Se o QA escreve o critério, o
  PO é decorativo.

---

## 4. Superfície de ataque do avaliador

Onde a demo pode ser demonstrada como teatro. Cada item aqui é um teste que o avaliador pode
rodar em trinta segundos — vale ter resposta preparada para todos.

| # | Ataque | Pergunta que o avaliador faz | Defesa |
|---|---|---|---|
| A1 | **LLM declarando aprovado** | "Quem disse que passou?" | veredito vem de runner determinístico, não de julgamento de LLM — ver ADR-004 |
| A2 | **Briefing vazando para o Dev** | "Mostre o prompt exato que o Dev recebeu" | isolamento de contexto mecânico + forma de exibir o prompt real na demo (ESPEC §5.4) |
| A3 | **Cenários injetados** | "Você plantou os 3 cenários no PO?" | os 3 cenários estão no enunciado do **avaliador**, não no briefing da **Rivexx** — o PO tem de derivá-los do texto do cliente |
| A4 | **Replay pré-gravado** | "Rode de novo, com um briefing que eu escrevo" | ADR-001 tem de sobreviver a briefing novo, não só ao da Rivexx |
| A5 | **Teste que não roda** | "Esse teste realmente executou? Faça ele falhar" | evidência de execução no log, com saída real do runner; quebrar de propósito e ver reprovar |
| A6 | **Comunicação simulada** | "Esse 'diálogo' entre agentes é real ou narrado?" | event log com `causation_id` — cada evento aponta o evento que o disparou |

O A3 é o mais interessante, e a ESPEC já o identifica como "risco crítico": se o PO Agent derivar
os três cenários sozinho a partir da prosa do cliente, em execuções repetidas, esse é o momento
mais forte da demo. Se não derivar, o problema está na rubrica de priorização — não no PO.

O A5 merece ensaio explícito: demonstrar uma **reprovação** é mais convincente que demonstrar
dez aprovações. Um QA que nunca reprova nada é indistinguível de um QA que sempre aprova.

---

## 5. Decisões fechadas e dependências restantes

As cinco ADRs estruturais foram fechadas em 2026-08-22 e estão detalhadas na
[ESPEC §4](ESPEC.md) e em [ORQUESTRADOR.md](ORQUESTRADOR.md):

| ADR | Decisão do MVP |
|---|---|
| ADR-001 | plataforma e scaffold humanos; artefatos dos agentes produzidos ao vivo |
| ADR-002 | LangGraph determinístico com workers externos em containers efêmeros |
| ADR-003 | backend Python/FastAPI, painel React/TypeScript e runtime Docker |
| ADR-004 | QA cria testes; runner determinístico produz o veredito |
| ADR-005 | PostgreSQL único, relacional + `JSONB`, sem MongoDB no MVP |

O caminho crítico agora é de implementação: contratos → Compose/PostgreSQL → API/event log →
fake worker distribuído → PO real → ciclo Dev/QA/runner → demo Rivexx.

**Dívidas que permanecem:** criar o contrato do QA, escolher o provedor/modelo da demo e definir
volume/realismo dos seeds. `R1`–`R4` já possuem alvos verificáveis na ESPEC §1; o teste importante
agora é conferir se o backlog real os transcreve nas stories corretas.

---

## 6. Efeito das decisões sobre os ataques da avaliação

| Ataque | Resposta arquitetural |
|---|---|
| A1 — LLM se autoaprova | somente a API aceita uma story a partir do resultado do runner |
| A2 — briefing vaza | API filtra contexto e workspace do Dev/QA nasce sem os documentos do briefing |
| A3 — cenários injetados | continua dependendo do teste de convergência do PO em três execuções |
| A4 — replay | fluxo híbrido executa agentes e gera artefatos ao vivo sobre scaffold declarado |
| A5 — teste não executa | runner isolado persiste comando, exit code, resultados e evidências |
| A6 — comunicação simulada | toda saída passa pela API e gera evento com correlação e causalidade |

O teste de convergência do PO e uma reprovação real continuam sendo os dois ensaios de maior
valor antes de polir a interface.

---

## 7. Estado do repositório hoje (2026-08-22)

```
/
├── README.md                    ← visão geral; instruções de execução ainda pendentes
└── docs/
    ├── DESCRICAO-TAREFA.md      ← enunciado do hackathon (fonte, não editar)
    ├── ESPEC.md                 ← decisões e contratos compartilhados
    ├── ENTENDIMENTO.md          ← este documento; análise, não decisão
    ├── ORQUESTRADOR.md          ← arquitetura implementável e backlog técnico
    ├── FLOWCHART.txt            ← topologia e sequência em texto
    ├── PO/
        ├── README.md            ← mapa e precedência dos artefatos do PO
        ├── persona.md           ← missão, autoridade e limites de contexto
        ├── SKILL.md             ← fluxo de decomposição de backlog
        └── acceptancecriteria.md ← critérios binários e reproduzíveis
    └── dev/
        ├── persona.md           ← missão, autoridade e limites do Dev
        ├── SKILL.md             ← implementação e remediação
        ├── task-contract.md     ← contrato de tasks, ADR e entrega
        └── qa-remediation.md    ← protocolo após reprovação
```

Ainda não há aplicação nem orquestrador implementados. A arquitetura e as cinco ADRs estão
fechadas; PO e Dev têm definição em rascunho avançado, enquanto QA segue em `TODO`. O próximo
incremento deve ser a fatia distribuída mínima com fake worker descrita em ORQUESTRADOR §13.
