import pytest
from pydantic import ValidationError

from massa.contratos import EspecificacaoCenario, Suite


def base(**kw):
    d = dict(id="CT-1", titulo="t", operacao="bloqueio", entidade="garantias:garantia_imobiliaria", tipo="positivo")
    d.update(kw)
    return d


def test_especificacao_valida():
    e = EspecificacaoCenario(**base(resultado_esperado=[{"descricao": "x", "verificacao": {"http_status": 202},
                                                          "origem": "funcional", "fonte": "FN-GAR-003"}]))
    assert e.avisos == []


def test_negativo_sem_variacao_rejeitado():
    with pytest.raises(ValidationError):
        EspecificacaoCenario(**base(tipo="negativo"))


def test_negativo_com_variacao_valida_rejeitado():
    with pytest.raises(ValidationError):
        EspecificacaoCenario(**base(tipo="negativo", variacoes=[{"campo": "x", "regra": "limite_inferior"}]))


def test_operacao_invalida_rejeitada():
    with pytest.raises(ValidationError):
        EspecificacaoCenario(**base(operacao="apagar"))


def test_aviso_oraculo_nao_independente():
    e = EspecificacaoCenario(**base(resultado_esperado=[{"descricao": "x", "verificacao": {"http_status": 202},
                                                          "origem": "tecnica"}]))
    assert "oraculo_nao_independente" in e.avisos


def test_suite_ids_repetidos():
    with pytest.raises(ValidationError):
        Suite(id="S", cenarios=[base(), base()])
