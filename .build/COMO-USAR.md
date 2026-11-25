# Como usar os prompts da Fábrica de Massa de Testes

1. Copie a pasta `.build/` para a raiz de um repositório **novo e vazio** (de preferência fora da rede corporativa
   na primeira rodada, já que tudo roda contra um ambiente demo fictício).
2. Abra o repositório no GitHub Copilot (modo agente), Cline ou Claude Code.
3. Cole **apenas** o comando abaixo:

```
Leia .build/prompts/00-protocolo.md e depois execute .build/prompts/01-fundacao.md.
Siga o protocolo de execução autônoma até concluir a etapa 5, encadeando as etapas sem esperar por mim.
```

4. Se a ferramenta parar pedindo confirmação para continuar (limite de passos por turno), digite apenas:

```
continue
```

O agente relê `.build/ESTADO.md` e retoma de onde parou.

## O que acompanhar

- `.build/ESTADO.md` — etapa atual, checklist e próximos passos (é o checkpoint).
- `.build/DECISOES.md` — decisões que o agente tomou sozinho (revise ao final).
- `.build/RELATORIO-FINAL.md` — resumo ao término da etapa 5.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `00-protocolo.md` | Regras comuns: checkpoint, escada de autonomia, regras invioláveis, stack, encadeamento |
| `01-fundacao.md` | Contratos de dados, registro de eventos, ambiente demo fictício |
| `02-catalogo.md` | Extratores, regras com fonte, estados, receitas, interfaces, federação, versão |
| `03-motor-de-massa.md` | Gerador, garimpo e reserva, provisionador, montador, executor, verificador, época |
| `04-planejamento-execucao.md` | Planejador de suíte, plano a seco, resolvedor de decisões, Guardião, condutor, servidor MCP |
| `05-agentes-hooks-operacao.md` | QA Lead, investigador, skills, hooks, pool e canários, pipeline, métricas, aceitação |
