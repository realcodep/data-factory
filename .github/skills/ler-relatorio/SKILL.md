---
name: ler-relatorio
description: Como apresentar ao usuário o relatório de um plano de massa — resultados, massa entregue, decisões, alertas de oráculo e sugestões.
---

# Ler e apresentar o relatório

Apresente nesta ordem, de forma curta:

1. **Resumo:** cenários ok, divergências, bloqueados, falhas; quanto da massa veio de garimpo e quanto foi provisionada.
2. **Divergências primeiro:** para cada uma, o que era esperado, o que aconteceu, e a **origem** da expectativa.
   Divergência com expectativa de origem funcional é **possível defeito** do sistema — destaque.
3. **Massa entregue:** registros por cenário e até quando ficam reservados.
4. **Decisões:** quantas por degrau da escada; liste as de `premissa` e `humano` (são as que alguém pode querer contestar).
5. **Alertas:** cenários com oráculo não independente (expectativa só do código).
6. **Pendências abertas** e propostas de catálogo, se houver.
7. **Sugestões** de cenários complementares (nunca executados sem pedido).

Nunca exiba documentos completos: o servidor já devolve CPF/CNPJ mascarados; mantenha assim.
