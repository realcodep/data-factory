"""Garimpo: encontrar no banco registros que já estejam no estado pedido (somente leitura)."""
from __future__ import annotations

from typing import Any

from massa.catalogo.predicados import atributos_relacionados, montar_select, satisfaz
from massa.motor.contexto import Contexto, FalhaCaminho


def registro_id(tabela: str, chave: Any) -> str:
    return f"{tabela}:{chave}"


def garimpar(ctx: Contexto, estado_id: str, quantidade: int = 1, uso: str = "compartilhavel",
             somente_marcados: bool = False, excluir: set[str] | None = None, telemetria: bool = True,
             plano_id: str | None = None) -> list[dict[str, Any]]:
    estado = ctx.catalogo.estados.get(estado_id)
    if estado is None:
        raise FalhaCaminho(f"estado desconhecido: {estado_id}")
    if estado.predicado is None:
        return []
    pred = estado.predicado
    ocupados = ctx.reservas.ocupados(uso) | (excluir or set())
    ocupadas_chaves = [r.split(":", 1)[1] for r in ocupados if r.startswith(pred.tabela + ":")]
    marcados = None
    if somente_marcados:
        marcados = {str(m["chave"]) for m in ctx.eventos.massa_criada() if m.get("tabela") == pred.tabela}
    with ctx.engine.connect() as c:
        linhas = c.execute(montar_select(ctx.engine, pred, excluir=[int(x) if x.isdigit() else x for x in ocupadas_chaves],
                                         limite=max(quantidade * 5, 10))).mappings().all()
    achados = []
    for ln in linhas:
        chave = ln[pred.chave]
        if marcados is not None and str(chave) not in marcados:
            continue
        achados.append({"registro": registro_id(pred.tabela, chave), "tabela": pred.tabela, "chave": chave,
                        "estado": estado_id, "atributos": {**{k: _json(v) for k, v in ln.items()},
                                                           **atributos_relacionados(ctx.engine, pred, chave)}})
        if len(achados) >= quantidade:
            break
    if not achados and telemetria:
        ctx.eventos.registrar("garimpo_vazio", {"estado": estado_id, "uso": uso}, plano_id)
    return achados


def reconferir(ctx: Contexto, estado_id: str, chave: Any) -> bool:
    return satisfaz(ctx.engine, ctx.catalogo.estados[estado_id].predicado, chave)


def _json(v: Any) -> Any:
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if v.__class__.__name__ == "Decimal":
        return float(v)
    return v
