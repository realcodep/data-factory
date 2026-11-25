import random
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, func, select, text

from massa.contratos import EspecificacaoCenario, RegraCampo
from massa.motor import gerador
from massa.motor.contexto import FalhaCaminho
from massa.motor.epoca import verificar_epoca
from massa.motor.executor import chamar_api, executar_roteiro
from massa.motor.garimpo import garimpar
from massa.motor.montador import montar_payload, montar_roteiro_tela
from massa.motor.provisionador import provisionar
from massa.motor.verificador import verificar

ENT = "garantias:garantia_imobiliaria"
BLOQ = f"{ENT}.bloqueada"


def _conta(ctx, tabela):
    with ctx.engine.connect() as c:
        return c.execute(text(f"select count(*) from {tabela}")).scalar()


# ───── gerador ─────
def test_gerador_deterministico_e_documentos(ctx):
    regra = ctx.catalogo.regra(ENT, "valor_avaliacao")
    a = [gerador.gerar(regra, e, gerador.rng(7, "k"), ctx.data_base).valor for e in ("valido", "abaixo_minimo")]
    b = [gerador.gerar(regra, e, gerador.rng(7, "k"), ctx.data_base).valor for e in ("valido", "abaixo_minimo")]
    assert a == b and a[1] == 999.99
    r = random.Random(1)
    assert all(gerador.documento_valido(gerador.cpf(r)) for _ in range(50))
    assert all(gerador.documento_valido(gerador.cnpj(r)) for _ in range(50))
    assert not gerador.documento_valido(gerador.cpf(r, valido=False))


def test_valido_respeita_conflito_de_dominio(ctx):
    regra = ctx.catalogo.regra(ENT, "motivo_bloqueio")
    vals = {gerador.gerar(regra, "valido", gerador.rng(i, "m")).valor for i in range(40)}
    assert vals <= {"JUD", "ADM"}  # interseção funcional × técnica


# ───── reservas ─────
def test_reservas(ctx):
    rs = ctx.reservas
    assert rs.reservar("garantia:1", "x", "P1", "consumivel")
    assert not rs.reservar("garantia:1", "x", "P2", "consumivel")
    assert not rs.reservar("garantia:1", "x", "P2", "compartilhavel")
    assert rs.reservar("contrato:1", "x", "P1", "compartilhavel")
    assert rs.reservar("contrato:1", "x", "P2", "compartilhavel")
    assert not rs.reservar("contrato:1", "x", "P3", "consumivel")
    assert rs.reservar("contrato:9", "x", "P1", "consumivel", prazo_s=0)
    assert rs.reservar("contrato:9", "x", "P2", "consumivel")       # a anterior já expirou
    assert rs.expirar() >= 1


def test_garimpo_respeita_reserva(ctx):
    achados = garimpar(ctx, "credito:contrato.ativo", 5, uso="consumivel")
    assert len(achados) == 3
    ctx.reservas.reservar(achados[0]["registro"], "credito:contrato.ativo", "P1", "consumivel")
    assert len(garimpar(ctx, "credito:contrato.ativo", 5, uso="consumivel")) == 2
    assert garimpar(ctx, f"{ENT}.associada", 1)[0]["atributos"]["id_contrato_vigente"] == 1


# ───── provisionamento ─────
def test_provisiona_ate_bloqueada_sem_duplicar(ctx):
    antes = _conta(ctx, "garantia")
    inst = provisionar(ctx, {"id": "i1", "estado": f"{ENT}.inexistente", "chave": None, "atributos": {}},
                       BLOQ, "P1", 42, {})
    assert inst["estado"] == BLOQ and _conta(ctx, "garantia") == antes + 1
    assert any(e["dados"]["registro"].startswith("contrato:") for e in ctx.eventos.listar("P1", ["reserva_feita"]))
    inst2 = provisionar(ctx, {"id": "i1", "estado": f"{ENT}.inexistente", "chave": None, "atributos": {}},
                        BLOQ, "P1", 42, {})
    assert inst2["chave"] == inst["chave"] and _conta(ctx, "garantia") == antes + 1


