"""Verificação dos resultados esperados, respeitando o tempo de propagação de cada estado."""
from __future__ import annotations

from typing import Any

from massa.contratos import EspecificacaoCenario
from massa.motor.contexto import Contexto
from massa.motor.garimpo import reconferir
from massa.motor.provisionador import aguardar_estado


def verificar(ctx: Contexto, spec: EspecificacaoCenario, resposta: dict | None, papeis: dict[str, dict],
              plano_id: str | None, espera: bool = True) -> dict[str, Any]:
    itens = []
    for esp in spec.resultado_esperado:
        v = esp.verificacao
        ok, obtido = False, None
        if "http_status" in v:
            obtido = (resposta or {}).get("status")
            ok = obtido == v["http_status"]
        elif "estado" in v:
            chave = papeis[v.get("papel", "alvo")]["chave"]
            ok = aguardar_estado(ctx, v["estado"], chave, espera=espera)
            obtido = "atingido" if ok else "não atingido"
        elif "estado_mantido" in v:
            chave = papeis[v.get("papel", "alvo")]["chave"]
            ok = reconferir(ctx, v["estado_mantido"], chave)
            obtido = "mantido" if ok else "alterado"
        item = {"descricao": esp.descricao, "verificacao": v, "ok": ok, "obtido": obtido,
                "origem": esp.origem, "fonte": esp.fonte}
        itens.append(item)
    resultado = {"cenario": spec.id, "ok": all(i["ok"] for i in itens), "itens": itens,
                 "oraculo_nao_independente": "oraculo_nao_independente" in spec.avisos}
    ctx.eventos.registrar("verificacao_concluida", resultado, plano_id, chave=f"{plano_id}:{spec.id}:verificacao")
    return resultado
