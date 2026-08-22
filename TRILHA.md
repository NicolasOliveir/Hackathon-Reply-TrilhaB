O Desafio
O seu time precisa criar um squad autônomo de agentes de IA que, ao receber um briefing de
cliente, seja capaz de, por conta própria e de forma orquestrada, entender o problema,
quebrar em stories, escrever o código, testar e entregar uma solução funcional.
O time humano entra no início, com o briefing. O squad de agentes faz o resto.

Como o Squad Funciona
O squad deve ter no mínimo 3 agentes com papéis distintos, comunicando-se entre si como
um time de desenvolvimento real:
• PO Agent — recebe o briefing, interpreta o problema, escreve as user stories
priorizadas com critérios de aceite e alimenta o backlog. É o único ponto de contato
com o problema do cliente
• Dev Agent — consome as stories do PO Agent, toma decisões de arquitetura, escreve
o código seguindo boas práticas e registra cada decisão técnica com justificativa
• QA Agent — intercepta cada entrega do Dev Agent, cria e executa os casos de teste
contra os critérios de aceite definidos pelo PO Agent e só libera o que estiver validado
A comunicação entre os agentes deve ser explícita e auditável — o avaliador precisa enxergar
o squad trabalhando junto, tomando decisões, passando contexto entre si. Um output final
sem orquestração visível não será considerado.

O Briefing que o Squad vai receber
Empresa: Rivexx Componentes Indústria de componentes plásticos de alta precisão, 2 plantas,
fornecimento para os setores automotivo e eletroeletrônico. Certificada, auditada
trimestralmente, 480 colaboradores, operação em 3 turnos.
O problema: Toda não conformidade detectada — internamente ou pelo cliente —
desencadeia uma investigação manual. Quem operou, qual lote, qual matéria-prima, qual
equipamento. A informação existe, mas está espalhada em registros físicos, planilhas e
memória de pessoas. Reconstituir o histórico leva horas. A causa raiz vira opinião. O plano de
ação vira promessa sem monitoramento. E quando um cliente aciona a Rivexx por um defeito,
ninguém consegue responder rapidamente quais lotes foram afetados e onde estão.
O que a Rivexx precisa: Uma aplicação web interna que centralize o registro de não
conformidades, conduza a análise de causa raiz com metodologia estruturada, gere e monitore
planos de ação corretiva — e permita rastrear qualquer lote em segundos, do insumo recebido
ao produto expedido.
Restrições do cliente:
• Aplicação responsiva — operadores registram pelo celular no chão de fábrica
• Interface operável sem treinamento técnico

• Todo registro com evidência auditável — data, responsável, turno e equipamento
• Rastreabilidade de lote cobrindo toda a cadeia produtiva

O que a Demo do Squad precisa mostrar
O avaliador vai acionar o squad com o briefing acima e observar os agentes trabalhando. A
demo precisa cobrir obrigatoriamente:
Cenário O que o squad precisa entregar

Registro ágil

Operador descreve defeito dimensional na linha 4. O PO Agent gera a
story, o Dev Agent entrega o formulário de registro responsivo, o QA
Agent valida contra o critério de aceite — tudo em cadeia, sem
intervenção humana

Causa raiz
assistida

A partir do registro, o squad entrega a tela de análise estruturada com
sugestão de causas baseada no histórico e geração automática do plano
de ação corretiva

Rastreabilidade
de lote

Coordenador informa o código do lote. O squad entrega a tela que mapeia
toda a cadeia — matéria-prima, fornecedor, equipamento, turno,
operadores e lotes correlatos

Entregáveis
• Squad funcional com agentes orquestrados e comunicação visível entre eles
• Aplicação web rodando localmente cobrindo os 3 cenários
• Backlog gerado pelo PO Agent
• Log de decisões técnicas do Dev Agent
• Relatório de QA com casos executados e evidências de aceite
