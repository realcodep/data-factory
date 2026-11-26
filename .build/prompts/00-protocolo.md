# Protocolo de execução autônoma (vale para todas as etapas)

Você está construindo, em 5 etapas, a **Fábrica de Massa de Testes** do Cluster Garantias:
uma arquitetura em que um agente QA Lead interpreta cenários de teste e um motor determinístico
(servidor MCP) garimpa, reserva, provisiona e executa a massa — via payload de API ou direto na tela.

As etapas estão em `.build/prompts/`:

| Etapa | Arquivo |
|---|---|
| 1 | `01-fundacao.md` |
| 2 | `02-catalogo.md` |
| 3 | `03-motor-de-massa.md` |
| 4 | `04-planejamento-execucao.md` |
| 5 | `05-agentes-hooks-operacao.md` |

## 1. Estado e checkpoint

- O estado da construção fica em `.build/ESTADO.md`. **Leia-o antes de qualquer ação.**
- Se ele não existir, crie-o com: etapa atual, itens da etapa (checklist), itens concluídos, bloqueios, próximos passos.
- Trabalhe em **incrementos pequenos**. Depois de cada incremento:
  1. rode os testes da área afetada;
  2. atualize `.build/ESTADO.md` (marque o item, registre o próximo passo);
  3. faça um commit local com mensagem `etapa N: <item>` (nunca faça push).
- Se a sessão for interrompida, quem retomar deve conseguir continuar **apenas lendo `.build/ESTADO.md`**.
  Escreva o checkpoint pensando nisso.
- Se o estado indicar que a etapa atual já foi concluída, vá direto para a próxima.

## 2. Decisões sem perguntar (escada de autonomia)

Diante de qualquer dúvida, suba esta escada e pare no primeiro degrau que resolve:

1. **Fato:** a resposta está no repositório, nesta especificação ou na etapa anterior.
2. **Convenção:** existe padrão definido aqui (stack, nomes, estrutura). Siga-o.
3. **Precedente:** a mesma dúvida já foi decidida em `.build/DECISOES.md`. Aplique igual.
4. **Premissa reversível:** escolha a opção mais simples e fácil de mudar, registre em `.build/DECISOES.md`
   (dúvida, opção escolhida, alternativas, por quê) e siga.
5. **Cobrir as duas leituras:** se for barato, implemente as duas opções atrás de configuração.
6. **Entrega parcial:** se algo realmente travar, marque como bloqueio em `ESTADO.md`, deixe um `TODO(bloqueio)`
   no código e continue com tudo o que não depende dele.
7. **Perguntar ao usuário:** só se for impossível seguir sem resposta, ou seja:
   - ação irreversível fora do repositório;
   - credencial ou acesso a sistema real;
   - contradição na especificação que muda o comportamento e não pode ser coberta pelas duas leituras.
   Se perguntar, faça todas as perguntas juntas, com recomendação, e continue o que não depende delas.

**Não** peça confirmação para criar arquivos, instalar dependências do projeto, rodar testes ou fazer commits locais.

## 3. Regras invioláveis

- **Nunca** conecte a sistemas reais (homologação, produção, mainframe, bancos corporativos) durante a construção.
  Tudo roda contra o **ambiente demo fictício** criado na etapa 1. Integrações reais ficam como adaptadores
  configuráveis, desligados por padrão.
- **Nunca** use dados reais. Nomes, documentos, contratos e valores são sintéticos.
- **Nunca** grave segredos no repositório. Configuração sensível vem de variáveis de ambiente.

## 4. Stack padrão (convenção)

- Python 3.11+, `pydantic` v2 (esquemas), `sqlalchemy` 2 (banco), `fastapi` + `uvicorn` (API e telas demo),
  `mcp` (SDK oficial do Model Context Protocol para Python), `playwright` (execução em tela), `pytest`, `pyyaml`.
- Gerenciador: `uv` se disponível; senão `pip` com `venv`.
- Pacote principal: `massa/`. Testes em `tests/`. Configuração em `config/`. Catálogo em `catalogo/`.
- Camada agêntica no formato GitHub Copilot: `.github/copilot-instructions.md`, `.github/agents/*.agent.md`,
  `.github/skills/<nome>/SKILL.md`, `.github/hooks/*.json`. Mantenha os textos neutros o bastante para
  funcionar também no Cline e no Claude Code.

## 5. Gate de saída de cada etapa

Cada etapa termina com uma lista de **critérios de saída**. Só considere a etapa concluída quando todos passarem.
- Se o mesmo critério falhar 3 vezes seguidas, registre como bloqueio e siga para o que não depende dele.
- Ao concluir: rode **todos** os testes do projeto (não só os da etapa), atualize `ESTADO.md` marcando a etapa como concluída,
  faça o commit `etapa N: concluída`.

## 6. Encadeamento

Ao concluir uma etapa, **sem esperar o usuário**, leia o próximo arquivo de `.build/prompts/` e execute-o.
Ao concluir a etapa 5, escreva o resumo final em `.build/RELATORIO-FINAL.md` (o que foi construído,
decisões tomadas, bloqueios, como rodar) e só então encerre.

Se a ferramenta exigir que o usuário confirme a continuação (limite de passos por turno), o usuário digitará
apenas `continue`. Nesse caso, releia `.build/ESTADO.md` e prossiga de onde parou.
