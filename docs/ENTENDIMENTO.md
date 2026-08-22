# ENTENDIMENTO — leitura do enunciado e estado das decisões

> **Natureza deste documento:** análise, não decisão. Nada aqui vincula ninguém.
> Recomendação registrada aqui só vale quando virar `DECIDIDO` na [ESPEC](ESPEC.md) §4.
> **Última atualização:** 2026-08-22 · derivado de [DESCRICAO-TAREFA.md](DESCRICAO-TAREFA.md) e [ESPEC.md](ESPEC.md)
> **Para que serve:** dar ao time um ponto de partida sobre o que está sendo avaliado, onde o
> avaliador vai atacar, e em que ordem as ADRs abertas precisam cair.

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

## 5. Ordem em que as decisões precisam cair

As cinco ADRs abertas não são independentes. Derivado das próprias marcações de bloqueio da
ESPEC:

```
ADR-003 (stack)  ──────┬──> todo o /squad (ESPEC §3, §5)
ADR-001 (escopo live) ─┴──> cronograma, quanto do app é scaffold

ADR-002 (topologia) ───────> ESPEC §5.1 (hoje BLOQUEADO), §5.3

ADR-004 (veredito) ────────> contrato do QA (§6.3), formato do relatório

ADR-005 (persistência) ────> rastreabilidade (§7.2, hoje BLOQUEADO)

R1–R4 sem verificação ─────> contrato do QA — transversal a toda story
```

**Caminho crítico:** ADR-003 e ADR-001 primeiro, porque destravam a estrutura do repositório e o
cronograma. ADR-002 e ADR-004 em seguida (definem o contrato do QA). ADR-005 pode ir em
paralelo — é local ao app, não ao squad.

**A dívida que não está numerada como ADR mas bloqueia igual:** a coluna "como se verifica" das
restrições `R1`–`R4` na ESPEC §1 está inteira em `TODO`. A própria ESPEC avisa que *"restrição sem
meio de verificação é decoração"*. Enquanto ela estiver vazia, o QA Agent não tem contra o que
testar as restrições transversais — e o enunciado lista as quatro como restrições do cliente,
não como sugestões. `R2` ("operável sem treinamento técnico") é a mais difícil de objetivar e já
está registrada como Q3.

---

## 6. Recomendações abertas ao time

Insumo para discussão. Nenhuma destas é decisão; cada uma precisa virar ADR na ESPEC §4 para
valer.

**ADR-004 (veredito de aceite) — tratar como a mais urgente.** A própria ESPEC anota o motivo: se
um LLM declara "aprovado", ele é o elo fraco e o ponto óbvio de ataque (A1). Recomendação:
veredito determinístico do test runner; o QA Agent escreve o plano e os testes, e não julga o
resultado. Isso torna o entregável 5 uma projeção de saída de runner, não de opinião de modelo —
e é o que permite responder ao A5 sem hesitar.

**ADR-002 (topologia).** Grafo de estados determinístico com LLM só dentro dos nós tende a ser
mais defensável que chat livre: transições auditáveis, isolamento de contexto mecânico (A2) e
sem risco de os agentes negociarem fora do protocolo. Chat livre parece mais impressionante em
tese e é mais frágil sob inspeção.

**ADR-001 (escopo live).** O híbrido — plataforma humana + features geradas ao vivo — é o único
que sobrevive ao A4 sem ser frágil. Vale definir junto com ele *o que exatamente* é scaffold, e
ter isso escrito antes da demo, para responder à pergunta "o que aí é seu e o que é do squad?".

**Ensaio a agendar cedo, independente das ADRs:** o teste de convergência do PO (3 execuções, o
PO chega nos 3 cenários?) já está previsto na ESPEC §6.1 sem dono. Ele valida ou derruba o A3, que
é o momento mais forte ou o furo mais visível da demo. Descobrir isso tarde é caro.

---

## 7. Estado do repositório hoje (2026-08-22)

```
/
├── README.md                    ← visão geral; instruções de execução ainda pendentes
└── docs/
    ├── DESCRICAO-TAREFA.md      ← enunciado do hackathon (fonte, não editar)
    ├── ESPEC.md                 ← esqueleto colaborativo; maioria em TODO / ABERTO
    ├── ENTENDIMENTO.md          ← este documento; análise, não decisão
    └── PO/
        ├── README.md            ← mapa e precedência dos artefatos do PO
        ├── persona.md           ← missão, autoridade e limites de contexto
        ├── SKILL.md             ← fluxo de decomposição de backlog
        └── acceptancecriteria.md ← critérios binários e reproduzíveis
```

Ainda não há aplicação nem orquestrador e nenhuma das cinco ADRs foi decidida. O PO é o único
agente com definição em rascunho avançado; Dev e QA seguem em `TODO`. A estrutura de execução
da ESPEC §3 continua proposta (`ABERTO`) e depende de ADR-003 para saber se será monorepo TS ou
Python + app separado.
