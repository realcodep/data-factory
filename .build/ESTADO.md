# Estado da construção

**Etapa atual:** 5 — Agentes, hooks e operação

## Etapa 1 — Fundação: CONCLUÍDA
- [x] 1.1 Estrutura do projeto, pyproject, Makefile
- [x] 1.2 Contratos de dados (pydantic) com testes
- [x] 1.3 Registro de eventos somente-acréscimo + projeções (checkpoint, massa, precedentes, auditoria)
- [x] 1.4 Ambiente demo: banco, API (5 operações + contratos), propagação assíncrona, telas, fontes fictícios
- [x] docs/arquitetura.md com princípios e diagrama Mermaid

## Etapa 2 — Catálogo: CONCLUÍDA
- [x] 2.1 Extratores: copybook, Java, banco, OpenAPI, Domain Pack (fontes com arquivo:linha)
- [x] 2.2 Consolidação: técnica = mais restritiva; funcional × técnica = conflito registrado (catalogo/conflitos.yaml)
- [x] 2.3 Dicionário de estados (crédito + garantias) com predicados estruturados e sinônimos
- [x] 2.4 Receitas e grafo de estados validado (estados `somente_garimpo` permitidos)
- [x] 2.5 Interfaces (APIs + telas)
- [x] 2.6 Federação: garantias consome credito:contrato.ativo; dependência declarada em clusters.yaml
- [x] 2.7 Build versionado (hash + commit), vocabulário fechado, diff e detecção de defasagem

## Etapa 3 — Motor de massa: CONCLUÍDA
- [x] 3.1 Regras via catálogo; motor recusa catálogo desatualizado (Contexto.__post_init__)
- [x] 3.2 Gerador determinístico (semente + chave), CPF/CNPJ sintéticos, interseção de domínio em conflito
- [x] 3.3 Garimpo somente-leitura + reservas com prazo (consumível exclusivo, compartilhável múltiplo)
- [x] 3.4 Provisionador por receitas: menor custo, dependências, idempotência, recusa valor inválido
- [x] 3.5 Montador: payload (negativo viola exatamente a variação), roteiro Playwright, pacote de massa
- [x] 3.6 Executor com classificação de falhas e nova tentativa; verificador com espera de propagação
- [x] 3.7 Época do ambiente invalida reservas após recarga

## Etapa 4 — Planejamento, Guardião e MCP: CONCLUÍDA
- [x] 4.1 Planejador de suíte (compartilhável única, consumível por cenário, ordenação, grupos paralelizáveis)
- [x] 4.2 Fases F0–F7 geradas só quando necessárias (F3 esvaziada se garimpo cobre tudo)
- [x] 4.3 Plano a seco: só leituras; levanta pendências (termos, conflitos, oráculo, caminhos, política)
- [x] 4.4 Resolvedor determinístico: fato, convenção (config/convencoes.yaml), precedente
- [x] 4.5 Guardião: política única, avaliação do plano, aprovação única, falha fechada, mascaramento
- [x] 4.6 Condutor: checkpoint por passo, classificação de falhas, retomada (inclusive queda no meio de receita)
- [x] 4.7 Servidor MCP (SDK 2.x, compatível com 1.x) com 15 ferramentas, sem SQL livre

## Bloqueios
(nenhum)

## Próximos passos
Etapa 5: instructions, QA Lead, investigador, skills, hooks, pool/canários, cenário executável, métricas, aceitação.
