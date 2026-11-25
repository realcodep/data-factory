"""Banco do ambiente demo — garantia imobiliária na comercialização (dados 100% fictícios)."""
from __future__ import annotations

import argparse
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import (CheckConstraint, Column, Date, ForeignKey, Integer, MetaData, Numeric, String, Table,
                        create_engine, insert)

URL_PADRAO = "sqlite:///demo/demo.db"
meta = MetaData()

contrato = Table(
    "contrato", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("numero", String(20), nullable=False, unique=True),
    Column("cpf_cnpj_cliente", String(14), nullable=False),
    Column("situacao", String(1), nullable=False),
    Column("valor", Numeric(15, 2), nullable=False),
    CheckConstraint("situacao IN ('A','L','C')", name="ck_contrato_situacao"),
)

garantia = Table(
    "garantia", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tipo", String(3), nullable=False),
    Column("matricula_imovel", String(20), nullable=False),
    Column("valor_avaliacao", Numeric(15, 2), nullable=False),
    Column("cpf_cnpj_proprietario", String(14), nullable=False),
    Column("data_avaliacao", Date, nullable=False),
    Column("situacao", String(1), nullable=False),
    Column("motivo_bloqueio", String(3), nullable=True),
    CheckConstraint("tipo IN ('IMO')", name="ck_garantia_tipo"),
    CheckConstraint("situacao IN ('A','B','E')", name="ck_garantia_situacao"),
    CheckConstraint("motivo_bloqueio IN ('JUD','ADM','FRA')", name="ck_garantia_motivo"),
)

garantia_contrato = Table(
    "garantia_contrato", meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("id_garantia", Integer, ForeignKey("garantia.id"), nullable=False),
    Column("id_contrato", Integer, ForeignKey("contrato.id"), nullable=False),
    Column("situacao", String(1), nullable=False),
    CheckConstraint("situacao IN ('V','D')", name="ck_vinculo_situacao"),
)

sentinela = Table(
    "sentinela", meta,
    Column("id", Integer, primary_key=True),
    Column("assinatura", String(40), nullable=False),
)


def resetar(url: str = URL_PADRAO) -> str:
    """Recria o banco com dados preexistentes fictícios. Muda a 'época' do ambiente."""
    if url.startswith("sqlite:///"):
        caminho = Path(url.replace("sqlite:///", ""))
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if caminho.exists():
            caminho.unlink()
    eng = create_engine(url)
    meta.create_all(eng)
    assinatura = uuid.uuid4().hex
    with eng.begin() as c:
        c.execute(insert(sentinela), [{"id": 1, "assinatura": assinatura}])
        c.execute(insert(contrato), [
            {"numero": "CT-DEMO-0001", "cpf_cnpj_cliente": "52998224725", "situacao": "A", "valor": 250000},
            {"numero": "CT-DEMO-0002", "cpf_cnpj_cliente": "11144477735", "situacao": "A", "valor": 480000},
            {"numero": "CT-DEMO-0003", "cpf_cnpj_cliente": "11222333000181", "situacao": "A", "valor": 1200000},
            {"numero": "CT-DEMO-0004", "cpf_cnpj_cliente": "39053344705", "situacao": "L", "valor": 90000},
        ])
        c.execute(insert(garantia), [
            {"tipo": "IMO", "matricula_imovel": "1234567", "valor_avaliacao": 350000, "cpf_cnpj_proprietario": "52998224725",
             "data_avaliacao": date(2025, 6, 10), "situacao": "A", "motivo_bloqueio": None},
            {"tipo": "IMO", "matricula_imovel": "7654321", "valor_avaliacao": 610000, "cpf_cnpj_proprietario": "11144477735",
             "data_avaliacao": date(2025, 8, 2), "situacao": "B", "motivo_bloqueio": "JUD"},
            {"tipo": "IMO", "matricula_imovel": "5550001", "valor_avaliacao": 180000, "cpf_cnpj_proprietario": "39053344705",
             "data_avaliacao": date(2025, 3, 15), "situacao": "A", "motivo_bloqueio": None},
        ])
        c.execute(insert(garantia_contrato), [
            {"id_garantia": 1, "id_contrato": 1, "situacao": "V"},
            {"id_garantia": 2, "id_contrato": 2, "situacao": "V"},
        ])
    eng.dispose()
    return assinatura


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--url", default=URL_PADRAO)
    a = ap.parse_args()
    if a.reset:
        print("época:", resetar(a.url))
