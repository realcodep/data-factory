# Fábrica de Massa de Testes — Cluster Garantias

Gera massa de testes a partir de **cenários estruturados ou em texto livre**, usando **o banco de dados e o código-fonte**,
e entrega a massa pronta, o **payload preenchido** (e executado via API) ou o **teste direto na tela** (Playwright).

> Tudo neste repositório roda contra um **ambiente demo fictício** (banco SQLite, API e telas de garantia imobiliária).
> Nenhum dado, código ou regra real. Integrações com ambientes reais ficam desligadas — veja
> [Conectar a um ambiente real](#conectar-a-um-ambiente-real).

## Como funciona

| Camada | Usa IA? | Papel |
|---|---|---|
| Agente **QA Lead** (`.github/agents/qa-lead.agent.md`) | Sim | Interpreta cenários com vocabulário fechado e decide ambiguidades (escada de autonomia) |
| Subagente **investigador** | Sim | Propõe estados, regras ou receitas que faltam no catálogo, com evidências, para revisão humana |
| **Catálogo** (`catalogo/`) | Não | Regras de campo com fonte, dicionário de estados, receitas, interfaces; montado no build, federado por cluster |
| **Motor** — servidor MCP `massa` | Não | Planeja a suíte, simula (plano a seco), resolve fato/convenção/precedente, executa por fases com checkpoint |
| **Guardião** (`config/politica.yaml`) | Não | Política única aplicada dentro do servidor; aprovação única por plano; falha fechada; mascaramento |
| **Hooks** (`.github/hooks/`) | Não | Isolam o agente (só MCP), sanitizam dados reais no prompt, auditam, preparam a retomada |

Detalhes e diagrama: [`docs/arquitetura.md`](docs/arquitetura.md).

## Começar

```bash
pip install -e ".[dev]"
python -m demo.banco --reset                 # banco demo (recria = nova "época" do ambiente)
python -m massa.cli catalogo build           # monta o catálogo (regras, estados, receitas, vocabulário)
python -m pytest                             # 65 testes, incluindo a suíte de aceitação
```

Subir a API e as telas demo (necessário para executar planos pela CLI ou pelo MCP):

```bash
python -m uvicorn demo.api:app --port 8765
```

## Usar com um agente (Copilot, Cline, Claude Code)

1. O servidor MCP já está configurado em `.vscode/mcp.json` (VS Code/Copilot) e `.mcp.json` (Claude Code).
   No Cline, adicione o mesmo comando: `python -m massa.mcp_server`.
2. Selecione o agente **qa-lead** e envie a suíte, por exemplo:
   > Gere massa e teste via API: (1) bloquear garantia associada a contrato ativo por motivo judicial;
   > (2) incluir garantia com valor abaixo do mínimo deve ser rejeitada.
3. O agente interpreta, planeja, simula, decide, pede aprovação só se a política exigir, executa e entrega o relatório.

## Usar pela CLI

```bash
python -m massa.cli plano planejar tests/aceitacao/minha_suite.yaml   # devolve plano_id
python -m massa.cli plano simular PL-xxxx                             # plano a seco + pendências
python -m massa.cli plano decidir PL-xxxx --pendencia PD-01 --degrau premissa --escolha '"seguir_normativo"' --justificativa "..."
python -m massa.cli plano aprovar PL-xxxx --por "nome"
python -m massa.cli plano executar PL-xxxx                            # ou: retomar
python -m massa.cli plano relatorio PL-xxxx
python -m massa.cli rodar saida/cenarios/CT-03                        # reexecuta um cenário (massa nova)
python -m massa.cli canarios                                          # testa todas as receitas
python -m massa.cli pool reabastecer                                  # pré-aquece estados frequentes
python -m massa.cli metricas
```

Saídas em `saida/planos/<plano>/` (pacote de massa, roteiros de tela, evidências, relatório) e
`saida/cenarios/<cenário>/` (cenário executável).

## Ativar os hooks

Os hooks vêm **inativos** para não bloquear quem desenvolve a fábrica. Para ativar no uso do agente:

```bash
export MASSA_HOOKS=on        # ou: touch config/hooks.ativos
```

Com eles ativos, o agente só consegue usar o servidor MCP `massa`, ler o repositório e escrever em `saida/`
e `catalogo/propostas/`. Terminal, SQL e chamadas diretas a APIs são negados.

## Conectar a um ambiente real

Os adaptadores reais estão desligados (`adaptadores_reais: false` em `config/ambiente.yaml`). Antes de apontar para
uma homologação real, cumpra **todos** os itens:

- [ ] Usuário de banco com **permissão mínima**: leitura nas tabelas do domínio; nenhuma escrita direta (a massa é
      criada pelas APIs/transações oficiais).
- [ ] A rede de onde o motor roda **não alcança produção**.
- [ ] Credenciais em **cofre**, injetadas por variável de ambiente (`MASSA_BANCO_URL`, `MASSA_API_BASE`); nunca no repositório.
- [ ] `config/politica.yaml` revisado pelo time: endpoints permitidos, limites, campos a mascarar, o que exige aprovação.
- [ ] Catálogo montado a partir dos fontes reais (copybooks, DTOs, schema, OpenAPI, Domain Packs) e conflitos revisados.
- [ ] Tabela `sentinela` (ou equivalente) definida para detectar recarga do ambiente.
- [ ] Hooks ativos (`MASSA_HOOKS=on`) nas máquinas dos usuários do agente.
- [ ] Canários rodando antes de liberar o uso.

## Estrutura

```
massa/            motor: contratos, eventos, catálogo, motor, planejamento, guardião, servidor MCP, operação, CLI
catalogo/         catálogo federado (credito/, garantias/), sinônimos, conflitos gerados, propostas
config/           ambiente, política, convenções, pool
demo/             ambiente fictício: banco, API, telas e fontes (copybook, DTOs, Domain Pack)
.github/          instructions, agentes, skills, hooks, workflow
tests/            testes por etapa + aceitação (tests/aceitacao/)
.build/           prompts de construção, estado, decisões e relatório final
```
