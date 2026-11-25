"""Comandos de plano, operação e cenários executáveis."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml


def _svc():
    from massa.motor.contexto import Contexto
    from massa.planejamento.servico import Servico
    return Servico(Contexto.do_ambiente())


def _imprimir(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _ler(caminho: str) -> dict:
    t = Path(caminho).read_text(encoding="utf-8")
    return json.loads(t) if caminho.endswith(".json") else yaml.safe_load(t)


def cmd_plano(a) -> int:
    s = _svc()
    if a.acao == "planejar":
        _imprimir(s.planejar_suite(_ler(a.alvo)))
    elif a.acao == "simular":
        _imprimir(s.simular_plano(a.alvo))
    elif a.acao == "pendencias":
        _imprimir(s.pendencias(a.alvo))
    elif a.acao == "decidir":
        _imprimir(s.registrar_decisao(a.alvo, a.pendencia, json.loads(a.escolha), a.degrau, a.justificativa))
    elif a.acao == "aprovar":
        _imprimir(s.aprovar_plano(a.alvo, a.por))
    elif a.acao in ("executar", "retomar"):
        _imprimir(s.executar_plano(a.alvo))
    elif a.acao == "status":
        _imprimir(s.status_plano(a.alvo))
    elif a.acao == "relatorio":
        _imprimir(s.relatorio(a.alvo))
    return 0


def rodar_cenario(servico, pasta: Path, aprovar: bool = False) -> dict:
    """Reexecuta um cenário executável: nova suíte => novo plano => massa nova (nunca reaproveita IDs)."""
    spec = json.loads((pasta / "especificacao.json").read_text(encoding="utf-8"))
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    suite = {"id": f"RERUN-{spec['id']}-{carimbo}", "cenarios": [spec]}
    p = servico.planejar_suite(suite)
    sim = servico.simular_plano(p["plano_id"])
    if sim["pendencias_para_qa_lead"]:
        return {"status": "pendencias", "plano_id": p["plano_id"], "pendencias": sim["pendencias_para_qa_lead"]}
    if sim["aprovacao_necessaria"]:
        if not aprovar:
            return {"status": "aguardando_aprovacao", "plano_id": p["plano_id"]}
        servico.aprovar_plano(p["plano_id"], "execucao-pipeline")
    return servico.executar_plano(p["plano_id"])


def cmd_rodar(a) -> int:
    r = rodar_cenario(_svc(), Path(a.pasta), a.aprovar)
    _imprimir(r)
    return 0 if r.get("resumo", {}).get("ok") else 1


def cmd_operacao(a) -> int:
    from massa import operacao
    s = _svc()
    if a.cmd == "pool":
        _imprimir(operacao.reabastecer_pool(s.ctx, s.g))
    elif a.cmd == "canarios":
        r = operacao.rodar_canarios(s.ctx, s.g)
        _imprimir(r)
        return 1 if "quebrada" in r["receitas"].values() else 0
    elif a.cmd == "metricas":
        _imprimir(operacao.metricas(s.ctx))
    return 0


def cmd_mcp(a) -> int:
    from massa.mcp_server import main
    main()
    return 0


def registrar(sub) -> None:
    p = sub.add_parser("plano", help="planejar, simular, decidir, aprovar, executar, retomar, status, relatorio")
    p.add_argument("acao", choices=["planejar", "simular", "pendencias", "decidir", "aprovar", "executar", "retomar",
                                    "status", "relatorio"])
    p.add_argument("alvo", help="arquivo da suíte (planejar) ou plano_id")
    p.add_argument("--pendencia")
    p.add_argument("--degrau", default="premissa")
    p.add_argument("--escolha", default="null")
    p.add_argument("--justificativa", default="")
    p.add_argument("--por", default="usuario")
    p.set_defaults(func=cmd_plano)
    r = sub.add_parser("rodar", help="reexecutar um cenário executável (gera massa nova)")
    r.add_argument("pasta")
    r.add_argument("--aprovar", action="store_true")
    r.set_defaults(func=cmd_rodar)
    for nome in ("pool", "canarios", "metricas"):
        o = sub.add_parser(nome)
        if nome == "pool":
            o.add_argument("acao", nargs="?", default="reabastecer")
        o.set_defaults(func=cmd_operacao)
    m = sub.add_parser("mcp", help="sobe o servidor MCP (stdio)")
    m.set_defaults(func=cmd_mcp)
