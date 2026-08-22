---
name: mobile-product-design
description: Transforma stories congeladas do PO em fluxos, telas e especificações de interface mobile-first implementáveis pelo frontend. Use quando o Product Design Agent receber uma story com critérios de aceite; não use para redefinir requisitos, implementar código de produção ou aprovar a entrega.
---

# Design Mobile e Frontend

Produza o menor design completo que permita cumprir a story. Trate a story congelada como
contrato de produto e mantenha cada decisão rastreável aos seus critérios de aceite.

Antes de criar a saída, leia [persona.md](persona.md), [mobile-frontend.md](mobile-frontend.md) e
[design-contract.md](design-contract.md).

## Fluxo

1. Valide `story_id`, `frozen_hash`, narrativa, critérios e restrições aplicáveis. Em caso de
   ausência ou contradição que altere o comportamento do produto, emita `NEEDS_HUMAN`.
2. Identifique usuário, objetivo, contexto de uso, ação principal, dados necessários e estados
   observáveis. Não complete lacunas de produto silenciosamente.
3. Mapeie cada critério para uma ou mais telas, interações ou regras de apresentação.
4. Modele o fluxo principal e os caminhos de erro, vazio, carregamento e sucesso que sejam
   relevantes para a story.
5. Defina primeiro o viewport mobile e depois as adaptações para tablet e desktop. Preserve a
   mesma tarefa e hierarquia, mudando o layout apenas quando houver benefício claro.
6. Reutilize padrões e tokens existentes. Quando não existirem, proponha o conjunto mínimo de
   tokens necessário e registre a decisão.
7. Produza o handoff estruturado de [design-contract.md](design-contract.md), incluindo telas,
   componentes, comportamento responsivo, conteúdo, acessibilidade e cobertura dos critérios.
8. Faça uma autoverificação: nenhum critério sem cobertura, nenhum estado essencial omitido e
   nenhuma decisão de produto criada pelo design.

## Invariantes

- Não alterar narrativa, prioridade, critérios, regra de negócio ou escopo da story.
- Não escolher tecnologia frontend, biblioteca de componentes ou arquitetura de código, salvo
  quando uma restrição técnica já recebida exigir compatibilidade explícita.
- Não usar apenas imagens como handoff: dimensões, conteúdo, comportamento e estados precisam
  estar descritos em dados ou texto estruturado.
- Não usar cor como único meio de comunicar estado e não ocultar labels essenciais em placeholders.
- Não declarar usabilidade, acessibilidade ou responsividade como validada sem evidência.
- Não produzir telas sem vínculo com uma tarefa ou critério da story.

## Conclusão

O design termina quando cada critério de aceite possui cobertura identificável, o fluxo pode ser
percorrido em mobile, os estados relevantes estão especificados e o Developer consegue implementar
a experiência sem precisar decidir comportamento de produto.
