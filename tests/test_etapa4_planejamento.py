import asyncio
import json

import pytest
from sqlalchemy import text

from massa.contratos import Suite
from massa.guardiao import Guardiao
from massa.motor.contexto import FalhaPolitica
from massa.planejamento.condutor import Interrompido
from massa.planejamento.servico import Servico

ENT = "garantias:garantia_imobiliaria"
CT = "credito:contrato.ativo"


def cen(i, op, tipo="positivo", **kw):
    base = {"id": f"C{i}", "titulo": f"cenário {i}", "operacao": op, "entidade": ENT, "tipo": tipo, "modo_execucao": "api"}
    base.update(kw)
    return base


def esp(verificacao, origem="funcional", fonte="FN-GAR-003", d="resultado"):
    return [{"descricao": d, "verificacao": verificacao, "origem": origem, "fonte": fonte}]


def suite_seis():
    """6 cenários; a pré-condição compartilhável 'contrato ativo' aparece em vários (associação)."""
    return {"id": "S6", "cenarios": [
        cen(1, "associacao", resultado_esperado=esp({"estado": f"{ENT}.associada", "papel": "alvo"}, fonte="FN-GAR-006")),
        cen(2, "associacao", resultado_esperado=esp({"aceito": True}, fonte="FN-GAR-006")),
        cen(3, "associacao", modo_execucao="somente_massa"),
        cen(4, "bloqueio", entradas={"motivo_bloqueio": "JUD"},
            resultado_esperado=esp({"estado": f"{ENT}.bloqueada", "papel": "alvo"})),
        cen(5, "inclusao", "negativo", variacoes=[{"campo": "valor_avaliacao", "regra": "abaixo_minimo"}],
            resultado_esperado=esp({"rejeitado": True}, fonte="FN-GAR-005")),
        cen(6, "inclusao", resultado_esperado=esp({"estado": f"{ENT}.ativa_sem_vinculo", "papel": "alvo"}, fonte="FN-GAR-008")),
    ]}


@pytest.fixture
def svc(ctx):
    return Servico(ctx)


def _contagens(ctx):
    with ctx.engine.connect() as c:
        tabs = {t: c.execute(text(f"select count(*) from {t}")).scalar() for t in ("garantia", "contrato", "garantia_contrato")}
    escrita = len(ctx.eventos.listar(tipos=["reserva_feita", "registro_criado", "chamada_executada"]))
    return tabs, escrita


def test_compartilhavel_atendida_uma_vez(svc):
    p = svc.planejar_suite(suite_seis())
    contratos = [i for i in p["instancias"] if i["estado"] == CT]
    assert len(contratos) == 1 and set(contratos[0]["cenarios"]) == {"C1", "C2", "C3"}
    alvos = [i for i in p["instancias"] if i["estado"] == f"{ENT}.ativa_sem_vinculo"]
    assert len(alvos) == 3 and all(i["uso"] == "consumivel" for i in alvos)


def test_plano_a_seco_nao_escreve(svc, ctx):
    p = svc.planejar_suite(suite_seis())
    antes = _contagens(ctx)
    sim = svc.simular_plano(p["plano_id"])
    assert _contagens(ctx) == antes
    assert sim["pendencias_para_qa_lead"] == []
    assert set(sim["estrategias"].values()) <= {"garimpar", "provisionar"}


