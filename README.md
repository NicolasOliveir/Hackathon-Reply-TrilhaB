# Hackathon-Reply-TrilhaB

Squad autônomo de agentes de IA (PO → Dev → QA) que recebe um briefing de cliente e entrega
uma aplicação web funcional — cliente da simulação: **Rivexx Componentes** (gestão de não
conformidades, causa raiz e rastreabilidade de lote).

O humano entra uma vez, com o briefing. O squad faz o resto.

## Docs

| Documento | O que é |
|---|---|
| [AGENTS.md](AGENTS.md) | Regras obrigatórias para reserva, sincronização e entrega paralela |
| [TASKS.md](TASKS.md) | Quadro oficial de tarefas e responsáveis da iteração atual |
| [docs/DESCRICAO-TAREFA.md](docs/DESCRICAO-TAREFA.md) | Enunciado do hackathon — fonte, não editar |
| [docs/ESPEC.md](docs/ESPEC.md) | Spec colaborativa: ADRs, contratos de agente, cenários da demo |
| [docs/ENTENDIMENTO.md](docs/ENTENDIMENTO.md) | Leitura do enunciado, ataques prováveis e respostas arquiteturais |
| [docs/ORQUESTRADOR.md](docs/ORQUESTRADOR.md) | Arquitetura implementável, protocolo e backlog técnico do orquestrador |
| [docs/FLOWCHART.txt](docs/FLOWCHART.txt) | Topologia e sequência principal em formato texto |
| [docs/PO/SKILL.md](docs/PO/SKILL.md) | Decomposição de backlog e contrato operacional do PO Agent |

## Como rodar

Com Docker e Compose v2 disponíveis:

```bash
./tests/e2e/run.sh
```

O comando constrói uma instalação isolada, envia o briefing pelo painel em um
Chromium mobile e valida execução, timeline, retry e isolamento. Para manter o
ambiente de desenvolvimento rodando, siga [infra/README.md](infra/README.md).
Em máquinas com GNU Make, `make e2e` é um atalho equivalente.

## Estado

A primeira fatia distribuída funcional do MVP está implementada: painel React,
API central, PostgreSQL/event log, scheduler e fake worker efêmero. PO, Dev e
QA reais, integração com modelo e geração da aplicação continuam fora desta
iteração.
