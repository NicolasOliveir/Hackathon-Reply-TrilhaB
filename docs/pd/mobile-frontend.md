# Regras para Mobile e Frontend

Estas regras orientam decisões de interface. Quando a story ou o design system existente trouxer
uma regra mais específica, ela prevalece.

## Mobile-first

- Comece pelo menor viewport declarado na story. Na ausência de valor, use `320 px` como hipótese
  de verificação e registre-a no handoff, sem promovê-la a requisito do produto.
- Preserve a ação principal visível e evite rolagem horizontal.
- Use uma coluna para formulários em mobile; agrupe campos apenas quando a relação for evidente.
- Evite depender de hover, clique com botão direito ou gesto sem alternativa visível.
- Defina alvos de toque de pelo menos `44 x 44 px`, salvo restrição existente mais rigorosa.
- Considere teclado virtual, áreas seguras, orientação e conteúdo extenso quando afetarem o fluxo.
- Minimize digitação com padrões de entrada adequados, opções selecionáveis e preenchimento
  contextual, sem inventar valores do usuário.

## Layout responsivo

Para cada tela, descreva o comportamento em `mobile`, `tablet` e `desktop`; não forneça apenas uma
imagem escalada. Informe:

- ordem e agrupamento do conteúdo;
- elementos fixos, fluidos, ocultos ou movidos;
- comportamento de navegação e ação principal;
- quebra de tabelas, listas, gráficos e formulários;
- largura máxima e tratamento de conteúdo longo.

Ocultar informação obrigatória em um breakpoint não é adaptação responsiva válida.

## Estados obrigatórios quando aplicáveis

- inicial;
- carregando;
- vazio;
- preenchido;
- validação de campo;
- erro de operação;
- sucesso;
- indisponível ou somente leitura.

Para cada estado, descreva gatilho, conteúdo exibido, ação disponível e próximo estado. Mensagens
devem orientar recuperação e não depender apenas de cor ou ícone.

## Acessibilidade

- Todo controle possui nome acessível e label persistente quando coleta dados.
- A ordem de foco acompanha a ordem visual e todas as ações funcionam por teclado.
- O foco permanece visível e é movido deliberadamente após abertura de modal ou erro de envio.
- Texto e controles devem respeitar contraste adequado; registre tokens ou pares de cores usados.
- Ícones informativos possuem texto alternativo ou rótulo; ícones decorativos são ignorados por
  tecnologia assistiva.
- Mudanças assíncronas importantes devem ser anunciáveis sem retirar o contexto do usuário.
- Movimento não deve ser necessário para entender o conteúdo e deve respeitar redução de animação.

## Especificação visual mínima

O handoff deve usar unidades e tokens consistentes para:

- tipografia: família existente, tamanho, peso e altura de linha;
- espaçamento: escala reutilizável;
- cores: superfície, texto, borda, ação e estados semânticos;
- bordas, raio e elevação quando alterarem hierarquia ou interação;
- ícones: significado, tamanho e label acessível;
- componentes: variantes, propriedades e estados.

Se o repositório já possuir design system, referencie tokens e componentes pelo nome. Não crie um
sistema visual paralelo para uma única story.
