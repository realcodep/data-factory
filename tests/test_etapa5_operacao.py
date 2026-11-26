import json
import shutil
from pathlib import Path

import pytest

from massa import operacao
from massa.cli_extra import rodar_cenario
from massa.motor.garimpo import garimpar
from massa.planejamento.servico import Servico

ENT = "garantias:garantia_imobiliaria"


@pytest.fixture
def catalogo_isolado(tmp_path, ctx):
    """Cópia do catálogo para os canários poderem marcar saúde sem afetar o repositório."""
    from massa.catalogo import Catalogo
    raiz = tmp_path / "catalogo"
    shutil.copytree("catalogo", raiz)
    ctx.catalogo = Catalogo.carregar(raiz, verificar_defasagem=False)
    return ctx


def test_pool_reabastece(ctx):
    antes = len(garimpar(ctx, f"{ENT}.associada", 10, uso="consumivel", telemetria=False))
    garimpar(ctx, f"{ENT}.bloqueada", 10, uso="consumivel", excluir={"garantia:2"})  # gera telemetria de garimpo vazio
    r = operacao.reabastecer_pool(ctx)
    assert r["estados"][0]["estado"] == f"{ENT}.bloqueada"          # priorizado pela telemetria
    assert len(garimpar(ctx, f"{ENT}.associada", 10, uso="consumivel", telemetria=False)) >= max(antes, 3)
    assert ctx.reservas.ativas() == []                                # pool fica livre para garimpo


def test_canarios_detectam_receita_quebrada(catalogo_isolado):
    ctx = catalogo_isolado
    r = operacao.rodar_canarios(ctx)
    assert set(r["receitas"].values()) == {"saudavel"}
    ctx.catalogo.interfaces["garantias:bloquear"].caminho = "/v1/garantias/{id_garantia}/bloqueio-inexistente"
    r = operacao.rodar_canarios(ctx)
    assert r["receitas"]["garantias:bloquear"] == "quebrada"
    assert ctx.catalogo.caminho(f"{ENT}.inexistente", f"{ENT}.bloqueada") is None   # o planejador passa a evitar
    svc = Servico(ctx)
    p = svc.planejar_suite({"id": "SQ", "cenarios": [{"id": "C1", "titulo": "t", "operacao": "desassociacao",
                            "entidade": ENT, "tipo": "negativo", "modo_execucao": "somente_massa",
                            "precondicoes": [{"estado": f"{ENT}.bloqueada", "uso": "consumivel", "papel": "alvo"}]}]})
    # há garantia bloqueada no banco (garimpo), então o cenário ainda é atendido mesmo com a receita quebrada
    assert svc.simular_plano(p["plano_id"])["estrategias"]["I-01"] == "garimpar"
    assert operacao.metricas(ctx)["receitas_quebradas_detectadas"] >= 1


def test_cenario_executavel_gera_massa_nova(ctx):
    svc = Servico(ctx)
    spec = {"id": "CX", "titulo": "inclusão", "operacao": "inclusao", "entidade": ENT, "tipo": "positivo",
            "resultado_esperado": [{"descricao": "criada", "verificacao": {"estado": f"{ENT}.ativa_sem_vinculo", "papel": "alvo"},
                                    "origem": "funcional", "fonte": "FN-GAR-008"}]}
    p = svc.planejar_suite({"id": "S-CX", "cenarios": [spec]})
    svc.simular_plano(p["plano_id"])
    rel = svc.executar_plano(p["plano_id"])
    pasta = ctx.saida / "cenarios" / "CX"
    assert (pasta / "especificacao.json").exists() and (pasta / "plano_modelo.json").exists()
    r1 = rodar_cenario(svc, pasta)
    r2 = rodar_cenario(svc, pasta)
    assert r1["resumo"]["ok"] == r2["resumo"]["ok"] == 1
    criados = [e["dados"]["chave"] for e in ctx.eventos.listar(tipos=["registro_criado"])]
    assert len(criados) == len(set(criados)) == 3        # cada execução criou a sua própria garantia


def test_metricas(ctx):
    m = operacao.metricas(ctx)
    assert set(m) >= {"perguntas_por_cenario", "cenarios_concluidos_sem_intervencao", "taxa_garimpo",
                      "receitas_quebradas_detectadas", "expectativas_sem_fonte_funcional", "decisoes_por_degrau"}
