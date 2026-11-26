"""Resolvedor de decisões determinístico: degraus 1 a 3 da escada (fato, convenção, precedente). Sem LLM.

O que sobra vira pendência estruturada para o agente QA Lead (degraus 4 a 7).
"""
from __future__ import annotations

from massa import config
from massa.contratos import Decisao, Degrau, Pendencia, Plano, Suite
from massa.eventos import RegistroEventos

NAO_DECIDIVEIS = {"aprovacao", "falha_politica"}   # aprovação é ato humano; política não se decide


def registrar(ev: RegistroEventos, plano_id: str, d: Decisao) -> None:
    ev.registrar("decisao_tomada", d.model_dump(mode="json"), plano_id, chave=f"{plano_id}:decisao:{d.pendencia_id}")


def _convencao(p: Pendencia, suite: Suite, convs: list[dict]) -> dict | None:
    tipos = {s.id: s.tipo for s in suite.cenarios}
    for c in convs:
        if c["tipo"] != p.tipo:
            continue
        if c.get("assinatura_prefixo") and not p.assinatura.startswith(c["assinatura_prefixo"]):
            continue
        quando = c.get("quando", {})
        if "tipo_cenario" in quando and any(tipos.get(cid) != quando["tipo_cenario"] for cid in p.cenarios):
            continue
        return c
    return None


def resolver(ev: RegistroEventos, plano: Plano, suite: Suite) -> list[Decisao]:
    cfg = config.carregar("convencoes")
    convs = cfg.get("convencoes", [])
    precedentes = ev.precedentes(cfg.get("precedente_minimo_aplicacoes", 2))
    decididas: list[Decisao] = []
    for p in plano.pendencias:
        if p.decisao or p.tipo in NAO_DECIDIVEIS:
            continue
        d: Decisao | None = None
        if len(p.opcoes) == 1 and p.tipo in ("termo_desconhecido",):
            d = Decisao(pendencia_id=p.id, assinatura=p.assinatura, duvida=p.duvida, degrau=Degrau.FATO,
                        escolha=p.opcoes[0], justificativa="Única opção existente no catálogo.",
                        evidencias=["catalogo"], confianca=1.0)
        elif (c := _convencao(p, suite, convs)) is not None:
            d = Decisao(pendencia_id=p.id, assinatura=p.assinatura, duvida=p.duvida, degrau=Degrau.CONVENCAO,
                        escolha=c["escolha"], justificativa=c["justificativa"], evidencias=[f"config/convencoes.yaml#{c['id']}"],
                        confianca=0.9)
        elif p.assinatura in precedentes:
            prec = precedentes[p.assinatura]
            d = Decisao(pendencia_id=p.id, assinatura=p.assinatura, duvida=p.duvida, degrau=Degrau.PRECEDENTE,
                        escolha=prec["escolha"], justificativa=f"Precedente: {prec['justificativa']}",
                        evidencias=[f"decisao:{prec['pendencia_id']}"], confianca=prec.get("confianca", 0.8),
                        reversivel=prec.get("reversivel", True))
        if d:
            p.decisao = d
            registrar(ev, plano.id, d)
            decididas.append(d)
    return decididas


def aplicar_decisoes_registradas(ev: RegistroEventos, plano: Plano) -> None:
    """Recarrega no plano as decisões gravadas no registro de eventos (inclusive as do QA Lead e humanas)."""
    gravadas = ev.checkpoint(plano.id)["decisoes"]
    for p in plano.pendencias:
        if p.id in gravadas and p.decisao is None:
            p.decisao = Decisao(**gravadas[p.id])


def pendentes(plano: Plano) -> list[Pendencia]:
    return [p for p in plano.pendencias if p.decisao is None and p.tipo != "aprovacao"]


def cenarios_bloqueados(plano: Plano) -> set[str]:
    bloq = set()
    for p in plano.pendencias:
        if p.tipo == "aprovacao":
            continue
        if p.decisao is None and (p.afeta_resultado or p.tipo in ("sem_caminho", "falha_politica", "lacuna_catalogo",
                                                                   "termo_desconhecido", "especificacao_incoerente")):
            bloq |= set(p.cenarios)
        elif p.decisao is not None and p.decisao.degrau in (Degrau.PARCIAL,):
            bloq |= set(p.cenarios)
    return bloq
