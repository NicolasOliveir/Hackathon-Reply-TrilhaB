# Regras de coordenação para agentes e desenvolvedores

Estas instruções valem para todo o repositório. O objetivo é permitir desenvolvimento paralelo
sem duas pessoas implementarem a mesma tarefa ou sobrescreverem trabalho alheio.

## Fonte de verdade

- A branch principal deste repositório é `main`. Quando alguém disser “master”, considere `main`.
- O quadro oficial de reserva é [TASKS.md](TASKS.md) na `origin/main`.
- Uma tarefa só pertence a alguém depois que a reserva com nome e branch foi commitada e aceita
  pelo remoto em `origin/main`.
- Conversa, plano local ou branch não publicada não reservam tarefa.

## Antes de começar qualquer tarefa

1. Identifique-se pelo nome usado pelo time. Não use apenas “Dev A”, “agente” ou “Codex”.
2. Termine, guarde em commit ou descarte de forma segura qualquer mudança local antes de trocar
   de branch. Nunca execute pull com mudanças não commitadas.
3. Sincronize a branch principal:

   ```bash
   git switch main
   git pull --ff-only origin main
   ```

4. Leia `TASKS.md` novamente no conteúdo atualizado de `main`.
5. Confirme que a tarefa está `LIVRE`, que suas dependências permitem início e que nenhuma tarefa
   ativa possui a mesma área exclusiva.
6. Edite somente a linha da tarefa escolhida:
   - `Status`: `EM_ANDAMENTO`;
   - `Responsável`: seu nome;
   - `Branch`: `task/<ID>-<slug>`;
   - `Início`: data e hora com fuso;
   - `Atualização`: resumo curto da reserva.
7. Faça e publique imediatamente o commit de reserva na `main`:

   ```bash
   git add TASKS.md
   git commit -m "chore(tasks): reserve <ID> for <nome>"
   git push origin main
   ```

8. Somente depois do push aceito crie a branch de implementação:

   ```bash
   git switch -c task/<ID>-<slug>
   git push -u origin task/<ID>-<slug>
   ```

Se o push da reserva for rejeitado, outra atualização chegou primeiro. Não use force push. Faça
fetch, releia `origin/main:TASKS.md` e preserve a reserva remota. Se outra pessoa reservou a mesma
tarefa, escolha uma tarefa diferente.

## Durante o desenvolvimento

- Trabalhe somente no escopo e nas áreas declaradas na tarefa.
- Não altere nome, status ou branch de uma tarefa pertencente a outra pessoa.
- Arquivos compartilhados fora da área exclusiva exigem aviso ao responsável da tarefa afetada e
  registro em `TASKS.md`.
- Use o ID da tarefa em todos os commits, por exemplo:

  ```text
  feat(I1-004): persist runs and events
  test(I1-004): cover duplicate idempotency key
  ```

- Faça commits pequenos após cada incremento verificável e publique a branch com frequência.
- Antes de iniciar uma nova parte, antes do handoff e sempre que `main` mudar, sincronize sem
  reescrever o trabalho remoto:

  ```bash
  git fetch origin
  git merge --no-edit origin/main
  git push
  ```

- Execute `git status` antes de commit e push. Não inclua arquivos não relacionados à tarefa.
- Não use `git reset --hard`, force push, rebase de branch compartilhada ou remoção de mudanças
  de outro desenvolvedor.
- Segredos, tokens, `.env` reais, credenciais de banco e chaves de modelo nunca entram em commit.

## Atualização de status

Atualizações do quadro são commits pequenos feitos em `main`, separados do código da feature:

- `EM_ANDAMENTO`: reserva publicada e desenvolvimento iniciado;
- `EM_REVISAO`: branch publicada, verificações executadas e pronta para revisão/merge;
- `BLOQUEADA`: impedimento concreto, dependência e próximo passo registrados;
- `CONCLUIDA`: código já integrado em `main`, verificações aprovadas e commit final informado;
- `LIVRE`: ninguém trabalhando; responsável e branch vazios.

Antes de mudar o status, sincronize `main` com `git pull --ff-only origin main`. Uma tarefa
`CONCLUIDA` deve informar o commit integrado; branch apenas publicada não significa conclusão.

Se precisar abandonar uma tarefa, não deixe a reserva esquecida. Publique na `main` a mudança
para `LIVRE`, ou `BLOQUEADA` quando existir trabalho reaproveitável e impedimento documentado.

## Revisão e integração

1. Sincronize a branch com `origin/main` e resolva conflitos preservando ambos os trabalhos.
2. Execute todos os critérios de aceite e comandos indicados na tarefa.
3. Faça push da branch e marque a tarefa como `EM_REVISAO` na `main`.
4. Use PR quando disponível. Quem revisa não deve ser a mesma pessoa que implementou.
5. Depois do merge, atualize a tarefa para `CONCLUIDA`, com commit, evidências e data.
6. Faça pull da `main` novamente antes de reservar outro item.

## Regra de parada

Pare e coordene com o time quando:

- a tarefa já estiver reservada;
- a área necessária pertencer a outra tarefa ativa;
- o contrato compartilhado precisar mudar;
- o pull revelar conflito de intenção, não apenas conflito textual;
- a implementação exigir ampliar o escopo do MVP.

Nunca “resolva” essas situações sobrescrevendo o quadro ou o código remoto.
