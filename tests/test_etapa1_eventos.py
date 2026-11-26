import sqlite3

import pytest


def test_idempotencia(eventos):
    assert eventos.registrar("registro_criado", {"instancia": "i1"}, "P1", chave="P1:F3:i1") is not None
    assert eventos.registrar("registro_criado", {"instancia": "i1"}, "P1", chave="P1:F3:i1") is None
    assert len(eventos.listar("P1")) == 1


def test_somente_acrescimo(eventos):
    eventos.registrar("plano_criado", {"plano": {"id": "P1"}}, "P1")
    with pytest.raises(sqlite3.DatabaseError):
        eventos.con.execute("UPDATE eventos SET tipo='x'")
    with pytest.raises(sqlite3.DatabaseError):
        eventos.con.execute("DELETE FROM eventos")


def test_tipo_desconhecido(eventos):
    with pytest.raises(ValueError):
        eventos.registrar("qualquer", {})


def test_checkpoint_reconstroi_plano(eventos):
    eventos.registrar("plano_criado", {"plano": {"id": "P1"}}, "P1")
    eventos.registrar("fase_concluida", {"fase": "F0"}, "P1")
    eventos.registrar("passo_concluido", {"passo": "F2.res.i1", "resultado": {"id": 3}}, "P1")
    eventos.registrar("reserva_feita", {"registro": "garantia:3"}, "P1")
    eventos.registrar("registro_criado", {"instancia": "i2", "chave": {"id": 9}}, "P1")
    ck = eventos.checkpoint("P1")
    assert ck["plano"]["id"] == "P1" and ck["fases_concluidas"] == ["F0"]
    assert "garantia:3" in ck["reservas"] and "i2" in ck["registros"]
    eventos.registrar("plano_replanejado", {"plano": {"id": "P1", "versao": 2}, "fases_validas": []}, "P1")
    ck = eventos.checkpoint("P1")
    assert ck["fases_concluidas"] == [] and ck["passos_concluidos"] == {}


def test_precedentes(eventos):
    for _ in range(2):
        eventos.registrar("decisao_tomada", {"pendencia_id": "p", "assinatura": "A", "degrau": "premissa", "escolha": 1})
    eventos.registrar("decisao_tomada", {"pendencia_id": "q", "assinatura": "B", "degrau": "premissa", "escolha": 1})
    assert set(eventos.precedentes(2)) == {"A"}
    eventos.registrar("decisao_contestada", {"assinatura": "A"})
    assert "A" not in eventos.precedentes(2)
