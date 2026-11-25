---
name: operar-motor-massa
description: Ordem correta de uso das ferramentas do servidor MCP `massa` — planejar, simular, decidir, aprovar, executar, acompanhar e retomar.
---

# Operar o motor de massa

```
vocabulario ─► validar_especificacao ─► planejar_suite ─► simular_plano
      ─► pendencias ─► (registrar_decisao | registrar_interpretacao | registrar_perguntas)
      ─► solicitar_aprovacao ─► [usuário confirma] ─► aprovar_plano
      ─► executar_plano ─► status_plano ─► relatorio
```

- `simular_plano` **não escreve nada**: pode ser chamado quantas vezes quiser.
- `executar_plano` grava checkpoint a cada passo. Se a sessão cair, `retomar_plano(plano_id)` continua de onde parou,
  sem duplicar massa.
- `status: aguardando_aprovacao` → peça a aprovação ao usuário (uma vez), nunca aprove por conta própria.
- Ação negada pelo Guardião aparece como falha de política no relatório: não tente outro caminho para contorná-la.
- Massa entregue fica **reservada** até o prazo. Se o usuário terminar antes, `liberar_reservas`.
- Modos: `somente_massa` (só reserva/cria), `payload` (monta o payload sem enviar), `api` (envia), `tela` (Playwright).
