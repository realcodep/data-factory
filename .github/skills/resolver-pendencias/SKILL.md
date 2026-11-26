---
name: resolver-pendencias
description: Decidir pendências do plano de massa com a escada de autonomia, perguntando ao humano somente quando for impossível decidir.
---

# Resolver pendências

O motor já resolveu sozinho os degraus 1 a 3 (fato, convenção, precedente). O que chega até você precisa de julgamento.
Suba a escada e pare no primeiro degrau que resolve:

| Degrau | Use quando | Registro |
|---|---|---|
| 4. `premissa` | Há uma leitura mais provável, de baixo risco e fácil de desfazer | `registrar_decisao(..., degrau="premissa")` |
| 5. `duas_leituras` | Cobrir as opções é barato (gerar as duas variações) | `registrar_interpretacao` / duas especificações |
| 6. `parcial` | Não dá para decidir agora, mas o resto da suíte pode seguir | `registrar_decisao(..., degrau="parcial")` |
| 7. `humano` | Impossível seguir sem resposta (ver abaixo) | `registrar_perguntas` e, depois, `registrar_decisao(..., degrau="humano")` |

## Pergunte ao humano somente se

- a ambiguidade **muda o resultado esperado** e não dá para cobrir as duas leituras;
- falta informação que **não existe** em nenhuma fonte (regra de negócio nova, não documentada);
- **conflito** entre código e normativo sem evidência de desempate, afetando o resultado;
- a ação é **irreversível** ou fora da política.

## Não pergunte quando

- o catálogo tem a resposta (consulte antes com `consultar_catalogo`);
- a dúvida é só sobre um valor válido qualquer (o motor escolhe);
- dá para gerar as duas variações;
- a dúvida afeta só um cenário e os outros podem seguir (entrega parcial).

## Como perguntar

Todas as perguntas juntas, uma mensagem só. Para cada uma: contexto em uma frase, opções, **recomendação** e o que
acontece sem resposta. Exemplo:

> **CT-08 — bloqueio com motivo FRA.** O código aceita FRA; o normativo NG-IMO-01 §5.1 só prevê JUD e ADM.
> Opções: (a) seguir o normativo — esperar rejeição; (b) seguir o código — esperar aceite.
> **Recomendo (a)**: se o sistema aceitar, o relatório aponta possível defeito. Sem resposta até o fim do dia, aplico (a).

Ao receber a resposta, registre a decisão com `degrau="humano"`. Se a resposta muda o resultado esperado, use
`escolha={"verificacao": {...}, "fonte": "<fato>", "descricao": "...", "substituir": true}`.
