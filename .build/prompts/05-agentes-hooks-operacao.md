# Etapa 5 de 5 — Camada agêntica (QA Lead, investigador, skills, hooks) e operação

Antes de tudo, leia e siga `.build/prompts/00-protocolo.md`. Depois leia `.build/ESTADO.md` e `.build/DECISOES.md`.
Confirme que as etapas 1 a 4 estão concluídas; se não estiverem, termine-as primeiro.

## Objetivo

Criar a única camada com IA da arquitetura — o **agente QA Lead** e o **subagente investigador** — com custom instructions,
skills e hooks; colocar em operação o **pool com canários**, o **cenário executável** no pipeline e as **métricas**;
e validar tudo de ponta a ponta com uma suíte de aceitação.

Regra de ouro desta camada: **o agente só interpreta e decide**. Planejar, simular, executar e verificar é do motor (via MCP).

## Itens da etapa

### 5.1 Custom instructions (`.github/copilot-instructions.md`)
Curtas e estáveis (o detalhe fica nas skills):
- só homologação ou demo; dados sempre sintéticos; nunca dados reais no cenário ou na saída;
- toda massa passa pelo servidor MCP `massa`; nunca SQL, nunca chamadas diretas a APIs;
- usar apenas termos do vocabulário do catálogo; termo desconhecido é pendência, não invenção;
- toda expectativa de resultado declara origem (funcional, técnica, premissa);
- seguir a escada de autonomia e perguntar só quando impossível.

### 5.2 Agente QA Lead (`.github/agents/qa-lead.agent.md`)
Ferramentas: somente o servidor MCP `massa` e leitura do repositório. Fluxo obrigatório:
1. Receber a suíte (estruturada ou texto livre, um ou vários cenários).
2. Interpretar cada cenário em `EspecificacaoCenario`, usando **somente** o vocabulário (`vocabulario`).
   Separar pré-condições (com uso compartilhável/consumível) de dados de entrada.
3. `planejar_suite` → `simular_plano` → `pendencias`.
4. Resolver as pendências que restaram após o resolvedor determinístico, subindo a escada a partir do degrau 4:
   - **premissa reversível** (mais provável, baixo risco, fácil de desfazer; registrar);
   - **cobrir as duas leituras** quando barato (gerar as duas variações);
   - **entrega parcial** (seguir com o resto e marcar o ramo bloqueado);
   - **perguntar ao humano** somente se: a ambiguidade muda o resultado esperado e não dá para cobrir as duas leituras;
     falta informação inexistente em qualquer fonte; conflito sem evidência de desempate que afeta o resultado;
     ou a ação é irreversível/fora da política.
   Perguntas: todas juntas, no início, cada uma com opções, recomendação e o que acontece sem resposta.
   Sem resposta no prazo e opção reversível → aplicar a recomendação e marcar no relatório.
5. Registrar cada decisão (`registrar_decisao`) com degrau, justificativa, evidências, confiança e reversibilidade.
6. Se necessário, `solicitar_aprovacao` (uma vez). Depois `executar_plano` e acompanhar com `status_plano` sem intervir,
   exceto para novas pendências.
7. Entregar `relatorio`: massa, evidências, decisões (com degrau), alertas de **oráculo não independente**,
   cenários complementares **sugeridos** (nunca executados por conta própria).
Limites explícitos: nunca contorna o Guardião; nunca publica receita ou regra no catálogo; nunca amplia o escopo da suíte.

### 5.3 Subagente investigador (`.github/agents/investigador-catalogo.agent.md`)
Acionado pelo QA Lead quando a pendência é **lacuna de catálogo** (estado, regra ou receita inexistente).
Ferramentas: leitura do repositório e `consultar_catalogo`. Saída: **proposta** em `catalogo/propostas/` com evidências
(arquivo e linha). Nunca altera o catálogo publicado; a proposta exige revisão humana.

### 5.4 Skills (`.github/skills/<nome>/SKILL.md`)
Genéricas (reutilizáveis por qualquer cluster; nada específico do Garantias dentro delas):
- `interpretar-cenario`: do texto à especificação, com exemplos de Gherkin, planilha e texto livre.
- `resolver-pendencias`: a escada a partir do degrau 4, com exemplos de quando perguntar e quando não.
- `operar-motor-massa`: ordem de uso das ferramentas MCP, leitura de status e retomada.
- `investigar-lacuna`: como propor estado, regra ou receita com evidência.
- `ler-relatorio`: como apresentar o relatório ao usuário.
O específico do cluster fica em `config/` e `catalogo/`.

