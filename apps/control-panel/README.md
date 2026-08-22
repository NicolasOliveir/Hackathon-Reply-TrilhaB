# control-panel

Painel React/TypeScript do MVP. Cria uma execução pela API central, acompanha o
event log por SSE e retoma a timeline usando o último `sequence` recebido.

## Desenvolvimento

Como o lockfile pertence a este workspace, execute os comandos dentro do
diretório com `--workspaces=false`:

```bash
cd apps/control-panel
npm ci --workspaces=false
npm run dev --workspaces=false
```

Verificações:

```bash
npm test --workspaces=false
npm run typecheck --workspaces=false
npm run build --workspaces=false
```

## Endereço da API e acesso mobile

Sem configuração, o painel reutiliza o hostname aberto no navegador e troca a
porta para `8000`. Assim, se o celular abrir `http://192.168.1.20:5173`, as
requisições seguem para `http://192.168.1.20:8000`, e não para o `localhost` do
telefone.

Defina `VITE_CONTROL_API_URL` quando a API estiver em outro host ou atrás de um
proxy:

```bash
VITE_CONTROL_API_URL=https://api.exemplo.local npm run dev --workspaces=false
```

O backend aceita origens locais por padrão no MVP. `CONTROL_PANEL_ORIGINS` pode
restringir a lista no formato `https://painel-a,https://painel-b`.

## Retomada do stream

O cliente usa `fetch` em vez de `EventSource` para controlar o header
`Last-Event-ID`. O maior `sequence` aceito vira o cursor da próxima conexão;
eventos com sequência já exibida são ignorados. Falhas de transporte usam
backoff limitado a cinco segundos e preservam a timeline visível.
