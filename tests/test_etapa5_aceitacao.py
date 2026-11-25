import json
from pathlib import Path

import yaml

from massa.planejamento.servico import Servico
from tests.aceitacao import qa_lead_simulado as qa

SUITE = Path("tests/aceitacao/suite_imobiliario.yaml")


def rodar_suite(svc: Servico) -> tuple[dict, int]:
    entrada = yaml.safe_load(SUITE.read_text(encoding="utf-8"))
    specs = [s for c in entrada["cenarios"] for s in qa.interpretar(c)]
    plano = svc.planejar_suite({"id": entrada["id"], "historia": entrada["historia"], "cenarios": specs})
    pid = plano["plano_id"]
    for d in qa.decisoes_de_interpretacao():
        svc.registrar_interpretacao(pid, **d)
    sim = svc.simular_plano(pid)
    pend = {p["id"]: p for p in sim["pendencias_para_qa_lead"]}
    decisoes, perguntas = qa.decidir(list(pend.values()))
    for d in decisoes:
        svc.registrar_decisao(pid, **d)
    if perguntas:
        svc.registrar_perguntas(pid, perguntas)
        for q in perguntas:
            for d in qa.resposta_humana(q, pend):
                svc.registrar_decisao(pid, **d)
    if sim["aprovacao_necessaria"]:
        svc.aprovar_plano(pid, "aprovador-ci")
    return svc.executar_plano(pid), len(perguntas)


def test_suite_de_aceitacao(ctx):
    svc = Servico(ctx)
    rel, n_perguntas = rodar_suite(svc)
    status = {c["id"]: c["status"] for c in rel["cenarios"]}
    assert n_perguntas == 1, "o único cenário que exige pergunta é o CT-08"
    esperado = {"CT-01": "ok", "CT-02": "ok", "CT-03": "ok", "CT-04": "ok", "CT-05": "ok", "CT-06": "ok",
                "CT-07a": "ok", "CT-07b": "ok", "CT-08": "divergencia"}
    assert status == esperado, json.dumps(rel["cenarios"], ensure_ascii=False, indent=1)[:4000]
    ct08 = next(c for c in rel["cenarios"] if c["id"] == "CT-08")
    assert ct08["resposta"]["status"] == 202           # o código aceita FRA...
    assert ct08["verificacao"]["itens"][0]["origem"] == "funcional"   # ...mas o normativo diz que não: possível defeito
    degraus = {d["degrau"] for d in rel["decisoes"]}
    assert {"convencao", "duas_leituras", "humano"} <= degraus or {"duas_leituras", "humano"} <= degraus
    from massa.operacao import metricas
    m = metricas(ctx)
    assert m["perguntas_ao_humano"] == 1 and m["cenarios_planejados"] == 9
