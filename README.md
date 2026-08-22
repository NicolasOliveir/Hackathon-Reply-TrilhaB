# Hackathon-Reply-TrilhaB

Squad autônomo de agentes de IA (PO → Dev → QA) que recebe um briefing de cliente e entrega
uma aplicação web funcional — cliente da simulação: **Rivexx Componentes** (gestão de não
conformidades, causa raiz e rastreabilidade de lote).

O humano entra uma vez, com o briefing. O squad faz o resto.

## Docs

| Documento | O que é |
|---|---|
| [docs/DESCRICAO-TAREFA.md](docs/DESCRICAO-TAREFA.md) | Enunciado do hackathon — fonte, não editar |
| [docs/ESPEC.md](docs/ESPEC.md) | Spec colaborativa: ADRs, contratos de agente, cenários da demo |
| [docs/ENTENDIMENTO.md](docs/ENTENDIMENTO.md) | Leitura do enunciado, ataques prováveis e respostas arquiteturais |
| [docs/ORQUESTRADOR.md](docs/ORQUESTRADOR.md) | Arquitetura implementável, protocolo e backlog técnico do orquestrador |
| [docs/FLOWCHART.txt](docs/FLOWCHART.txt) | Topologia e sequência principal em formato texto |
| [docs/PO/README.md](docs/PO/README.md) | Mapa dos artefatos que definem o comportamento do PO Agent |

## Como rodar

`TODO` — a escrever por último, quando a demo estiver fechada (ver [ESPEC](docs/ESPEC.md) §3).

## Estado

Arquitetura do MVP definida; ainda não há aplicação nem orquestrador implementados. As cinco ADRs
estruturais estão fechadas, PO e Dev têm contratos em rascunho avançado e o QA ainda precisa ser
especificado. A implementação começa pela fatia distribuída mínima do
[plano do orquestrador](docs/ORQUESTRADOR.md) §13.
