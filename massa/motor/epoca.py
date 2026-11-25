"""Época do ambiente: detecta recarga (refresh) da base de homologação.

Quando a assinatura dos registros-sentinela muda, tudo o que aponta para IDs da época anterior
(reservas, pool) deixa de valer. Decisões por conceito (precedentes) continuam valendo.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import MetaData, Table, select

from massa.motor.contexto import Contexto


def assinatura(ctx: Contexto, tabela: str = "sentinela") -> str:
    t = Table(tabela, MetaData(), autoload_with=ctx.engine)
    with ctx.engine.connect() as c:
        linhas = c.execute(select(t).order_by(*t.primary_key.columns)).all()
    return hashlib.sha256(repr(linhas).encode()).hexdigest()[:16]


def verificar_epoca(ctx: Contexto) -> bool:
    """Devolve True se o ambiente foi recarregado desde a última verificação (e invalida reservas)."""
    atual = assinatura(ctx)
    anteriores = ctx.eventos.listar(tipos=["epoca_detectada"])
    if anteriores and anteriores[-1]["dados"]["assinatura"] == atual:
        return False
    mudou = bool(anteriores)
    invalidadas = ctx.reservas.invalidar_todas("ambiente_recarregado") if mudou else 0
    ctx.eventos.registrar("epoca_detectada", {"assinatura": atual, "recarga": mudou, "reservas_invalidadas": invalidadas})
    return mudou
