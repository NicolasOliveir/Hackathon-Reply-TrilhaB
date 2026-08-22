---
name: backlog-decomposition
description: Transforma um briefing de cliente em um backlog pequeno, priorizado e auditável de user stories verticais, cujos critérios de aceitação um agente de QA independente consegue verificar sem nunca ler o briefing. Use quando o Product Owner precisar planejar uma execução nova, refinar um briefing ambíguo, quebrar trabalho grande demais ou confirmar que toda capacidade declarada foi coberta exatamente uma vez.
---

# Decomposição de Backlog

Converta o briefing recebido na menor sequência útil de resultados verificáveis de
forma independente. Permaneça dentro do problema e das restrições declaradas.

O backlog é um contrato, não um resumo. Os agentes seguintes nunca leem o
briefing: o Developer recebe uma story por vez e o QA recebe a story mais a
evidência de build e testes. **Tudo que ficar de fora de uma story se perde para o
resto da execução.**

## Fluxo

1. Leia o briefing duas vezes. Na primeira passada, extraia usuários, objetivos,
   capacidades observáveis, restrições, riscos e exclusões explícitas. Na segunda,
   marque qual frase sustenta cada item extraído.
2. Separe requisitos declarados dos derivados e das suposições. Consulte
   [briefing-anchoring.md](briefing-anchoring.md).
3. Identifique um resultado fino de ponta a ponta que prove primeiro o laço do
   produto.
4. Quebre o restante em stories verticais. Evite camadas como "criar o backend" ou
   "construir a interface" como stories isoladas.
5. Ordene por dependência, depois redução de risco, depois valor para o usuário.
6. Escreva critérios de aceitação como fatos observáveis com resultado binário.
   Consulte [acceptance-criteria.md](acceptance-criteria.md).
7. Execute a verificação de cobertura descrita abaixo.
8. Devolva somente a estrutura pedida pelo orquestrador.

## Ancoragem

Toda story precisa remeter ao briefing.

- Leve o trecho que a sustenta para a descrição da story, citado ou parafraseado
  de perto, para que o resto da execução consiga rastreá-lo.
- Requisito sem trecho correspondente é suposição. Registre como decisão, com a
  justificativa e a alternativa descartada; jamais deixe virar critério de
  aceitação silencioso.
- Restrição declarada pelo cliente — dispositivo, acessibilidade, evidência
  auditável, rastreabilidade — é requisito. Cada uma precisa aparecer como
  critério em alguma story, não como prosa de contexto.
- Não invente autenticação, perfil de acesso, integração externa, deploy,
  notificação, relatório ou analytics que o briefing não pediu.

## Regras de qualidade da story

- Um resultado concreto de usuário ou operador por story.
- Título curto; use a descrição para valor, contexto e ancoragem.
- Prefira de três a seis critérios precisos a uma lista longa de implementação.
- Inclua comportamento negativo ou de borda quando ele muda a correção visível.
- Não prescreva biblioteca, nome de arquivo, arquitetura ou estrutura de código, a
  menos que o briefing exija explicitamente.
- Expresse dependência pela ordenação e pelo conteúdo da story, nunca por
  suposição oculta sobre o que uma story posterior terá construído.
- Duas stories não podem reivindicar o mesmo resultado. Resultado sobreposto torna
  a evidência do QA ambígua e produz vereditos contraditórios.

## Verificação de cobertura

Antes de devolver, liste toda capacidade e restrição declarada no briefing e
marque cada uma como:

- **coberta** — uma story e um critério específicos a atendem;
- **adiada** — deixada de fora deliberadamente, registrada como decisão com o motivo;
- **assumida** — inferida em vez de declarada, registrada como decisão.

Capacidade que não cai em nenhum dos três estados é defeito do backlog. Corrija
antes de devolver. Quando o teto de stories forçar um corte, corte a capacidade de
menor valor e declare-a adiada — **corte silencioso passa a impressão de cobertura
total e engana a execução inteira.**

## Exigência de auditoria

Adicione uma decisão chamada `Skill backlog-decomposition` à saída estruturada.
Declare o objetivo de ativar a skill, o resultado da decomposição e qualquer
divisão alternativa de stories que tenha sido considerada. Se a skill não
acrescentar valor para o briefing, registre esse resultado em vez de fabricar
mudanças.

## Verificação final

- [ ] todo critério é observável e resolve em passou ou falhou;
- [ ] o QA conseguiria verificar cada critério tendo apenas a story em mãos;
- [ ] nenhuma story reivindica o mesmo resultado de outra;
- [ ] toda capacidade do briefing está coberta, adiada ou assumida;
- [ ] nenhuma decisão de biblioteca, caminho de arquivo ou arquitetura vazou para
      dentro de uma story;
- [ ] suposições e adiamentos aparecem em `decisions`, não apenas na prosa.
