---
name: investigar-lacuna
description: Como tratar lacunas do catálogo de massa (estado, regra ou receita inexistente) por meio do subagente investigador, sem alterar o catálogo publicado.
---

# Investigar lacuna de catálogo

1. Confirme que é lacuna: `consultar_catalogo` não traz o estado, a regra ou a receita, e nenhum sinônimo do
   `vocabulario` corresponde ao termo do cenário.
2. Acione o subagente `investigador-catalogo` com: o termo exato do cenário, a entidade, e o que se espera
   (ex.: "estado: garantia com avaliação vencida").
3. O cenário afetado segue como **entrega parcial** (`registrar_decisao(..., degrau="parcial")`); o resto da suíte continua.
4. No relatório, aponte a proposta criada em `catalogo/propostas/` para revisão humana.
5. Depois de aprovada e publicada (novo build do catálogo), o cenário pode ser reexecutado.
