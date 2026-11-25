"""Operação contínua: pool pré-aquecido, canários de receitas e métricas."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from massa import config
from massa.guardiao import Guardiao
from massa.motor.contexto import Contexto, FalhaMotor
from massa.motor.garimpo import garimpar
from massa.motor.provisionador import executar_receita, provisionar


def _carimbo() -> str:
    import uuid
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]


def reabastecer_pool(ctx: Contexto, guardiao: Guardiao | None = None) -> dict:
    """Garante o mínimo de registros livres por estado. Prioriza estados com mais garimpo vazio."""
    g = guardiao or Guardiao(ambiente=ctx.ambiente)
    ctx.autorizar = g.autorizador(None, exigir_plano=False)
    cfg = config.carregar("pool").get("estados", [])
    vazios = Counter(e["dados"]["estado"] for e in ctx.eventos.listar(tipos=["garimpo_vazio"]))
    cfg = sorted(cfg, key=lambda c: -vazios.get(c["estado"], 0))
    plano_id = f"POOL-{_carimbo()}"
    relatorio = []
    for item in cfg:
        livres = len(garimpar(ctx, item["estado"], quantidade=item["minimo"], uso="consumivel", telemetria=False))
        criados = 0
        for n in range(max(item["minimo"] - livres, 0)):
            entidade = item["estado"].split(".")[0]
            inst = {"id": f"pool-{item['estado']}-{n}", "estado": ctx.catalogo.inexistente(entidade), "chave": None,
                    "atributos": {}}
            try:
                provisionar(ctx, inst, item["estado"], plano_id, 7, {})
                criados += 1
            except FalhaMotor as e:
                relatorio.append({"estado": item["estado"], "erro": str(e)})
                break
        relatorio.append({"estado": item["estado"], "livres_antes": livres, "criados": criados,
                          "prioridade_garimpo_vazio": vazios.get(item["estado"], 0)})
    ctx.reservas.liberar(plano_id, motivo="pool_disponivel")   # dependências usadas no pool voltam a ficar livres
    return {"plano_id": plano_id, "estados": relatorio}


def rodar_canarios(ctx: Contexto, guardiao: Guardiao | None = None) -> dict:
    """Executa cada receita aprovada de ponta a ponta. Receita que falha vira 'quebrada' (o planejador passa a evitá-la)."""
    g = guardiao or Guardiao(ambiente=ctx.ambiente)
    ctx.autorizar = g.autorizador(None, exigir_plano=False)
    plano_id = f"CANARIO-{_carimbo()}"
    resultado = {}
    for rid, receita in sorted(ctx.catalogo.receitas.items()):
        if not receita.aprovada:
            continue
        entidade = receita.entidade
        rota = ctx.catalogo.caminho(ctx.catalogo.inexistente(entidade), receita.origem, evitar_quebradas=False) or []
        inst = {"id": f"can-{rid}", "estado": ctx.catalogo.inexistente(entidade), "chave": None, "atributos": {}}
        atual = None
        try:
            for r in [*rota, receita]:
                atual = r.id
                executar_receita(ctx, r, inst, plano_id, 11, {}, ultima=True)
            resultado[rid] = "saudavel"
            ctx.eventos.registrar("receita_saudavel", {"receita": rid}, plano_id)
        except FalhaMotor as e:
            # a receita que falhou é a culpada; a receita testada fica indisponível se dependia dela
            resultado[atual] = "quebrada"
            if atual != rid:
                resultado[rid] = f"indisponivel:{atual}"
            ctx.eventos.registrar("receita_quebrada", {"receita": atual, "testando": rid, "erro": str(e)[:300]}, plano_id)
            ctx.catalogo.marcar_saude(atual, "quebrada")
            continue
        ctx.catalogo.marcar_saude(rid, resultado[rid])
    ctx.reservas.liberar(plano_id, motivo="canario_concluido")
    return {"plano_id": plano_id, "receitas": resultado}


def metricas(ctx: Contexto) -> dict:
    ev = ctx.eventos
    planos = {e["plano_id"]: e["dados"] for e in ev.listar(tipos=["plano_criado"])}
    n_cenarios = sum(len(p["suite"]["cenarios"]) for p in planos.values())
    perguntas = Counter(e["plano_id"] for e in ev.listar(tipos=["pergunta_feita"]))
    aprovados = {e["plano_id"] for e in ev.listar(tipos=["plano_aprovado"])}
    concluidos = {e["plano_id"]: e["dados"] for e in ev.listar(tipos=["plano_concluido"])}
    sem_intervencao = sum(d["cenarios_ok"] for pid, d in concluidos.items()
                          if pid not in aprovados and not perguntas.get(pid))
    por_instancia: dict[tuple, str] = {}
    for e in ev.listar(tipos=["passo_concluido"]):
        passo = e["dados"]["passo"]
        r = e["dados"].get("resultado") or {}
        if isinstance(r, dict) and r.get("origem") and passo.startswith(("F2.", "F3.")):
            chave = (e["plano_id"], passo.split(".")[-1])
            if passo.startswith("F3.") or chave not in por_instancia:   # F3 (final) prevalece sobre F2
                por_instancia[chave] = r["origem"]
    origens = Counter(por_instancia.values())
    expectativas = Counter()
    for e in ev.listar(tipos=["verificacao_concluida"]):
        for item in e["dados"].get("itens", []):
            expectativas[item["origem"]] += 1
    degraus = Counter(e["dados"]["degrau"] for e in ev.listar(tipos=["decisao_tomada"]))
    return {
        "cenarios_planejados": n_cenarios,
        "perguntas_ao_humano": sum(perguntas.values()),
        "perguntas_por_cenario": round(sum(perguntas.values()) / n_cenarios, 3) if n_cenarios else 0,
        "cenarios_concluidos_sem_intervencao": sem_intervencao,
        "massa_por_origem": dict(origens),
        "taxa_garimpo": round(origens["garimpo"] / sum(origens.values()), 3) if origens else None,
        "receitas_quebradas_detectadas": len(ev.listar(tipos=["receita_quebrada"])),
        "expectativas_por_origem": dict(expectativas),
        "expectativas_sem_fonte_funcional": sum(v for k, v in expectativas.items() if k != "funcional"),
        "decisoes_por_degrau": dict(degraus),
    }
