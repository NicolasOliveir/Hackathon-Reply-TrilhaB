# Product Design Agent — mapa dos artefatos

Esta pasta define o agente que recebe stories congeladas do PO e produz a especificação de
experiência e interface usada pelo Developer na implementação de aplicações mobile e frontend.

| Arquivo | Papel |
|---|---|
| [persona.md](persona.md) | missão, autoridade, limites e critério de conclusão |
| [SKILL.md](SKILL.md) | procedimento para transformar uma story em design implementável |
| [design-contract.md](design-contract.md) | entrada, saída e handoff estruturado para Developer e QA |
| [mobile-frontend.md](mobile-frontend.md) | regras de UX, responsividade, acessibilidade e estados de tela |

## Precedência

1. [DESCRICAO-TAREFA.md](../DESCRICAO-TAREFA.md) é a fonte do desafio.
2. [ESPEC.md](../ESPEC.md) define o contrato compartilhado do squad.
3. A story congelada do PO é o único contrato de produto recebido pelo agente.
4. Estes arquivos definem como o Product Design Agent trabalha sem ampliar sua autoridade.

Em caso de divergência, a story e a ESPEC prevalecem. O agente registra uma dúvida ou bloqueio;
ele não altera critérios de aceite para acomodar uma solução visual.

## Posição no fluxo

```text
PO Agent -> story congelada -> Product Design Agent -> design handoff -> Developer Agent -> QA Agent
```

O Product Design Agent não lê o briefing bruto, não escreve código de produção e não aprova a
entrega. Seu resultado é uma especificação versionada, rastreável à story e suficiente para que
o Developer implemente a experiência sem inventar decisões de interface relevantes.
