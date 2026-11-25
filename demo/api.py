"""API e telas do ambiente demo (fictício) — garantia imobiliária.

Simula:
- regras de negócio das 5 operações (inclusão, associação, bloqueio, desassociação, exclusão);
- a API de contratos do cluster Crédito;
- propagação assíncrona: o bloqueio é aceito (202) e só aparece no banco após um atraso.
"""
from __future__ import annotations

import os
import re
import threading
from datetime import date
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, insert, select, update

from demo.banco import contrato, garantia, garantia_contrato

DATA_BASE = date(2026, 1, 1)


def _dv(base: list[int], pesos: list[int]) -> int:
    s = sum(d * p for d, p in zip(base, pesos)) % 11
    return 0 if s < 2 else 11 - s


def documento_valido(doc: str) -> bool:
    if not doc.isdigit():
        return False
    d = [int(x) for x in doc]
    if len(d) == 11 and len(set(d)) > 1:
        return d[9] == _dv(d[:9], list(range(10, 1, -1))) and d[10] == _dv(d[:10], list(range(11, 1, -1)))
    if len(d) == 14:
        return d[12] == _dv(d[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) and \
            d[13] == _dv(d[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return False


class NovoContrato(BaseModel):
    numero: str = Field(min_length=1, max_length=20)
    cpf_cnpj_cliente: str = Field(max_length=14)
    valor: Decimal = Field(gt=0, max_digits=15, decimal_places=2)

    @field_validator("cpf_cnpj_cliente")
    @classmethod
    def _doc(cls, v):
        if not documento_valido(v):
            raise ValueError("documento inválido")
        return v


class NovaGarantia(BaseModel):
    matricula_imovel: str = Field(max_length=20)
    valor_avaliacao: Decimal = Field(ge=Decimal("1000.00"), max_digits=15, decimal_places=2)
    data_avaliacao: date
    cpf_cnpj_proprietario: str = Field(max_length=14)

    @field_validator("matricula_imovel")
    @classmethod
    def _mat(cls, v):
        if not re.fullmatch(r"\d{6,10}", v):
            raise ValueError("matrícula deve ter de 6 a 10 dígitos")
        return v

    @field_validator("data_avaliacao")
    @classmethod
    def _data(cls, v):
        if v > DATA_BASE:
            raise ValueError("data de avaliação no futuro")
        return v

    @field_validator("cpf_cnpj_proprietario")
    @classmethod
    def _doc(cls, v):
        if not documento_valido(v):
            raise ValueError("documento inválido")
        return v


class Associacao(BaseModel):
    id_contrato: int


class Bloqueio(BaseModel):
    motivo_bloqueio: str

    @field_validator("motivo_bloqueio")
    @classmethod
    def _motivo(cls, v):
        # Implementação técnica aceita FRA; o normativo funcional (Domain Pack) só prevê JUD e ADM.
        if v not in ("JUD", "ADM", "FRA"):
            raise ValueError("motivo inválido")
        return v


def criar_app(db_url: str | None = None, propagacao_s: float | None = None) -> FastAPI:
    db_url = db_url or os.environ.get("DEMO_DB_URL", "sqlite:///demo/demo.db")
    atraso = float(os.environ.get("DEMO_PROPAGACAO_S", "2")) if propagacao_s is None else propagacao_s
    eng = create_engine(db_url, connect_args={"check_same_thread": False})
    app = FastAPI(title="API demo — Garantias (fictícia)", version="1.0.0")
    app.state.engine = eng
    app.state.propagacao_s = atraso
    app.state.timers = []

    def _garantia(c, gid: int):
        g = c.execute(select(garantia).where(garantia.c.id == gid)).mappings().first()
        if not g:
            raise HTTPException(404, "garantia não encontrada")
        return g

    def _vinculo_vigente(c, gid: int):
        return c.execute(select(garantia_contrato).where(garantia_contrato.c.id_garantia == gid,
                                                         garantia_contrato.c.situacao == "V")).mappings().first()

    @app.post("/v1/contratos", status_code=201, tags=["credito"])
    def criar_contrato(body: NovoContrato):
        with eng.begin() as c:
            r = c.execute(insert(contrato).values(**body.model_dump(), situacao="A"))
            return {"id_contrato": r.inserted_primary_key[0]}

    @app.get("/v1/contratos/{cid}", tags=["credito"])
    def ler_contrato(cid: int):
        with eng.connect() as c:
            r = c.execute(select(contrato).where(contrato.c.id == cid)).mappings().first()
            if not r:
                raise HTTPException(404, "contrato não encontrado")
            return dict(r)

    @app.post("/v1/garantias/imobiliarias", status_code=201, tags=["garantias"])
    def incluir(body: NovaGarantia):
        with eng.begin() as c:
            r = c.execute(insert(garantia).values(**body.model_dump(), tipo="IMO", situacao="A"))
            return {"id_garantia": r.inserted_primary_key[0]}

    @app.get("/v1/garantias/{gid}", tags=["garantias"])
    def ler(gid: int):
        with eng.connect() as c:
            g = dict(_garantia(c, gid))
            v = _vinculo_vigente(c, gid)
            g["id_contrato_vigente"] = v["id_contrato"] if v else None
            return g

    @app.post("/v1/garantias/{gid}/associacoes", status_code=201, tags=["garantias"])
    def associar(gid: int, body: Associacao):
        with eng.begin() as c:
            g = _garantia(c, gid)
            if g["situacao"] != "A":
                raise HTTPException(409, "garantia não está ativa")
            ct = c.execute(select(contrato).where(contrato.c.id == body.id_contrato)).mappings().first()
            if not ct or ct["situacao"] != "A":
                raise HTTPException(409, "contrato inexistente ou não ativo")
            if _vinculo_vigente(c, gid):
                raise HTTPException(409, "garantia já associada")
            r = c.execute(insert(garantia_contrato).values(id_garantia=gid, id_contrato=body.id_contrato, situacao="V"))
            return {"id_vinculo": r.inserted_primary_key[0]}

    @app.post("/v1/garantias/{gid}/bloqueios", status_code=202, tags=["garantias"])
    def bloquear(gid: int, body: Bloqueio):
        with eng.connect() as c:
            g = _garantia(c, gid)
            if g["situacao"] == "B":
                raise HTTPException(409, "garantia já bloqueada")
            if g["situacao"] != "A" or not _vinculo_vigente(c, gid):
                raise HTTPException(409, "só é possível bloquear garantia ativa e associada")

        def efetivar():
            with eng.begin() as c2:
                c2.execute(update(garantia).where(garantia.c.id == gid)
                           .values(situacao="B", motivo_bloqueio=body.motivo_bloqueio))

        if atraso <= 0:
            efetivar()
        else:
            t = threading.Timer(atraso, efetivar)
            t.daemon = True
            app.state.timers.append(t)
            t.start()
        return {"id_garantia": gid, "status": "bloqueio_em_processamento"}

    @app.post("/v1/garantias/{gid}/desassociacoes", status_code=200, tags=["garantias"])
    def desassociar(gid: int, body: Associacao):
        with eng.begin() as c:
            g = _garantia(c, gid)
            v = _vinculo_vigente(c, gid)
            if not v or v["id_contrato"] != body.id_contrato:
                raise HTTPException(409, "não há vínculo vigente com este contrato")
            if g["situacao"] == "B":
                raise HTTPException(409, "garantia bloqueada não pode ser desassociada")
            c.execute(update(garantia_contrato).where(garantia_contrato.c.id == v["id"]).values(situacao="D"))
            return {"id_garantia": gid, "status": "desassociada"}

    @app.delete("/v1/garantias/{gid}", status_code=200, tags=["garantias"])
    def excluir(gid: int):
        with eng.begin() as c:
            g = _garantia(c, gid)
            if g["situacao"] != "A":
                raise HTTPException(409, "só é possível excluir garantia ativa")
            if _vinculo_vigente(c, gid):
                raise HTTPException(409, "garantia associada não pode ser excluída")
            c.execute(update(garantia).where(garantia.c.id == gid).values(situacao="E"))
            return {"id_garantia": gid, "status": "excluida"}

    # ───────── telas ─────────
    def _tela(titulo: str, campos: list[tuple[str, str]], acao_js: str) -> str:
        inputs = "\n".join(
            f'<label>{rotulo}<input id="campo-{cid}" name="{cid}" /></label>' for cid, rotulo in campos)
        return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{titulo}</title>
<style>body{{font-family:sans-serif;max-width:560px;margin:40px auto}}label{{display:block;margin:10px 0}}
input{{display:block;width:100%;padding:6px}}#resultado{{margin-top:16px;padding:10px;border:1px solid #ccc}}</style>
</head><body><h1>{titulo}</h1>{inputs}
<button id="btn-confirmar">Confirmar</button><div id="resultado" data-status=""></div>
<script>
document.getElementById('btn-confirmar').onclick = async () => {{
  const v = id => document.getElementById('campo-' + id).value;
  {acao_js}
  const el = document.getElementById('resultado');
  el.dataset.status = r.status; el.textContent = r.status + ' ' + await r.text();
}};
</script></body></html>"""

    @app.get("/telas/garantias/inclusao", response_class=HTMLResponse, include_in_schema=False)
    def tela_inclusao():
        return _tela("Inclusão de garantia imobiliária",
                     [("matricula_imovel", "Matrícula"), ("valor_avaliacao", "Valor de avaliação"),
                      ("data_avaliacao", "Data de avaliação"), ("cpf_cnpj_proprietario", "CPF/CNPJ do proprietário")],
                     "const r = await fetch('/v1/garantias/imobiliarias', {method:'POST', headers:{'Content-Type':'application/json'},"
                     " body: JSON.stringify({matricula_imovel:v('matricula_imovel'), valor_avaliacao:v('valor_avaliacao'),"
                     " data_avaliacao:v('data_avaliacao'), cpf_cnpj_proprietario:v('cpf_cnpj_proprietario')})});")

    @app.get("/telas/garantias/bloqueio", response_class=HTMLResponse, include_in_schema=False)
    def tela_bloqueio():
        return _tela("Bloqueio de garantia",
                     [("id_garantia", "Garantia"), ("motivo_bloqueio", "Motivo")],
                     "const r = await fetch('/v1/garantias/' + v('id_garantia') + '/bloqueios', {method:'POST',"
                     " headers:{'Content-Type':'application/json'}, body: JSON.stringify({motivo_bloqueio:v('motivo_bloqueio')})});")

    return app


app = criar_app()
