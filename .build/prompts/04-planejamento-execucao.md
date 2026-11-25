# Etapa 4 de 5 — Planejamento da suíte, plano a seco, condutor de fases, Guardião e servidor MCP

Antes de tudo, leia e siga `.build/prompts/00-protocolo.md`. Depois leia `.build/ESTADO.md` e `.build/DECISOES.md`.
Confirme que as etapas 1 a 3 estão concluídas; se não estiverem, termine-as primeiro.

## Objetivo

Transformar as operações do motor num processo **autônomo e retomável**:
planejar a suíte inteira, simular o plano sem escrever nada, resolver dúvidas antes da execução,
pedir no máximo uma aprovação, executar fase a fase com checkpoint e expor tudo via servidor MCP
com a política de segurança aplicada no servidor.

## Itens da etapa

### 4.1 Planejador de suíte (`massa/planejamento/planejador.py`)
- Entrada: `Suite` (lista de especificações já interpretadas). Saída: `Plano` com fases e passos.
- Para cada pré-condição: estratégia `garimpar → pool → provisionar` (a mais barata disponível).
- **Otimizações de suíte**:
  - pré-condições iguais e `compartilhavel` são atendidas uma única vez e reutilizadas por vários cenários;
  - `consumivel` gera uma instância por cenário;
  - ordena: cenários de leitura antes dos destrutivos;
  - marca ramos independentes como paralelizáveis.
- Montar o plano é busca determinística no grafo de receitas: mesma suíte + mesmo catálogo → mesmo plano.

### 4.2 Fases do plano
Gere as fases abaixo **apenas quando necessárias** (um cenário atendido só por garimpo, em modo `somente_massa`,
não precisa das fases F3, F5 e F6):

| Fase | Objetivo | Critério de saída |
|---|---|---|
| F0 Entendimento | Especificações válidas contra o vocabulário do catálogo | Todos os termos resolvidos |
| F1 Estratégia | Estratégia e dependências de cada pré-condição | Cada pré-condição com caminho |
| F2 Garimpo e reserva | Reservar o que já existe | Reservas ativas, estado reconferido |
| F3 Provisionamento | Receitas na ordem das dependências (subpasso por entidade) | Estados-alvo verificados |
| F4 Dados de entrada | Variações + payload ou roteiro | Payload/roteiro validados contra o contrato |
| F5 Execução | API ou tela | Resposta e evidência registradas |
| F6 Verificação | Resultados esperados, com espera de propagação | Confirmado ou divergência documentada |
| F7 Entrega | Relatório, reservas, cenário executável | Pacote gerado |

Cada fase declara: entradas, saídas, critério de saída, nível de risco, política de nova tentativa e compensação.

### 4.3 Plano a seco (`massa/planejamento/simulacao.py`)
- Executa o plano **somente com leituras**: garimpa sem reservar, confere caminhos de receitas, valida payloads,
  consulta o Guardião sobre cada ação prevista.
- Produz a lista completa de **pendências de decisão** antes de qualquer escrita:
  conflitos de regra, termos ambíguos, expectativas sem fonte funcional, receitas não aprovadas, ações que exigem aprovação.

### 4.4 Resolvedor de decisões determinístico (`massa/planejamento/decisoes.py`)
Resolve sozinho, sem LLM, os três primeiros degraus da escada:
1. **Fato**: o catálogo ou o banco responde (ex.: domínio com valor único).
2. **Convenção**: regras do cluster em `config/convencoes.yaml` (ex.: pessoa física por padrão, quantidade 1).
3. **Precedente**: decisão igual já tomada e não contestada (projeção de precedentes do registro de eventos;
   só vira precedente após N aplicações sem contestação, configurável).
O que sobrar vira **pendência para o QA Lead** (etapa 5), em formato estruturado: dúvida, opções, evidências,
impacto no resultado esperado, custo de cobrir todas as opções, reversibilidade.
Toda decisão gera evento `decisao_tomada` com o degrau usado.

### 4.5 Guardião — política como código (`massa/guardiao/`)
- Política única em `config/politica.yaml`: ambientes permitidos (nunca produção), tabelas e endpoints permitidos,
  receitas aprovadas, limites de volume, campos a mascarar, ações que exigem aprovação.
- Avalia **o plano inteiro** (no plano a seco) e cada **ação** em tempo de execução:
  em execução, só passa o que foi aprovado no plano; qualquer desvio é negado.
- **Aprovação única**: se o plano exigir aprovação, gera um pedido consolidado; aprovado, o plano roda de ponta a ponta.
- **Falha fechada**: erro ou tempo esgotado no Guardião = ação negada.
- Mascaramento de dados sensíveis em tudo o que sai do motor para o agente.

### 4.6 Condutor de fases (`massa/planejamento/condutor.py`)
- Máquina de estados determinística: para cada fase → executar → validar critério de saída → gravar checkpoint
  (eventos `fase_iniciada`/`fase_concluida`) → avançar automaticamente.
- Falhas: `transitoria` (nova tentativa), `dado` (volta à F2), `caminho` e `politica` (gera pendência para o QA Lead
  sem parar os ramos independentes).
- **Retomada**: `retomar(plano_id)` reconstrói o estado pela projeção de eventos, revalida reservas, estados e época,
  refaz só o que deixou de valer e continua.
- **Replanejamento parcial**: nova versão do plano invalida apenas as fases dependentes do que mudou.

### 4.7 Servidor MCP (`massa/mcp_server/`)
Exponha o motor via SDK oficial `mcp` (transporte stdio e HTTP). Ferramentas mínimas:
`vocabulario`, `validar_especificacao`, `planejar_suite`, `simular_plano`, `pendencias`, `registrar_decisao`,
`solicitar_aprovacao`, `aprovar_plano`, `executar_plano`, `status_plano`, `retomar_plano`, `relatorio`,
`liberar_reservas`, `consultar_catalogo`.
- Todas as ferramentas passam pelo Guardião **dentro do servidor**.
- Credenciais e conexões ficam no servidor; nenhuma ferramenta devolve credencial ou SQL bruto.
- Não exponha ferramenta de SQL livre nem de escrita direta no banco.

## Critérios de saída
- [ ] Suíte de 6 cenários fictícios com pré-condições repetidas: o plano provisiona cada pré-condição compartilhável uma única vez.
- [ ] Plano a seco não grava nada (prova: contagem de registros e eventos de escrita inalterada) e lista todas as pendências.
- [ ] Resolvedor resolve fato, convenção e precedente sem LLM; o restante vira pendência estruturada.
- [ ] Guardião nega ação fora do plano aprovado, nega produção e falha fechado em erro simulado.
- [ ] Interromper a execução no meio da F3 e chamar `retomar_plano` conclui sem duplicar registros.
- [ ] Servidor MCP sobe e responde às ferramentas em teste de integração com um cliente MCP de teste.
- [ ] `.build/ESTADO.md` atualizado e commit `etapa 4: concluída`.

Ao concluir, siga o encadeamento do protocolo: abra `.build/prompts/05-agentes-hooks-operacao.md` e execute.