def test_provisiona_contrato_quando_garimpo_vazio(ctx):
    for i in range(3):
        ctx.reservas.reservar(f"contrato:{i + 1}", "x", "OUTRO", "consumivel")
    antes = _conta(ctx, "contrato")
    provisionar(ctx, {"id": "i1", "estado": f"{ENT}.inexistente", "chave": None, "atributos": {}},
                f"{ENT}.associada", "P2", 1, {})
    assert _conta(ctx, "contrato") == antes + 1


def test_valor_invalido_nunca_vai_para_o_banco(ctx, monkeypatch):
    antes = _conta(ctx, "garantia")
    real = gerador.gerar
    monkeypatch.setattr("massa.motor.provisionador.gerar",
                        lambda regra, est, r, db=None, destino="entrada": real(regra, "abaixo_minimo", r)
                        if regra.campo == "valor_avaliacao" else real(regra, est, r))
    with pytest.raises(FalhaCaminho):
        provisionar(ctx, {"id": "i9", "estado": f"{ENT}.inexistente", "chave": None, "atributos": {}},
                    f"{ENT}.ativa_sem_vinculo", "P3", 1, {})
    assert _conta(ctx, "garantia") == antes


# ───── montador ─────
def _spec(**kw):
    d = dict(id="CT", titulo="t", operacao="inclusao", entidade=ENT, tipo="positivo")
    d.update(kw)
    return EspecificacaoCenario(**d)


def test_payload_negativo_viola_exatamente_a_variacao(ctx):
    p = montar_payload(ctx, _spec(tipo="negativo", variacoes=[{"campo": "valor_avaliacao", "regra": "abaixo_minimo"}]),
                       None, {}, "P:c1")
    assert p["body"]["valor_avaliacao"] == "999.99"
    positivo = montar_payload(ctx, _spec(), None, {}, "P:c2")
    assert ctx.http.post("/v1/garantias/imobiliarias", json=positivo["body"]).status_code == 201
    assert ctx.http.post("/v1/garantias/imobiliarias", json=p["body"]).status_code == 422
    with pytest.raises(FalhaCaminho):   # entrada explícita inválida num cenário positivo
        montar_payload(ctx, _spec(entradas={"valor_avaliacao": 10}), None, {}, "P:c3")


def test_roteiro_de_tela(ctx, servidor, tmp_path):
    ctx.http = httpx.Client(base_url=servidor)
    ctx.api_base = servidor
    spec = _spec(modo_execucao="tela")
    p = montar_payload(ctx, spec, None, {}, "P:tela")
    roteiro = montar_roteiro_tela(ctx, spec, p, tmp_path / "tela")
    res = executar_roteiro(ctx, roteiro, "P", "P:tela:exec")
    assert res["status"] == 201 and Path(res["evidencia"]).exists()


# ───── verificação com propagação ─────
def test_verificador_espera_propagacao(ctx):
    spec = _spec(operacao="bloqueio", resultado_esperado=[
        {"descricao": "garantia bloqueada", "verificacao": {"estado": BLOQ, "papel": "alvo"},
         "origem": "funcional", "fonte": "FN-GAR-003"}])
    alvo = garimpar(ctx, f"{ENT}.associada", 1)[0]
    r = ctx.http.post(f"/v1/garantias/{alvo['chave']}/bloqueios", json={"motivo_bloqueio": "JUD"})
    sem_espera = verificar(ctx, spec, {"status": r.status_code}, {"alvo": alvo}, "PX", espera=False)
    assert not sem_espera["ok"]
    com_espera = verificar(ctx, spec, {"status": r.status_code}, {"alvo": alvo}, "PY", espera=True)
    assert com_espera["ok"]


# ───── época ─────
def test_epoca_invalida_reservas(ctx, db_url):
    from demo.banco import resetar
    assert verificar_epoca(ctx) is False
    ctx.reservas.reservar("garantia:1", "x", "P1", "consumivel")
    assert verificar_epoca(ctx) is False
    ctx.engine.dispose()
    resetar(db_url)
    assert verificar_epoca(ctx) is True
    assert ctx.reservas.ativas() == []
