# Tests

Testes de integração e ponta a ponta. Testes próprios de um pacote permanecem dentro do pacote;
a fatia E2E distribuída pertence à tarefa `I1-007`.

## Fatia distribuída completa

Pré-requisito único: Docker com Compose v2 e acesso ao daemon local.

```bash
./tests/e2e/run.sh
```

`make e2e` é apenas um atalho opcional; o script acima não depende de Make,
Node ou Python instalados no host.

O comando cria o projeto isolado `rivexx-e2e`, com banco e imagens próprios,
e sempre o remove ao terminar. Ele não apaga os volumes do ambiente
`rivexx-squad` usado no desenvolvimento.

As evidências impressas são:

- Chromium mobile envia o briefing pelo painel React real;
- API cria uma única task e o scheduler inicia um único fake worker;
- callback conclui o run e os seis eventos aparecem na timeline em cadeia;
- repetição da mesma `Idempotency-Key` mantém o mesmo `run_id`;
- retomada SSE após `sequence=3` entrega somente `4, 5, 6`;
- probe com a imagem e as restrições do worker alcança apenas a API, não
  resolve/alcança PostgreSQL e não possui Docker socket ou credenciais do banco.
