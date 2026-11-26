"""Tradução de predicados de estado (estruturados, nunca SQL livre) para SELECT parametrizado."""
from __future__ import annotations

from typing import Any

from sqlalchemy import MetaData, Table, and_, exists, select
from sqlalchemy.engine import Engine

from massa.contratos import Predicado

LIMITE_PADRAO = 50


def _tabela(meta: MetaData, eng: Engine, nome: str) -> Table:
    if nome in meta.tables:
        return meta.tables[nome]
    return Table(nome, meta, autoload_with=eng)


def montar_select(eng: Engine, pred: Predicado, chave_valor: Any = None, excluir: list[Any] | None = None,
                  limite: int = LIMITE_PADRAO):
    meta = MetaData()
    t = _tabela(meta, eng, pred.tabela)
    cond = [t.c[k] == v for k, v in pred.filtros.items()]
    for lista, positivo in ((pred.existe, True), (pred.nao_existe, False)):
        for f in lista:
            r = _tabela(meta, eng, f.tabela)
            sub = exists().where(r.c[f.chave_remota] == t.c[f.chave_local],
                                 *[r.c[k] == v for k, v in f.filtros.items()])
            cond.append(sub if positivo else ~sub)
    if chave_valor is not None:
        cond.append(t.c[pred.chave] == chave_valor)
    if excluir:
        cond.append(t.c[pred.chave].not_in(excluir))
    return select(t).where(and_(*cond)).order_by(t.c[pred.chave]).limit(min(limite, 500))


def atributos_relacionados(eng: Engine, pred: Predicado, chave_valor: Any) -> dict[str, Any]:
    """Busca atributos declarados em `trazer` nas tabelas relacionadas (ex.: contrato vigente da garantia)."""
    meta = MetaData()
    out: dict[str, Any] = {}
    for f in pred.existe:
        if not f.trazer:
            continue
        r = _tabela(meta, eng, f.tabela)
        cond = [r.c[f.chave_remota] == chave_valor, *[r.c[k] == v for k, v in f.filtros.items()]]
        with eng.connect() as c:
            row = c.execute(select(r).where(and_(*cond)).limit(1)).mappings().first()
        if row:
            out.update({attr: row[col] for attr, col in f.trazer.items()})
    return out


def satisfaz(eng: Engine, pred: Predicado | None, chave_valor: Any) -> bool:
    if pred is None:
        return False
    with eng.connect() as c:
        return c.execute(montar_select(eng, pred, chave_valor=chave_valor, limite=1)).first() is not None
