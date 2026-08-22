# Critérios de Aceitação

Os critérios de aceitação são o único contrato que o agente de QA tem. Ele avalia
cada critério exatamente uma vez, na ordem em que foi escrito, e precisa anexar
evidência concreta a cada veredito. Critério que ele não consegue observar trava a
validação e reprova a story por um defeito do backlog, não do código.

## Forma

Escreva cada critério como um único fato observável com resultado binário. Duas
formas funcionam; use a que for mais curta para o caso.

**Dado / Quando / Então** — para comportamento que depende de estado:

    Dada uma ocorrência com status ABERTA, quando o usuário muda o status para
    RESOLVIDA sem preencher a ação corretiva, então o formulário exibe o erro
    "Ação corretiva obrigatória" e o status permanece ABERTA.

**Afirmação direta** — para fatos estruturais ou de apresentação:

    O formulário de registro exibe os campos data, responsável, turno e
    equipamento, e nenhum deles aceita envio vazio.

## Regras

- Nomeie o campo, o valor, o estado ou a mensagem. Não "a validação funciona", mas
  qual validação, em qual campo, com qual mensagem.
- Uma afirmação por critério. Dois comportamentos unidos por "e também" viram dois
  critérios, porque o QA precisa julgar cada um como passou ou falhou por conta
  própria.
- Prefira o que aparece na tela ou no dado armazenado a chamadas internas de
  função.
- Declare o caso negativo quando ele muda a correção: entrada rejeitada, lista
  vazia, chave duplicada, campo obrigatório ausente.
- Não invente quantidade que o briefing não deu. Se ele diz "rápido", ou omita o
  critério, ou registre o alvo escolhido como suposição.
- Não cite componente, arquivo, rota ou biblioteca dentro de um critério. Descreva
  o que o usuário observa; o Developer escolhe como.

## Mantenha cada critério reproduzível ao pé da letra

O agente de QA precisa reproduzir cada critério **literalmente** no relatório, e o
orquestrador rejeita o relatório quando uma string não bate caractere por
caractere. Critério longo ou multilinha convida à paráfrase e transforma uma
validação boa em execução falhada.

- Mantenha o critério em uma frase, em uma linha.
- Evite aspas aninhadas além da única mensagem que está sendo afirmada.
- Evite marcador de lista, quebra de linha e espaço sobrando dentro da string.
- Se um critério não cabe em uma frase, ele está testando duas coisas — divida.

## Não verificáveis — reescreva estes

| Evite | Por que falha | Escreva assim |
|---|---|---|
| A interface é intuitiva | Sem resultado binário | Cada campo do formulário tem label associada e mensagem de erro visível ao lado |
| O sistema é responsivo | Sem alvo observável | Em 320 px de largura a tela de registro não apresenta rolagem horizontal |
| Os dados são persistidos corretamente | "Corretamente" esconde a regra | Após recarregar a página, a ocorrência criada continua na lista com os mesmos campos |
| O desempenho é adequado | Não testável sem alvo | Omita, ou registre o alvo como suposição |
| A rastreabilidade está completa | Isso é escopo, não critério | A consulta por código de lote retorna matéria-prima, fornecedor, equipamento, turno e operadores associados |
| O histórico é auditável | Sem campos declarados | Cada registro exibe data, responsável, turno e equipamento, e esses campos não podem ser editados após salvar |

## Padrões recorrentes

- **Campo obrigatório** — o campo, o gatilho, a mensagem exata e que a ação não se
  completa.
- **Chave única** — o que acontece na segunda tentativa com o mesmo valor.
- **Filtro ou busca** — a entrada, o subconjunto esperado e o caso de resultado
  vazio.
- **Persistência** — a ação, o recarregamento e o que precisa sobreviver a ele.
- **Evidência de auditoria** — quais campos são registrados e que não podem ser
  editados depois.
- **Indicador derivado** — as linhas de entrada e o número resultante.
- **Transição de estado** — o estado de origem, a condição, o estado de destino e o
  que bloqueia a transição.

## Ordenação

Escreva os critérios na ordem em que uma pessoa os exercitaria: criar, depois ler,
depois editar, depois borda. O QA reporta os vereditos nessa mesma ordem, então uma
sequência coerente torna o relatório de reprovação legível para o Developer.
