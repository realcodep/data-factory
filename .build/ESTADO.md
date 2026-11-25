# Estado da construção

**Etapa atual:** 3 — Motor de massa

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

## Bloqueios
(nenhum)

## Próximos passos
Etapa 3: regras, gerador, garimpo/reserva, provisionador, montador, executor, verificador, época.
