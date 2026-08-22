# Critérios de Validação Base (Rivexx)

Este documento é uma referência para o planejamento inicial de testes. Ele não
substitui os critérios canônicos emitidos pelo PO: o QA só pode executar e
reportar os critérios presentes na story congelada, literalmente e na ordem
recebida. Os alvos objetivos definidos na ESPEC devem ser transcritos pelo PO
nos critérios aplicáveis antes de virarem vereditos de QA.

## Cenário 1: Registro Ágil de Não Conformidades

- O formulário deve aceitar entradas de dispositivos móveis (responsividade para
  o chão de fábrica), conforme o viewport objetivo definido na story ou ESPEC.
- O envio do registro deve bloquear caso faltem os metadados auditáveis: Data,
  Responsável, Turno e Equipamento.

## Cenário 2: Análise de Causa Raiz Assistida

- A interface deve exibir sugestões estruturadas baseadas em dados históricos de
  registros anteriores.
- O sistema deve gerar um plano de ação contendo metas e responsáveis de forma
  automática após a conclusão da análise.

## Cenário 3: Rastreabilidade de Lote

- A busca por um código de lote deve retornar a árvore completa de dependências
  em segundos: fornecedor do insumo, equipamento utilizado, turno da produção,
  operadores envolvidos e lotes de produtos correlatos gerados no mesmo período.
