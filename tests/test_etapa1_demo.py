import time

from sqlalchemy import create_engine, text

NOVA = {"matricula_imovel": "1234500", "valor_avaliacao": "250000.00", "data_avaliacao": "2025-05-01",
        "cpf_cnpj_proprietario": "52998224725"}


def _situacao(db_url, gid):
    with create_engine(db_url).connect() as c:
        return c.execute(text("select situacao from garantia where id=:i"), {"i": gid}).scalar()


def test_cinco_operacoes(api, db_url):
    cid = api.post("/v1/contratos", json={"numero": "CT-X", "cpf_cnpj_cliente": "11144477735", "valor": "1000"}).json()["id_contrato"]
    gid = api.post("/v1/garantias/imobiliarias", json=NOVA).json()["id_garantia"]
    assert api.post(f"/v1/garantias/{gid}/associacoes", json={"id_contrato": cid}).status_code == 201
    assert api.post(f"/v1/garantias/{gid}/desassociacoes", json={"id_contrato": cid}).status_code == 200
    assert api.delete(f"/v1/garantias/{gid}").status_code == 200
    gid2 = api.post("/v1/garantias/imobiliarias", json=NOVA).json()["id_garantia"]
    api.post(f"/v1/garantias/{gid2}/associacoes", json={"id_contrato": cid})
    assert api.post(f"/v1/garantias/{gid2}/bloqueios", json={"motivo_bloqueio": "JUD"}).status_code == 202


def test_regras_de_negocio(api):
    assert api.post("/v1/garantias/imobiliarias", json=NOVA | {"valor_avaliacao": "999.99"}).status_code == 422
    assert api.post("/v1/garantias/imobiliarias", json=NOVA | {"cpf_cnpj_proprietario": "52998224726"}).status_code == 422
    assert api.post("/v1/garantias/2/bloqueios", json={"motivo_bloqueio": "JUD"}).status_code == 409  # já bloqueada
    assert api.delete("/v1/garantias/1").status_code == 409  # associada
    assert api.post("/v1/garantias/2/desassociacoes", json={"id_contrato": 2}).status_code == 409  # bloqueada


def test_propagacao_assincrona(api, db_url):
    assert api.post("/v1/garantias/1/bloqueios", json={"motivo_bloqueio": "ADM"}).status_code == 202
    assert _situacao(db_url, 1) == "A"          # ainda não propagou
    time.sleep(0.7)
    assert _situacao(db_url, 1) == "B"          # propagou


def test_telas_e_openapi(api):
    assert 'id="campo-matricula_imovel"' in api.get("/telas/garantias/inclusao").text
    assert "/v1/garantias/{gid}/bloqueios" in api.get("/openapi.json").json()["paths"]
