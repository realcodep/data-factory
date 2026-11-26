# Etapa 1 de 5 — Fundação: contratos, registro de eventos e ambiente demo

Antes de tudo, leia e siga `.build/prompts/00-protocolo.md`. Depois leia `.build/ESTADO.md` (crie se não existir).

## Objetivo

Criar a base que todas as outras etapas usam: estrutura do projeto, os **contratos de dados** da arquitetura,
o **registro único de eventos** e um **ambiente demo fictício** do domínio de Garantias contra o qual tudo será testado.

## Princípios que guiam toda a arquitetura (registre-os em `docs/arquitetura.md`)

1. O modelo interpreta e decide **o que** testar; o motor determinístico decide **os valores** e **as ações**.
2. Conhecimento é montado antes (catálogo versionado), não descoberto a cada pedido.
3. Toda decisão é tomada antes de qualquer escrita (plano a seco); a execução roda sem interrupção.
4. Pré-condição (precisa existir e ser válida no banco) é diferente de dado de entrada (pode ser inválido, vive no payload).
5. Toda expectativa de resultado declara a origem: funcional, técnica ou premissa.
6. Um único registro de eventos, somente-acréscimo; checkpoint, auditoria e precedentes são projeções dele.
7. A política de segurança (Guardião) é aplicada no servidor, não depende do cliente.

## Itens da etapa

### 1.1 Estrutura do projeto
```
massa/            # pacote principal (motor)
  contratos/      # esquemas pydantic
  eventos/        # registro de eventos e projeções
  catalogo/       # (etapa 2)
  motor/          # (etapa 3)
  planejamento/   # (etapa 4)
  guardiao/       # (etapa 4)
  mcp_server/     # (etapa 4)
demo/             # ambiente fictício
catalogo/         # dados do catálogo em YAML (etapa 2)
config/
tests/
docs/
```
Inclua `pyproject.toml`, `Makefile` (ou `tasks.py`) com alvos `setup`, `test`, `demo-up`, `demo-reset`, e `README.md` inicial.

### 1.2 Contratos de dados (`massa/contratos/`, pydantic v2, com testes de validação)

- **EspecificacaoCenario**: `id`, `titulo`, `origem_texto` (entrada original), `operacao`
  (`inclusao|associacao|bloqueio|desassociacao|exclusao|consulta|alteracao`), `entidade`,
  `tipo` (`positivo|negativo|limite`), `precondicoes` (lista de `{entidade, estado, uso: compartilhavel|consumivel}`),
  `entradas` (valores explícitos), `variacoes` (lista de `{campo, regra}` com regras
  `valido|limite_inferior|limite_superior|abaixo_minimo|acima_maximo|vazio|tamanho_excedido|fora_dominio|formato_invalido`),
  `resultado_esperado` (lista de `{descricao, verificacao, origem: funcional|tecnica|premissa, fonte}`),
  `modo_execucao` (`somente_massa|payload|api|tela`), `seed`.
  Validações: cenário negativo/limite exige variação; resultado esperado só com origem `tecnica` gera
  aviso `oraculo_nao_independente`.
- **Suite**: lista de especificações + metadados (história, autor, cluster).
- **RegraCampo**, **Estado**, **Receita**, **Interface** (detalhados na etapa 2; aqui só os esquemas):
  - `RegraCampo`: campo, tipo, tamanho, decimais, obrigatório, mínimo, máximo, padrão, domínio, semântica, `fontes[]`
    (cada fonte: `origem: copybook|java|banco|openapi|domain_pack|funcional`, `referencia`, `trecho`).
  - `Estado`: `id` (ex.: `garantia_imobiliaria.bloqueada`), cluster dono, descrição de negócio, predicado técnico
    (tabela + filtros), tempo máximo de propagação, sinônimos de negócio.
  - `Receita`: `id`, estado de origem, estado de destino, passos (cada passo: tipo `api|transacao|job`, interface, mapeamento de campos),
    efeito (`cria|transforma|consome`), custo relativo, se foi aprovada.
  - `Interface`: APIs (método, caminho, contrato de request/response) e telas (rota, campos, seletores, botão de ação).
