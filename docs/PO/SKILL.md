---
name: backlog-decomposition
description: Transforma um briefing de cliente em um backlog pequeno, priorizado e auditável de user stories verticais, cujos critérios de aceitação um agente de QA independente consegue verificar sem nunca ler o briefing. Use quando o Product Owner precisar planejar uma execução nova, refinar um briefing ambíguo, quebrar trabalho grande demais ou confirmar que toda capacidade declarada foi coberta exatamente uma vez.
---

# Decomposição de Backlog

Converta o briefing recebido na menor sequência útil de resultados verificáveis de forma
independente. Permaneça dentro do problema e das restrições declaradas.

O backlog é um contrato, não um resumo. Os agentes seguintes nunca leem o briefing: o Dev
recebe uma story por vez e o QA recebe a story mais a evidência de execução. **Tudo que
ficar de fora de uma story se perde para o resto da execução.**

## Fluxo

1. Leia o briefing duas vezes. Na primeira passada, extraia usuários, objetivos,
   capacidades observáveis, restrições, riscos e exclusões explícitas. Na segunda, marque
   qual frase sustenta cada item extraído.
2. Classifique cada item como declarado, derivado, assumido ou inventado. Consulte
   [briefing-anchoring.md](briefing-anchoring.md) — a classificação decide o que pode
   virar story e o que precisa virar decisão antes.
3. Identifique um resultado fino de ponta a ponta que prove primeiro o laço do produto.
4. Quebre o restante em stories verticais. Evite camadas como "criar o backend" ou
   "construir a interface" como stories isoladas.
5. Ordene por dependência, depois redução de risco, depois valor para o usuário. Registre
   a dependência em `depende_de` e a justificativa em `justificativa_prioridade`.
6. Escreva critérios de aceitação como fatos observáveis, em uma linha, com resultado
   binário, `verificavel_por` e `verifica_restricao` declarados. Consulte
   [acceptancecriteria.md](acceptancecriteria.md).
7. Torne mensurável cada restrição que a story declara. Restrição sem valor objetivo no
   briefing exige `SUPOSICAO` com `lacuna` e `risco`, ou `needs_human` — nunca um número
   inventado dentro do texto do critério. Ver [contrato de saída](output-contract.md) §6.
8. Monte a matriz de cobertura e execute a verificação abaixo.
9. Congele: mova para `READY`, calcule o `frozen_hash` e valide a saída contra o
   [contrato de saída](output-contract.md) — schema e invariantes `I1`–`I27`. Story que não
   fecha sai como `DRAFT`. Devolva somente o envelope.

## Ancoragem

Toda story precisa remeter ao briefing.

- Transcreva em `origem` o trecho que a sustenta, citado ou parafraseado de perto.
- Requisito sem trecho correspondente é suposição. Registre como decisão `SUPOSICAO`, com
  justificativa e alternativa descartada; jamais deixe virar critério de aceitação
  silencioso.
- Capacidade que o briefing exige sem nomear é **derivação**, e é trabalho seu enxergar.
  O teste está em [briefing-anchoring.md](briefing-anchoring.md): derivado é o que, se
  removido, torna um requisito declarado impossível.
- Restrição declarada pelo cliente é requisito. Cada uma precisa aparecer como critério em
  alguma story e constar em `restricoes_aplicaveis`, não como prosa de contexto.
- Não invente autenticação, perfil de acesso, integração externa, deploy, notificação,
  relatório nem analytics que o briefing não pediu.

## Regras de qualidade da story

- Um resultado concreto de usuário ou operador por story.
- Título curto; use `narrativa` (`como` / `quero` / `para`) para o valor e `origem` para a
  ancoragem.
- Prefira de três a seis critérios precisos a uma lista longa de implementação.
- Inclua comportamento negativo ou de borda quando ele muda a correção visível.
- Não prescreva biblioteca, nome de arquivo, arquitetura ou estrutura de código, a menos
  que o briefing exija explicitamente.
- Duas stories não podem reivindicar o mesmo resultado observável. Resultado sobreposto
  torna a evidência do QA ambígua e produz vereditos contraditórios.
- Story que você não conseguiu completar sai como `DRAFT`, com a lacuna registrada em
  `decisions`. `READY` significa congelada e completa.

## Verificação de cobertura

Antes de devolver, liste toda capacidade e restrição declarada no briefing e marque cada
uma como:

- **COBERTA** — uma story e um critério específicos a atendem;
- **ADIADA** — deixada de fora deliberadamente, com decisão `ADIAMENTO` e o motivo;
- **ASSUMIDA** — inferida em vez de declarada, com decisão `SUPOSICAO`.

Capacidade que não cai em nenhum dos três estados é defeito do backlog. Corrija antes de
devolver. Quando o teto de stories forçar um corte, corte a capacidade de menor valor e
declare-a adiada — **corte silencioso passa a impressão de cobertura total e engana a
execução inteira.**

A recíproca também vale e é verificada por máquina: **story que nenhum item de cobertura
aponta é invenção** (invariante `I6`). Se uma story sua não tem origem no briefing, ou
você acha a origem, ou ela vira decisão `SUPOSICAO`, ou ela sai do backlog.

## Exigência de auditoria

Adicione uma decisão `tipo: SKILL` com título `Skill backlog-decomposition`. Declare o
objetivo de ativar a skill, o resultado da decomposição e qualquer divisão alternativa de
stories considerada. Se a skill não acrescentar valor para o briefing, registre esse
resultado em vez de fabricar mudanças.

## Verificação final

- [ ] todo critério é observável, cabe em uma linha e resolve em passou ou falhou;
- [ ] o QA conseguiria verificar cada critério tendo apenas a story em mãos;
- [ ] nenhuma story reivindica o mesmo resultado de outra;
- [ ] toda capacidade do briefing está `COBERTA`, `ADIADA` ou `ASSUMIDA`;
- [ ] toda story é apontada por ao menos um item de cobertura;
- [ ] `R1`–`R4` aparecem na matriz e nas stories a que se aplicam;
- [ ] toda restrição declarada em uma story tem um critério que a mede
      (`verifica_restricao`);
- [ ] todo valor numérico que o briefing não deu está autorizado por uma `SUPOSICAO`;
- [ ] nenhuma decisão de biblioteca, caminho de arquivo ou arquitetura vazou para dentro
      de uma story;
- [ ] suposições e adiamentos aparecem em `decisions`, com `lacuna` e `risco`;
- [ ] toda story `READY` tem `frozen_hash`; nenhuma story em `needs_human` está `READY`;
- [ ] a saída passa nas invariantes `I1`–`I27` do contrato de saída.