def test_resolvedor_e_pendencias_estruturadas(svc, ctx):
    s = {"id": "S2", "cenarios": [
        cen(1, "inclusao", "negativo", variacoes=[{"campo": "valor_avaliacao", "regra": "abaixo_minimo"}]),  # convenção
        cen(2, "bloqueio", entradas={"motivo_bloqueio": "FRA"}, resultado_esperado=esp({"aceito": True}, origem="tecnica", fonte=None)),
    ]}
    p = svc.planejar_suite(s)
    sim = svc.simular_plano(p["plano_id"])
    assert [d["degrau"] for d in sim["decididas_sem_ia"]] == ["convencao"]
    tipos = sorted(x["tipo"] for x in sim["pendencias_para_qa_lead"])
    assert tipos == ["conflito_regra", "oraculo_sem_fonte"]
    assert all(x["cenarios"] == ["C2"] for x in sim["pendencias_para_qa_lead"])
    # precedente: depois de 2 decisões iguais não contestadas, a 3ª vem do histórico
    pd = next(x for x in sim["pendencias_para_qa_lead"] if x["tipo"] == "conflito_regra")
    svc.registrar_decisao(p["plano_id"], pd["id"], "seguir_normativo", "premissa", "normativo prevalece")
    ctx.eventos.registrar("decisao_tomada", {"pendencia_id": "x", "assinatura": pd["assinatura"], "degrau": "premissa",
                                             "escolha": "seguir_normativo", "justificativa": "idem"}, "OUTRO")
    p2 = svc.planejar_suite({**s, "id": "S2b"})
    sim2 = svc.simular_plano(p2["plano_id"])
    assert "precedente" in [d["degrau"] for d in sim2["decididas_sem_ia"]]


def test_execucao_ponta_a_ponta(svc, ctx):
    p = svc.planejar_suite(suite_seis())
    svc.simular_plano(p["plano_id"])
    rel = svc.executar_plano(p["plano_id"])
    assert rel["resumo"]["ok"] == 6, json.dumps(rel["cenarios"], indent=1, ensure_ascii=False)[:3000]
    assert (ctx.saida / "cenarios" / "C4" / "especificacao.json").exists()
    # mascaramento: CPF/CNPJ não sai inteiro pelo serviço
    pacote = json.loads((ctx.saida / "planos" / p["plano_id"] / "C6" / "pacote_massa.json").read_text())
    doc = next(r["valor"] for r in pacote["payload"]["rastreio"] if r["campo"] == "cpf_cnpj_proprietario")
    assert doc not in json.dumps(svc._out(pacote)) and doc in json.dumps(pacote)


def test_guardiao(ctx):
    from massa.contratos import Plano
    g = Guardiao(ambiente="DEMO")
    plano = Plano(id="P", suite_id="S", catalogo_hash="h", acoes_previstas=["api:garantias:incluir"])
    aut = g.autorizador(plano)
    aut({"tipo": "api", "interface": "garantias:incluir", "metodo": "POST", "caminho": "/v1/garantias/imobiliarias"})
    with pytest.raises(FalhaPolitica):   # fora do plano
        aut({"tipo": "api", "interface": "garantias:excluir", "metodo": "DELETE", "caminho": "/v1/garantias/1"})
    with pytest.raises(FalhaPolitica):   # endpoint fora da política
        aut({"tipo": "api", "interface": "garantias:incluir", "metodo": "POST", "caminho": "/admin/reset"})
    with pytest.raises(FalhaPolitica):   # produção
        Guardiao(ambiente="PRD").autorizador(plano)({"tipo": "api", "interface": "x", "metodo": "GET", "caminho": "/"})
    with pytest.raises(FalhaPolitica):   # falha fechada: erro interno nega
        Guardiao(politica={"ambientes_permitidos": ["DEMO"]}, ambiente="DEMO").autorizador(plano)(
            {"tipo": "api", "interface": "x", "metodo": "GET", "caminho": "/"})
    assert g.mascarar({"cpf_cnpj_cliente": "52998224725"})["cpf_cnpj_cliente"] == "*********25"


def test_aprovacao_unica(svc):
    s = {"id": "SX", "cenarios": [cen(1, "exclusao", resultado_esperado=esp({"estado": f"{ENT}.excluida", "papel": "alvo"},
                                                                          fonte="FN-GAR-009"))]}
    p = svc.planejar_suite(s)
    sim = svc.simular_plano(p["plano_id"])
    assert sim["aprovacao_necessaria"]
    assert svc.executar_plano(p["plano_id"])["status"] == "aguardando_aprovacao"
    svc.aprovar_plano(p["plano_id"], "tester")
    assert svc.executar_plano(p["plano_id"])["resumo"]["ok"] == 1