- **Plano**, **Fase**, **Passo**, **Decisao**, **Reserva** (esquemas usados nas etapas 3 e 4):
  - `Decisao`: dúvida, degrau da escada (`fato|convencao|precedente|premissa|duas_leituras|parcial|humano`),
    escolha, alternativas, justificativa, evidências, confiança, reversível.
  - `Reserva`: registro, estado, cenário, uso, expira_em.

### 1.3 Registro de eventos (`massa/eventos/`)
- Armazenamento somente-acréscimo em SQLite (tabela `eventos`: `seq`, `momento`, `plano_id`, `tipo`, `dados_json`, `chave_idempotencia`).
- Tipos mínimos: `plano_criado`, `decisao_tomada`, `fase_iniciada`, `fase_concluida`, `reserva_feita`, `reserva_liberada`,
  `registro_criado`, `chamada_executada`, `verificacao_concluida`, `falha_registrada`, `epoca_detectada`.
- `chave_idempotencia` única: gravar o mesmo evento duas vezes não duplica.
- **Projeções** (funções que reconstroem visões a partir dos eventos): estado do plano (checkpoint),
  massa criada, auditoria, precedentes (decisões não contestadas).
- Proibido `UPDATE`/`DELETE` na tabela de eventos (garanta com teste).

### 1.4 Ambiente demo fictício (`demo/`)
Simula o domínio de garantia imobiliária na comercialização. Tudo fictício.
- **Banco** (SQLite em `demo/demo.db`, script de criação e de reset):
  - `contrato` (pertence ao cluster Crédito): id, número, cpf_cnpj_cliente, situação (`A` ativo, `L` liquidado, `C` cancelado), valor.
  - `garantia`: id, tipo (`IMO`), matrícula do imóvel, valor_avaliação (decimal 15,2, mínimo 1.000,00),
    situação (`A` ativa, `B` bloqueada, `E` excluída), motivo_bloqueio (domínio `JUD|ADM|FRA`), data_avaliacao.
  - `garantia_contrato`: id_garantia, id_contrato, situação do vínculo (`V` vigente, `D` desassociado).
  - `sentinela`: registros cuja assinatura identifica a "época" do ambiente.
  - Constraints reais: NOT NULL, CHECK de domínio, FKs.
- **API demo** (FastAPI) com as 5 operações: incluir garantia, associar a contrato, bloquear, desassociar, excluir;
  além de criar contrato (simulando a API do cluster Crédito) e consultar.
  Regras de negócio: não bloquear garantia já bloqueada; não excluir garantia associada; valor abaixo do mínimo → 422; etc.
  **Simule propagação assíncrona**: o bloqueio só aparece no banco após um atraso configurável (padrão 2s).
- **Telas demo** (HTML simples servido pela mesma app) para inclusão e bloqueio, com IDs estáveis nos campos.
- **Código-fonte fictício** para os extratores da etapa 2: um copybook COBOL (`demo/fontes/CPGAR10.cpy`, com PIC e níveis 88),
  um DTO Java com Bean Validation (`demo/fontes/GarantiaImobiliariaRequest.java`), o OpenAPI gerado pela API demo
  e um Domain Pack fictício mínimo (`demo/fontes/domain_pack/` com fatos e evidências em JSON).
- `make demo-up` sobe API + banco; `make demo-reset` recria o banco (isso deve mudar a época do ambiente).

## Critérios de saída
- [ ] `make setup` e `make test` funcionam do zero.
- [ ] Contratos validam exemplos corretos e rejeitam incorretos (inclusive cenário negativo sem variação).
- [ ] Registro de eventos: idempotência e proibição de alteração cobertas por teste; projeção de checkpoint reconstrói um plano fictício.
- [ ] API demo executa as 5 operações e respeita as regras de negócio; propagação assíncrona observável em teste.
- [ ] `docs/arquitetura.md` com os princípios e um diagrama em Mermaid da arquitetura v3.
- [ ] `.build/ESTADO.md` atualizado e commit `etapa 1: concluída`.

Ao concluir, siga o encadeamento do protocolo: abra `.build/prompts/02-catalogo.md` e execute.
