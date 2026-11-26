# Relatório final da construção — Fábrica de Massa de Testes

Construção executada seguindo `.build/prompts/00` a `05`, com checkpoint em `ESTADO.md`, decisões em `DECISOES.md`
e um commit por etapa. **65 testes passando** a partir de um ambiente limpo (banco recriado, catálogo remontado).

## O que foi construído

| Etapa | Entregue |
|---|---|
| 1. Fundação | Contratos (pydantic), registro único de eventos somente-acréscimo com projeções (checkpoint, massa, auditoria, precedentes), ambiente demo fictício (banco, API com 5 operações + contratos de Crédito, propagação assíncrona, telas, fontes COBOL/Java/Domain Pack) |
| 2. Catálogo | Extratores sem IA (copybook, Java, banco, OpenAPI, Domain Pack); consolidação (técnica: mais restritiva vence; funcional × técnica: **conflito registrado**); 9 estados, 6 receitas, interfaces de API e tela; federação Crédito → Garantias; build versionado com detecção de defasagem; vocabulário fechado |
| 3. Motor | Gerador determinístico (CPF/CNPJ sintéticos), garimpo somente-leitura, reservas com prazo (consumível/compartilhável), provisionamento por receitas idempotente, payload que viola **exatamente** a variação pedida, roteiro Playwright reexecutável, verificação com espera de propagação, detecção de recarga do ambiente |
| 4. Planejamento | Planejador de suíte (pré-condição compartilhável atendida uma vez), plano a seco sem escrita, resolvedor de fato/convenção/precedente sem IA, Guardião (política única, aprovação única, falha fechada, mascaramento), condutor por fases com retomada — inclusive após queda **no meio** de uma receita — e servidor MCP com 16 ferramentas, sem SQL livre |
| 5. Camada agêntica | Instructions, agente QA Lead, subagente investigador, 5 skills genéricas, hooks para 7 eventos (inativos por padrão), pool priorizado por demanda, canários que detectam receita quebrada e fazem o planejador evitá-la, cenário executável, workflow de CI, métricas |

## Validação ponta a ponta

**CI (QA Lead simulado):** suíte de 8 entradas → 9 especificações. Resultado: 8 ok, 1 divergência proposital (CT-08),
**exatamente 1 pergunta**.

**Rodada manual ao vivo** (eu no papel de QA Lead, API demo no ar com propagação de 2 s; evidência em
`.build/evidencias/rodada_manual.json`):

| Cenário | Resultado | HTTP |
|---|---|---|
| CT-01 inclusão válida | ok | 201 |
| CT-02 associação | ok | 201 |
| CT-03 bloqueio judicial | ok (esperou a propagação) | 202 |
| CT-04 desassociar bloqueada (negativo) | ok — rejeitado e estado mantido | 409 |
| CT-05 exclusão | ok — após aprovação única | 200 |
| CT-06 texto livre: valor abaixo do mínimo | ok — rejeitado | 422 |
| CT-07a motivo fora do domínio (duas leituras) | ok — rejeitado | 422 |
| CT-07b motivo vazio (duas leituras) | ok — rejeitado | 422 |
| CT-08 motivo FRA | **divergência** — o sistema aceita FRA, o normativo não prevê | 202 |

- **Perguntas ao humano:** 1 (CT-08), feita no início, com recomendação. Sem humano na rodada, apliquei a regra do
  prazo: recomendação reversível (seguir o normativo), registrada como premissa.
- **Decisões:** 1 por duas leituras (CT-07), 1 premissa (CT-08). Nenhuma decisão de fato/convenção foi necessária nesta suíte.
- **Massa:** 8 instâncias para 9 cenários (contrato ativo compartilhado); 6 vieram de garimpo, 2 foram provisionadas.
- **CT-08 é o resultado mais útil da rodada:** a fábrica apontou uma divergência entre código e normativo — exatamente
  o tipo de possível defeito que um oráculo tirado só do código esconderia.

## Decisões a revisar

Todas em `.build/DECISOES.md` (19). As que mais merecem um olhar humano:
- **#6** conflito funcional × técnico nunca é resolvido pelo build;
- **#8** valor válido de campo em conflito usa a interseção das fontes;
- **#16** o hook de prompt bloqueia e devolve a versão sanitizada (não reescreve);
- **#18** na rodada manual, a aprovação foi dada pelo agente de construção (só porque o ambiente é fictício).

## Limitações conhecidas

- Condutor executa em série; o plano já expõe os grupos paralelizáveis.
- Extratores cobrem os formatos da demo (copybook com PIC/88, Bean Validation, CHECK IN, OpenAPI). Programas COBOL
  (lógica de procedimento), JCL e Node.js ainda não têm extrator: entram via Domain Pack ou como novos extratores.
- O agente QA Lead real (LLM) não roda no CI; o CI usa o stub determinístico. A rodada manual cobre o fluxo com julgamento.
- Hooks foram testados como scripts; o comportamento exato de cada evento varia entre Copilot, Cline e Claude Code
  (os scripts emitem os dois formatos de saída mais comuns).

## Como rodar

Ver `README.md` (seções "Começar", "Usar com um agente" e "Conectar a um ambiente real").
