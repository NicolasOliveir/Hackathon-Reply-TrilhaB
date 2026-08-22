# Contrato de Saída do PO Agent

A forma canônica do envelope pertence à [ESPEC §6.1](../ESPEC.md). Este arquivo não a
redefine: ele a torna **verificável** — schema formal, invariantes entre campos, regra de
congelamento e projeção para o evento que o QA consome. Em divergência, a ESPEC prevalece.

Motivo de existir: um exemplo em JSON diz como a saída se parece. Ele não diz o que torna
uma saída **inválida**. É a lista de inválidos que impede o PO de inventar escopo, porque
transforma regra de prompt em rejeição mecânica.

---

## 1. Schema

JSON Schema draft-07 — neutro de stack, consumível por Zod, Pydantic, `--output-schema`
ou structured output.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["stories", "decisions", "cobertura", "needs_human"],
  "additionalProperties": false,
  "properties": {
    "stories": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["id", "version", "titulo", "narrativa", "origem", "prioridade",
                     "justificativa_prioridade", "depende_de", "restricoes_aplicaveis",
                     "premissas", "criterios_aceite", "fora_de_escopo", "estado",
                     "frozen_hash"],
        "additionalProperties": false,
        "properties": {
          "id": { "type": "string", "pattern": "^US-[0-9]{3}$" },
          "version": { "type": "integer", "minimum": 1 },
          "titulo": { "type": "string", "minLength": 1, "maxLength": 80 },
          "narrativa": {
            "type": "object",
            "required": ["como", "quero", "para"],
            "additionalProperties": false,
            "properties": {
              "como": { "type": "string", "minLength": 1 },
              "quero": { "type": "string", "minLength": 1 },
              "para": { "type": "string", "minLength": 1 }
            }
          },
          "origem": { "type": "array", "items": { "type": "string", "minLength": 1 } },
          "prioridade": { "type": "integer", "minimum": 1 },
          "justificativa_prioridade": { "type": "string", "minLength": 1 },
          "depende_de": {
            "type": "array",
            "items": { "type": "string", "pattern": "^US-[0-9]{3}$" }
          },
          "restricoes_aplicaveis": {
            "type": "array",
            "items": { "enum": ["R1", "R2", "R3", "R4"] }
          },
          "premissas": { "type": "array", "items": { "type": "string", "minLength": 1 } },
          "criterios_aceite": {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "required": ["id", "texto", "verificavel_por", "verifica_restricao"],
              "additionalProperties": false,
              "properties": {
                "id": { "type": "string", "pattern": "^AC-[0-9]+$" },
                "texto": { "type": "string", "minLength": 1 },
                "verificavel_por": { "enum": ["ui", "dados", "api"] },
                "verifica_restricao": {
                  "type": ["string", "null"],
                  "enum": ["R1", "R2", "R3", "R4", null]
                }
              }
            }
          },
          "fora_de_escopo": { "type": "array", "items": { "type": "string" } },
          "estado": { "enum": ["DRAFT", "READY"] },
          "frozen_hash": {
            "type": ["string", "null"],
            "pattern": "^sha256:[0-9a-f]{64}$"
          }
        }
      }
    },
    "decisions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["titulo", "tipo", "lacuna", "justificativa", "risco",
                     "alternativa_descartada"],
        "additionalProperties": false,
        "properties": {
          "titulo": { "type": "string", "minLength": 1 },
          "tipo": { "enum": ["SUPOSICAO", "ADIAMENTO", "SKILL"] },
          "lacuna": { "type": ["string", "null"] },
          "justificativa": { "type": "string", "minLength": 1 },
          "risco": { "enum": ["BAIXO", "MEDIO", "ALTO", null] },
          "alternativa_descartada": { "type": "string" }
        }
      }
    },
    "cobertura": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["item", "origem", "estado", "story_id", "criterio_id",
                     "decision_titulo"],
        "additionalProperties": false,
        "properties": {
          "item": { "type": "string", "minLength": 1 },
          "origem": { "type": ["string", "null"] },
          "estado": { "enum": ["COBERTA", "ADIADA", "ASSUMIDA"] },
          "story_id": { "type": ["string", "null"] },
          "criterio_id": { "type": ["string", "null"] },
          "decision_titulo": { "type": ["string", "null"] }
        }
      }
    },
    "needs_human": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["motivo", "estado", "story_id", "restricao"],
        "additionalProperties": false,
        "properties": {
          "motivo": { "type": "string", "minLength": 1 },
          "estado": { "type": "string", "minLength": 1 },
          "story_id": { "type": ["string", "null"] },
          "restricao": { "enum": ["R1", "R2", "R3", "R4", null] }
        }
      }
    }
  }
}
```

`decisions[]` mapeia para o evento `PREMISSA_ASSUMIDA` da [ESPEC §5.2](../ESPEC.md)
(`lacuna, premissa, risco`): `lacuna` → `lacuna`; `titulo` + `justificativa` → `premissa`;
`risco` → `risco`.

---

## 2. Invariantes

O schema garante forma. Estas regras garantem **coerência**, e nenhuma delas cabe em JSON
Schema. Rodam como validação depois do parse. Violação é rejeição, não aviso.

### 2.1 Identidade e ordem

| # | Regra |
|---|---|
| `I1` | `stories[].id` é único |
| `I2` | `prioridade` forma a sequência `1..n`, sem repetição e sem lacuna |
| `I3` | `criterios_aceite[].id` é único dentro da story |
| `I4` | Todo `depende_de` aponta para um `id` existente com `prioridade` **menor** que a da própria story |
| `I5` | Nenhuma story depende de si mesma, direta ou transitivamente |

`I4` elimina ciclo de dependência e garante que a ordem de prioridade é executável na
sequência declarada.

### 2.2 Ancoragem — o núcleo anti-invenção

| # | Regra |
|---|---|
| `I6` | **Toda story é apontada por ao menos um item de `cobertura` com `estado: COBERTA`** |
| `I7` | `origem` vazio só é válido se a story for referenciada por item de cobertura com `estado: ASSUMIDA` |
| `I8` | `estado: COBERTA` exige `story_id` e `criterio_id` não nulos e existentes, e `decision_titulo` nulo |
| `I9` | `estado: ADIADA` exige `decision_titulo` de uma decisão `tipo: ADIAMENTO`, com `story_id` e `criterio_id` nulos |
| `I10` | `estado: ASSUMIDA` exige `decision_titulo` de uma decisão `tipo: SUPOSICAO`, e `origem: null` |
| `I11` | Todo `decision_titulo` citado existe em `decisions[].titulo` |
| `I12` | `decisions[].titulo` é único |

`I6` é a invariante central do contrato. Ela converte "não invente escopo" de instrução de
prompt em **rejeição verificável**: funcionalidade inventada não tem origem no briefing,
logo não gera item de cobertura, logo a story fica órfã e a saída é recusada.

### 2.3 Restrições transversais

| # | Regra |
|---|---|
| `I13` | `R1`, `R2`, `R3` e `R4` aparecem cada uma como item de `cobertura` |
| `I14` | Restrição com `estado: COBERTA` consta em `restricoes_aplicaveis` da story citada |
| `I19` | **Para cada `R` em `restricoes_aplicaveis`, existe ao menos um critério na mesma story com `verifica_restricao == R`** |
| `I22` | Critério com `verifica_restricao != null` só é válido se aquela restrição constar em `restricoes_aplicaveis` da story |

`I14` sozinha é decorativa: ela verifica que a restrição foi **declarada**, não que foi
**medida**. Uma story podia declarar `R1` sem nenhum critério sobre viewport e passar.
`I19` fecha isso — e é por ela que o campo `verifica_restricao` existe.

### 2.4 Critérios

| # | Regra |
|---|---|
| `I15` | `texto` não contém quebra de linha |
| `I16` | `texto` é único em todo o backlog — critérios idênticos tornam o veredito do QA ambíguo |
| `I17` | Story `READY` tem todos os critérios preenchidos e é imutável a partir daí |

`texto` é a **representação canônica congelada**. O QA a reproduz sem paráfrase, uma vez e
na ordem declarada.

### 2.5 Premissas e bloqueios

| # | Regra |
|---|---|
| `I23` | Todo título em `stories[].premissas` existe em `decisions[]` com `tipo: SUPOSICAO` |
| `I24` | Decisão `tipo: SUPOSICAO` ou `ADIAMENTO` tem `lacuna` e `risco` não nulos |
| `I25` | Story citada em `needs_human[].story_id` está em `estado: DRAFT` |
| `I26` | Restrição citada em `needs_human[].restricao` não aparece como `COBERTA` na matriz de cobertura |

`I25` é a regra que impede o pior caso: uma story congelada e despachada ao Dev enquanto o
próprio PO declarou que precisa de decisão humana sobre ela.

### 2.6 Congelamento

| # | Regra |
|---|---|
| `I20` | `frozen_hash` confere com a serialização canônica da seção 3 |
| `I21` | `version` ≥ 1; story `READY` com `version > 1` exige um `STORY_REOPENED` anterior no event log |
| `I27` | `frozen_hash` é não nulo se e somente se `estado: READY` |

### 2.7 Auditoria da skill

| # | Regra |
|---|---|
| `I18` | Existe exatamente uma decisão com `tipo: SKILL` e `titulo: "Skill backlog-decomposition"` |

---

## 3. Congelamento e hash canônico

Sem hash, "congelado" é política. Com hash, é verificável: o QA reporta o `frozen_hash`
que validou, o orquestrador compara com o emitido, e divergência invalida o relatório.
A comparação literal de string pega paráfrase do QA; o hash pega troca de critério entre o
congelamento e a validação.

### 3.1 Payload

```
{"criterios_aceite":[...],"story_id":"US-001","version":1}
```

Cada critério entra como:

```
{"id":"AC-1","texto":"...","verifica_restricao":"R1","verificavel_por":"ui"}
```

### 3.2 Regras de serialização

Duas implementações só chegam ao mesmo hash se seguirem todas:

1. JSON, codificado em UTF-8.
2. Nenhum espaço em branco entre tokens.
3. Chaves de cada objeto em ordem lexicográfica de code point.
4. `criterios_aceite` na ordem declarada — **não** reordenar.
5. `null` serializado como `null`, nunca omitido.
6. Nenhum campo além dos listados em 3.1.

A ordem lexicográfica das chaves do critério é `id`, `texto`, `verifica_restricao`,
`verificavel_por` — `_` (U+005F) precede `v` (U+0076).

### 3.3 Cálculo

```
frozen_hash = "sha256:" + hex_minusculo(SHA256(payload_em_bytes))
```

Calculado no instante em que a story passa a `READY`. Recalculado apenas em nova
`version`, depois de um `STORY_REOPENED`.

---

## 4. Projeção `STORY_FROZEN`

O envelope da seção 1 é entregue uma vez, ao orquestrador. O QA consome **um evento por
story**. A projeção abaixo é a regra de derivação — e é também a **fronteira de
isolamento**: o que entra neste evento define o que o QA tem permissão de saber.

### 4.1 Forma

```json
{
  "event_type": "STORY_FROZEN",
  "story_id": "US-001",
  "version": 1,
  "frozen_hash": "sha256:...",
  "titulo": "Registro de não conformidade no chão de fábrica",
  "criterios_aceite": [
    {
      "id": "AC-1",
      "texto": "Em uma viewport de 320 px, o formulário de registro não apresenta rolagem horizontal.",
      "verificavel_por": "ui",
      "verifica_restricao": "R1"
    },
    {
      "id": "AC-2",
      "texto": "Ao enviar o formulário sem preencher Turno, o registro não é criado e a mensagem \"Turno obrigatório\" é exibida.",
      "verificavel_por": "ui",
      "verifica_restricao": "R3"
    }
  ],
  "restricoes_aplicaveis": ["R1", "R3"],
  "depende_de": [],
  "premissas": [
    {
      "titulo": "Viewport mínimo de 320 px",
      "lacuna": "O briefing exige registro pelo celular mas não declara largura mínima.",
      "justificativa": "320 px é a menor largura de uso corrente; falhar aí garante as maiores.",
      "risco": "BAIXO"
    }
  ],
  "fora_de_escopo": ["Edição de registro após salvar"]
}
```

### 4.2 O que **não** é projetado, e por quê

| Campo | Motivo da exclusão |
|---|---|
| `origem` | Contém trecho literal do briefing. Projetá-lo faria o QA ler briefing e derrubaria a matriz de isolamento da [ESPEC §5.4](../ESPEC.md) — junto com o argumento de que a orquestração não é encenação |
| `narrativa` | É motivação, não obrigação. QA que julga pelo "espírito da story" em vez do critério é exatamente o modo de falha que o congelamento existe para impedir |
| `justificativa_prioridade` | Raciocínio de negócio do PO; irrelevante para verificação |
| `prioridade` | O orquestrador já ordenou o despacho; o QA não decide ordem |
| `cobertura` | Matriz do backlog inteiro, e carrega `origem` |
| `decisions` completo | Só as premissas ligadas à story passam, e **sem** `alternativa_descartada` — a alternativa descartada é raciocínio do PO, não obrigação a verificar |
| `estado` | Só story `READY` é projetada; o campo seria constante |

### 4.3 Quando é emitido

Uma story só é projetada quando `estado: READY` e `frozen_hash` não nulo. Story `DRAFT`
não gera `STORY_FROZEN` — gera `NEEDS_HUMAN` se estiver em `needs_human[]`, ou permanece
no backlog aguardando complemento.

---

## 5. Determinismo

Duas execuções sobre o mesmo briefing devem produzir backlogs comparáveis. Sem isso, o
teste de convergência dos três cenários (ESPEC §6.1) não tem como ser avaliado.

- `stories` sai ordenado por `prioridade` crescente.
- `cobertura` sai na ordem em que os itens aparecem no briefing.
- IDs são atribuídos por posição depois da ordenação: prioridade 1 é `US-001`.
- `criterios_aceite` sai na ordem de exercício: criar, ler, editar, borda.
- `version` começa em 1 em toda story recém-criada.

> `temperature` e política de retry em falha de schema seguem `ABERTO` na ESPEC §6.1.
> Enquanto não fecharem, comparar execuções mede o modelo **e** a configuração ao mesmo
> tempo, sem isolar nenhum dos dois.

---

## 6. Tornar as restrições mensuráveis antes de congelar

`I19` exige que toda restrição declarada tenha critério que a meça. Isso obriga a
converter texto de restrição em valor observável — e o briefing sustenta cada uma em grau
diferente. Aplicando a régua de [briefing-anchoring.md](briefing-anchoring.md):

| | O que o briefing dá | Classificação | Exige |
|---|---|---|---|
| `R1` | "operadores registram pelo celular no chão de fábrica" — sem número | Assumido | `SUPOSICAO` para o viewport |
| `R2` | "interface operável sem treinamento técnico" — sem valor objetivo derivável | Assumido, risco alto | `SUPOSICAO` com ação observável, ou `NEEDS_HUMAN` |
| `R3` | "data, responsável, turno e equipamento" — literal | **Declarado** | nada |
| `R4` | campos da árvore declarados no cenário 3; tempo apenas como "em segundos" | Misto | `SUPOSICAO` só para o teto de tempo |

**Regra dura:** se o briefing não dá valor objetivo, o PO **não o inventa em silêncio**.
Ou registra `SUPOSICAO` com `lacuna` e `risco`, ou emite `needs_human`. Um número que
aparece apenas dentro do `texto` de um critério, sem decisão que o autorize, é invenção —
e `I24` não o pega, porque a invenção está no texto livre. É por isso que a régua acima é
parte do contrato e não apenas orientação.

Notas por restrição:

- **`R3` é o único que fecha sem suposição.** O bloqueio de registro incompleto é
  *derivação*, não invenção: "todo registro com evidência auditável" torna impossível um
  registro sem os quatro metadados.
- **`R4` se divide.** Os campos da árvore — matéria-prima, fornecedor, equipamento, turno,
  operadores e lotes correlatos — são declarados. Só o teto de tempo é assumido.
- **`R2` merece cuidado com `NEEDS_HUMAN`.** É a saída correta pela regra, mas
  `NEEDS_HUMAN` no caminho da demo quebra o "tudo em cadeia, sem intervenção humana" do
  cenário 1 do enunciado. `SUPOSICAO` com `risco: ALTO` e uma ação observável é a saída
  que preserva a cadeia e mantém a honestidade no relatório.

---

## 7. O que o PO não emite

| Campo | Por quê |
|---|---|
| `caso_de_teste` | Critério de aceite é o contrato; caso de teste é a verificação, e pertence ao QA |
| `estimativa` | Não há requisito no enunciado, e viraria compromisso não verificável |
| `solucao`, `stack`, `componente` | Decisão do Dev |
| `aprovado`, `aceito` | Não existe transição para `ACCEPTED` disponível ao PO |
| `FROZEN` como valor de `estado` | Ver seção 8.1 |

---

## 8. Pendências conhecidas

**8.1 `READY` vs `FROZEN`.** A ESPEC §6.1 declara `estado: "DRAFT | READY | FROZEN"` e, na
função 10, "congelar a story ao movê-la para `READY`". Se `READY` já congela, `FROZEN` não
tem significado distinto. Resolução provisória, a ratificar:

- o **PO emite** `DRAFT` (incompleta, lacuna declarada) ou `READY` (congelada, com hash);
- `FROZEN`, se for mantido, é aplicado pelo **orquestrador** no despacho.

Enquanto não houver decisão, `FROZEN` está fora do enum de saída.

**8.2 Prefixo do ID.** A ESPEC exemplifica `id: "NC-003"`. `NC` é a sigla da entidade
central do domínio Rivexx — não conformidade. Um `NC-003` no event log fica ambíguo entre
"story 3" e "não conformidade 3", e o Dev lê os dois no mesmo contexto. Este contrato usa
`US-###`. Se a ESPEC mantiver `NC-`, o `pattern` do schema muda junto.

**8.3 `STORY_REOPENED` não existe.** `I21` referencia esse evento, mas ele não está na
tabela da ESPEC §5.2. Sem ele, `version` nunca passa de 1 e uma story com critério ambíguo
só tem saída por `NEEDS_HUMAN`. Definir: quem emite (orquestrador), sob que condição
(N reprovações da mesma story), e que o PO reescreve gerando `version + 1` em vez de
editar a congelada.

**8.4 Rubrica de priorização.** `ABERTO` na ESPEC §6.1. Sem ela,
`justificativa_prioridade` é prosa livre e o teste de convergência não tem baseline.
