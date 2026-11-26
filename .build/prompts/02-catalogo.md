# Etapa 2 de 5 — Catálogo de massa (build-time, federado e versionado)

Antes de tudo, leia e siga `.build/prompts/00-protocolo.md`. Depois leia `.build/ESTADO.md` e `.build/DECISOES.md`.
Confirme que a etapa 1 está concluída; se não estiver, termine-a primeiro.

## Objetivo

Construir o **catálogo de massa**: o conhecimento que o motor consulta na hora de gerar massa, montado
**antes** (no pipeline, por commit) a partir de código-fonte, schema do banco, contratos de API e Domain Packs.
Nenhum LLM é usado nesta etapa: tudo é extração e validação determinística.

O catálogo tem quatro partes:
1. **Regras de campo**: tipo, tamanho, obrigatoriedade, domínio, limites, sempre com fonte.
2. **Dicionário de estados**: traduz vocabulário de negócio ("contrato ativo", "garantia bloqueada") para predicado técnico.
3. **Receitas**: como levar uma entidade de um estado a outro, por quais interfaces.
4. **Interfaces**: APIs e telas, com mapeamento de campos.

## Itens da etapa

### 2.1 Extratores determinísticos (`massa/catalogo/extratores/`)
Cada extrator recebe um caminho e devolve `list[RegraCampo]` com `fontes` preenchidas (arquivo:linha ou tabela.coluna).
- **Copybook COBOL**: níveis, `PIC` (X, 9, S9, V, COMP-3, repetições `(n)`), `VALUE`, níveis 88 → domínio.
- **Java/Bean Validation**: `@NotNull`, `@NotBlank`, `@Size`, `@Pattern`, `@Min`, `@Max`, `@DecimalMin`, `@DecimalMax`,
  `@Digits`, `@Positive`, `@Past/@Future`, enums → domínio.
- **Schema do banco** (via SQLAlchemy inspect): tipos, tamanhos, NOT NULL, FKs, CHECK `IN (...)` → domínio.
- **OpenAPI**: `required`, `maxLength`, `minimum`, `maximum`, `pattern`, `enum`.
- **Domain Pack**: importa fatos e evidências existentes (formato do pack fictício em `demo/fontes/domain_pack/`).
  Fatos funcionais viram fontes com `origem: funcional` — são eles que permitem expectativas de resultado independentes do código.
- Normalização de nomes entre fontes (`VLR-AVALIACAO`, `valorAvaliacao`, `vlr_avaliacao`) com tabela de sinônimos
  configurável em `catalogo/sinonimos.yaml` além da normalização automática.

### 2.2 Consolidação de regras (`massa/catalogo/consolidacao.py`)
- Combina regras do mesmo campo vindas de fontes diferentes: **a mais restritiva vence**.
- **Conflito** (ex.: copybook permite 13 dígitos e banco 11; domínios disjuntos) não é resolvido sozinho:
  vira item em `catalogo/conflitos.yaml` com as duas evidências. O motor tratará conflitos como pendência de decisão.
- Toda regra consolidada mantém **todas** as fontes.

### 2.3 Dicionário de estados (`catalogo/estados/*.yaml`)
Escreva os estados do imobiliário para a demo, com predicado técnico, sinônimos e tempo máximo de propagação:
- Crédito: `contrato.ativo`, `contrato.liquidado`.
- Garantias: `garantia_imobiliaria.inexistente`, `.ativa_sem_vinculo`, `.associada`, `.bloqueada`, `.desassociada`, `.excluida`.
Cada estado declara o **cluster dono**. Valide que todo predicado é executável no banco demo.

### 2.4 Receitas (`catalogo/receitas/*.yaml`)
Para cada transição relevante, uma receita: origem → destino, passos via interface, mapeamento de campos,
efeito (`cria|transforma|consome`), custo relativo, `aprovada: true|false`.
Mínimo: criar contrato ativo (dono: Crédito), incluir garantia, associar, bloquear, desassociar, excluir.
Gere um **grafo de estados** a partir das receitas e valide: todo estado é alcançável a partir de `inexistente`;
nenhuma receita aponta para estado inexistente.

### 2.5 Interfaces (`catalogo/interfaces/*.yaml`)
- APIs: derivadas do OpenAPI da API demo + mapeamento campo de negócio → caminho no JSON.
- Telas: rota, campos (nome de negócio → seletor estável), botão de ação, indicador de sucesso/erro.

### 2.6 Federação entre clusters
- O catálogo é organizado por namespace de cluster (`credito/`, `garantias/`).
- Um cluster **consome** estados e receitas de outro por referência (ex.: Garantias usa `credito:contrato.ativo`),
  nunca copiando. Referência quebrada é erro de validação.
- Arquivo `catalogo/clusters.yaml` lista donos, versões e de quais clusters cada um depende.

### 2.7 Build, versão e detecção de defasagem
- CLI: `massa catalogo build` (gera `catalogo/dist/catalogo.json` com hash e commit de origem),
  `massa catalogo validar`, `massa catalogo diff <versao_a> <versao_b>`.
- **Detecção de defasagem**: se o hash das fontes mudou desde o último build, o catálogo é marcado como desatualizado
  e o motor (etapa 3) recusa gerar massa com ele até um novo build.
- Gere `catalogo/dist/vocabulario.json`: a lista fechada de entidades, estados (com sinônimos), operações e variações
  que o agente QA Lead poderá usar (etapa 5).

## Critérios de saída
- [ ] Cada extrator tem testes com os fontes fictícios da demo e preenche fontes com arquivo e linha.
- [ ] Consolidação: teste com campo de três fontes (mais restritiva vence) e teste de conflito registrado em vez de resolvido.
- [ ] Todos os predicados de estado executam no banco demo; grafo de estados validado.
- [ ] Federação: referência a `credito:contrato.ativo` funciona; referência quebrada falha na validação.
- [ ] `massa catalogo build` gera catálogo e vocabulário versionados; alterar um fonte marca o catálogo como desatualizado.
- [ ] `.build/ESTADO.md` atualizado e commit `etapa 2: concluída`.

Ao concluir, siga o encadeamento do protocolo: abra `.build/prompts/03-motor-de-massa.md` e execute.