def test_retomada_sem_duplicar(svc, ctx):
    # força provisionamento: reserva todos os contratos e garantias livres por outro plano
    with ctx.engine.connect() as c:
        for t in ("contrato", "garantia"):
            for (i,) in c.execute(text(f"select id from {t}")):
                ctx.reservas.reservar(f"{t}:{i}", "x", "OUTRO", "consumivel")
    s = {"id": "SR", "cenarios": [cen(1, "bloqueio", entradas={"motivo_bloqueio": "ADM"},
                                      resultado_esperado=esp({"estado": f"{ENT}.bloqueada", "papel": "alvo"}))]}
    p = svc.planejar_suite(s)
    sim = svc.simular_plano(p["plano_id"])
    assert "provisionar" in sim["estrategias"].values()
    passo_f3 = next(k for k in ["F3.provisionar.I-01"])
    with pytest.raises(Interrompido):
        svc.condutor.executar(p["plano_id"], interromper_apos=passo_f3)
    antes = _contagens(ctx)[0]
    rel = svc.retomar_plano(p["plano_id"])
    assert rel["resumo"]["ok"] == 1
    assert _contagens(ctx)[0]["garantia"] == antes["garantia"]  # nada duplicado na retomada


def test_servidor_mcp(svc):
    from mcp.client.client import Client
    from massa.mcp_server import criar_servidor
    servidor = criar_servidor(svc)

    async def rodar():
        async with Client(servidor) as cli:
            nomes = {t.name for t in (await cli.list_tools()).tools}
            assert {"vocabulario", "planejar_suite", "simular_plano", "executar_plano", "retomar_plano"} <= nomes
            assert not any("sql" in n for n in nomes)
            r = await cli.call_tool("planejar_suite", {"suite": suite_seis()})
            plano_id = json.loads(r.content[0].text)["plano_id"]
            r = await cli.call_tool("simular_plano", {"plano_id": plano_id})
            assert json.loads(r.content[0].text)["pendencias_para_qa_lead"] == []
    asyncio.run(rodar())


def test_queda_no_meio_de_uma_receita(svc, ctx, monkeypatch):
    """Queda DENTRO do provisionamento (após incluir, antes de associar): retomada reaproveita a inclusão."""
    import massa.motor.provisionador as prov
    with ctx.engine.connect() as c:
        for (i,) in c.execute(text("select id from garantia")):
            ctx.reservas.reservar(f"garantia:{i}", "x", "OUTRO", "consumivel")
    s = {"id": "SQ", "cenarios": [cen(1, "bloqueio", entradas={"motivo_bloqueio": "JUD"},
                                      resultado_esperado=esp({"estado": f"{ENT}.bloqueada", "papel": "alvo"}))]}
    p = svc.planejar_suite(s)
    svc.simular_plano(p["plano_id"])
    real = prov.executar_receita
    estado = {"caiu": False}

    def com_queda(ctx_, receita, *a, **k):
        if receita.id == "garantias:associar" and not estado["caiu"]:
            estado["caiu"] = True
            raise Interrompido("queda simulada no meio da F3")
        return real(ctx_, receita, *a, **k)

    monkeypatch.setattr(prov, "executar_receita", com_queda)
    antes = _contagens(ctx)[0]["garantia"]
    with pytest.raises(Interrompido):
        svc.condutor.executar(p["plano_id"])
    assert _contagens(ctx)[0]["garantia"] == antes + 1
    rel = svc.retomar_plano(p["plano_id"])
    assert rel["resumo"]["ok"] == 1
    assert _contagens(ctx)[0]["garantia"] == antes + 1