### 5.5 Hooks (`.github/hooks/massa.json` + `.github/hooks/scripts/`)
**Importante**: os hooks podem bloquear o próprio agente de construção. Crie-os **inativos**: cada script só age se
`MASSA_HOOKS=on` estiver definido (ou existir `config/hooks.ativos`). Teste os scripts por testes unitários, não ativando-os nesta sessão.
- `sessionStart`: confirma ambiente permitido, verifica época, injeta contexto (cluster, versão do catálogo) e avisa se há plano a retomar.
- `userPromptSubmitted`: detecta e substitui dados reais no cenário (CPF/CNPJ válidos que não sejam da fábrica, números de contrato, nomes).
- `preToolUse`: **isolamento** — nega ferramentas de terminal, escrita em arquivos fora de `saida/` e `catalogo/propostas/`,
  e qualquer acesso a banco ou API que não seja pelo servidor MCP `massa`. Falha fechada.
- `postToolUse`: auditoria das chamadas ao MCP (o mascaramento já é feito no servidor).
- `subagentStop`: valida que a saída do investigador é uma proposta com evidências.
- `sessionEnd` e `errorOccurred`: garantir checkpoint do plano em andamento e registrar o erro.

### 5.6 Pool e canários (`massa/operacao/`)
- `massa pool reabastecer`: provisiona antecipadamente os estados de `config/pool.yaml`, priorizando os que mais
  aparecem como garimpo vazio (projeção sobre os eventos).
- `massa canarios`: executa cada receita aprovada de ponta a ponta no ambiente; receita que falha é marcada como
  `quebrada` no catálogo (o planejador passa a evitá-la) e gera alerta.
- Ambos idempotentes e respeitando o Guardião.

### 5.7 Cenário executável e pipeline
- O relatório gera, por cenário, um **cenário executável** em `saida/cenarios/<id>/` (especificação + modelo de plano + roteiro).
  Reexecutar (`massa rodar saida/cenarios/<id>`) garimpa ou provisiona massa nova — nunca reutiliza IDs antigos.
- Workflow de exemplo em `.github/workflows/`: validar e montar catálogo em PR; testes; canários e reabastecimento do pool agendados.
  Tudo apontando para o ambiente demo.

### 5.8 Métricas (`massa relatorio metricas`)
Projeções sobre o registro de eventos: perguntas ao humano por cenário; cenários concluídos sem intervenção;
proporção garimpo/pool vs provisionamento; receitas quebradas detectadas por canário; expectativas sem fonte funcional;
decisões por degrau da escada.

### 5.9 Validação ponta a ponta
Crie `tests/aceitacao/suite_imobiliario.yaml` com 8 cenários fictícios:
5 estruturados (uma por operação), 1 em texto livre, 1 ambíguo resolvível por "cobrir as duas leituras",
1 que **exige** pergunta (expectativa central sem fonte funcional).
- Em CI: rode a suíte com um **QA Lead simulado** (stub determinístico que aplica as decisões esperadas) — tudo deve passar,
  e o cenário que exige pergunta deve gerar exatamente uma pergunta.
- Depois, **execute você mesmo** a suíte atuando como o QA Lead que acabou de definir, usando as ferramentas do motor
  (via MCP se o servidor estiver disponível para você; senão, pela CLI equivalente). Registre em `.build/RELATORIO-FINAL.md`
  quantas perguntas seriam feitas e quais decisões tomou.

## Critérios de saída
- [ ] Arquivos de instructions, 2 agentes, 5 skills e hooks criados; scripts de hooks com testes unitários; hooks inativos por padrão.
- [ ] Pool reabastecido e canários executados na demo; quebrar uma receita de propósito é detectado pelo canário.
- [ ] Cenário executável roda de novo e gera massa nova.
- [ ] Suíte de aceitação passa em CI com o QA Lead simulado, com exatamente uma pergunta.
- [ ] Execução manual da suíte registrada no relatório final.
- [ ] `README.md` final: como rodar, como ativar hooks, como conectar a um ambiente real
      (adaptadores desligados por padrão + checklist de segurança antes de ligar: usuário de banco com permissão mínima,
      rede sem acesso a produção, credenciais em cofre, política revisada).
- [ ] `.build/RELATORIO-FINAL.md` escrito e commit `etapa 5: concluída`.

Esta é a última etapa: ao concluir, encerre a execução com um resumo curto apontando para `.build/RELATORIO-FINAL.md`.
