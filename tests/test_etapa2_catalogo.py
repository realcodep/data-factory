import shutil
from pathlib import Path

import pytest
import yaml

from massa import catalogo as cat
from massa.catalogo.consolidacao import consolidar
from massa.catalogo.extratores import (extrair_banco, extrair_copybook, extrair_domain_pack, extrair_java,
                                       extrair_openapi, normalizar)
from massa.contratos import Fonte, RegraCampo

NOMES = {"prefixos": ["GAR-"], "sinonimos": yaml.safe_load(open("catalogo/sinonimos.yaml"))["sinonimos"]}


def _por(regras):
    return {r.campo: r for r in regras}


def test_normalizacao():
    assert normalizar("GAR-VLR-AVALIACAO", **NOMES) == "valor_avaliacao"
    assert normalizar("valorAvaliacao", **NOMES) == "valor_avaliacao"
    assert normalizar("motivoBloqueio", **NOMES) == "motivo_bloqueio"


def test_copybook():
    r = _por(extrair_copybook("demo/fontes/CPGAR10.cpy", **NOMES))
    v = r["valor_avaliacao"]
    assert (v.tipo, v.tamanho, v.decimais, v.maximo) == ("decimal", 15, 2, 9999999999999.99)
    assert r["situacao"].dominio == ["A", "B", "E"]
    assert r["motivo_bloqueio"].fontes[0].referencia.startswith("demo/fontes/CPGAR10.cpy:")


def test_java():
    r = _por(extrair_java("demo/fontes/GarantiaImobiliariaRequest.java", **NOMES))
    assert r["valor_avaliacao"].minimo == 1000.0 and r["valor_avaliacao"].obrigatorio
    assert r["matricula_imovel"].padrao == r"\d{6,10}" and r["matricula_imovel"].tamanho == 20
    assert r["data_avaliacao"].semantica == "pastOrPresent"
    assert all(":" in f.referencia for f in r["valor_avaliacao"].fontes)
    b = _por(extrair_java("demo/fontes/BloqueioRequest.java", **NOMES))
    assert b["motivo_bloqueio"].dominio == ["JUD", "ADM", "FRA"]


def test_banco(db_url):
    r = _por(extrair_banco(db_url, "garantia", **NOMES))
    assert r["matricula_imovel"].tamanho == 20 and r["matricula_imovel"].obrigatorio
    assert r["motivo_bloqueio"].dominio == ["JUD", "ADM", "FRA"]
    assert r["valor_avaliacao"].fontes[0].referencia == "garantia.valor_avaliacao"


def test_openapi_e_domain_pack():
    r = _por(extrair_openapi("catalogo/garantias/openapi.json", ["NovaGarantia"], **NOMES))
    assert r["matricula_imovel"].tamanho == 20
    funcionais, negocio = extrair_domain_pack("demo/fontes/domain_pack/fatos.json", "garantias:garantia_imobiliaria", **NOMES)
    assert {f.campo for f in funcionais} == {"valor_avaliacao", "motivo_bloqueio"}
    assert any(f["id"] == "FN-GAR-003" for f in negocio)


def _r(campo, origem, **kw):
    return RegraCampo(campo=campo, fontes=[Fonte(origem=origem, referencia=f"{origem}:1")], **kw)


def test_mais_restritiva_vence():
    regras, conflitos = consolidar([
        _r("x", "copybook", tipo="decimal", tamanho=15, maximo=9999.0, minimo=0.0),
        _r("x", "java", tipo="decimal", minimo=1000.0, obrigatorio=True),
        _r("x", "banco", tipo="decimal", tamanho=12, maximo=99999.0),
    ], "e")
    x = regras["x"]
    assert (x.tamanho, x.minimo, x.maximo, x.obrigatorio) == (12, 1000.0, 9999.0, True)
    assert len(x.fontes) == 3 and not conflitos


def test_conflito_registrado_e_nao_resolvido():
    regras, conflitos = consolidar([
        _r("m", "java", tipo="enum", dominio=["A", "B", "C"]),
        _r("m", "funcional", tipo="enum", dominio=["A", "B"]),
    ], "e")
    assert conflitos and conflitos[0]["tipo"] == "funcional_x_tecnico"
    assert regras["m"].dominio == ["A", "B", "C"]  # não escolheu sozinho
    assert regras["m"].conflito is not None


def test_predicados_executam_e_grafo(db_url):
    defs = cat.carregar_definicoes()
    assert cat.validar(defs, banco_url=db_url) == []


def _copia(tmp_path):
    raiz = tmp_path / "catalogo"
    shutil.copytree("catalogo", raiz, ignore=shutil.ignore_patterns("dist"))
    return raiz


def test_federacao_referencia_quebrada(tmp_path, db_url):
    raiz = _copia(tmp_path)
    p = raiz / "garantias" / "receitas.yaml"
    p.write_text(p.read_text().replace("credito:contrato.ativo", "credito:contrato.inexistente_xyz"))
    erros = cat.validar(cat.carregar_definicoes(raiz), raiz)
    assert any("inexistente_xyz" in e for e in erros)


def test_federacao_dependencia_nao_declarada(tmp_path):
    raiz = _copia(tmp_path)
    p = raiz / "clusters.yaml"
    p.write_text(p.read_text().replace("depende_de: [credito]", "depende_de: []"))
    assert any("sem declarar dependência" in e for e in cat.validar(cat.carregar_definicoes(raiz), raiz))


def test_build_vocabulario_e_defasagem(tmp_path, db_url):
    raiz = _copia(tmp_path)
    d = cat.construir(raiz, db_url)
    assert (raiz / "dist" / "vocabulario.json").exists() and len(d["conflitos"]) == 1
    c = cat.Catalogo.carregar(raiz)
    assert not c.desatualizado
    assert [r.id for r in c.caminho("garantias:garantia_imobiliaria.inexistente",
                                     "garantias:garantia_imobiliaria.bloqueada")] == \
        ["garantias:incluir_garantia", "garantias:associar", "garantias:bloquear"]
    p = raiz / "garantias" / "estados.yaml"
    p.write_text(p.read_text() + "\n# mudança\n")
    c2 = cat.Catalogo.carregar(raiz)
    assert c2.desatualizado
    with pytest.raises(cat.CatalogoDesatualizado):
        c2.exigir_atualizado()
