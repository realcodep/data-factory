---
name: interpretar-cenario
description: Converter cenários de teste (Gherkin, planilha ou texto livre) em EspecificacaoCenario usando apenas o vocabulário fechado do catálogo de massa.
---

# Interpretar cenário

## Passos

1. Chame `vocabulario` e trabalhe só com o que existe lá (entidades, estados e sinônimos, operações, campos, variações).
2. Para cada cenário, identifique:
   - **operação** e **entidade**;
   - **tipo**: `positivo`, `negativo` (viola campo **ou** regra de estado) ou `limite`;
   - **pré-condições**: estados que precisam existir antes. Se o cenário não disser, o motor infere pela operação.
     Declare explicitamente quando o estado é diferente do usual (ex.: "desassociar garantia **bloqueada**").
   - **entradas**: valores pedidos explicitamente (ex.: motivo `FRA`);
   - **variações**: campo + regra (`abaixo_minimo`, `fora_dominio`, `vazio`, ...);
   - **resultado esperado**: `aceito`, `rejeitado`, `http_status`, `estado` ou `estado_mantido`, com `origem` e `fonte`.
3. Valide com `validar_especificacao` antes de planejar.

## Exemplos

**Gherkin**
```gherkin
Dado uma garantia imobiliária associada a contrato ativo
Quando eu bloquear com motivo judicial
Então a garantia fica bloqueada
```
→ `operacao: bloqueio`, `tipo: positivo`, `entradas: {motivo_bloqueio: JUD}`,
`resultado_esperado: [{verificacao: {estado: garantias:garantia_imobiliaria.bloqueada, papel: alvo}, origem: funcional, fonte: FN-GAR-003}]`

**Planilha** (colunas: operação | condição | dado | esperado) — uma linha vira uma especificação; a coluna "esperado" vira
`resultado_esperado` e você procura a fonte funcional com `consultar_catalogo`.

**Texto livre**: "incluir garantia com valor de avaliação abaixo do mínimo deve ser rejeitado"
→ `operacao: inclusao`, `tipo: negativo`, `variacoes: [{campo: valor_avaliacao, regra: abaixo_minimo}]`,
`resultado_esperado: [{verificacao: {rejeitado: true}, origem: funcional, fonte: FN-GAR-005}]`.

## Duas leituras

"Bloquear com motivo inválido" pode ser motivo fora do domínio **ou** motivo vazio. As duas são baratas de cobrir:
gere duas especificações (`...a` e `...b`) e registre com `registrar_interpretacao` (degrau `duas_leituras`).
