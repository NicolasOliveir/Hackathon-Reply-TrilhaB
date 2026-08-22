# QA Worker

Worker independente que recebe apenas a story congelada e a entrega do Dev,
usa o gateway de modelo para criar um plano estruturado e materializa testes
reais em `/tests`. O worker nunca executa os testes nem declara aceite; essa
autoridade pertence ao runner determinístico.

O MVP roda localmente com `WORKSPACE_DIR` apontando para a entrega do Dev e
`TESTS_DIR` para um diretório gravável separado. Não depende de Docker. Os
comandos são executados sem shell por um executor allowlisted, com timeout,
exit code e stdout/stderr persistidos como evidência.
