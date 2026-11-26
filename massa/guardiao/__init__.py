"""Guardião: política como código, aplicada no servidor (não depende do cliente).

- Avalia o PLANO inteiro (no plano a seco) → decide se precisa de aprovação única.
- Autoriza cada AÇÃO em execução: só passa o que foi previsto no plano aprovado.
- Falha fechada: qualquer erro na avaliação = ação negada.
- Mascara dados sensíveis em tudo o que sai do motor para o agente.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from massa import config
from massa.contratos import Plano
from massa.motor.contexto import AMBIENTES_PROIBIDOS, FalhaPolitica


class Guardiao:
    def __init__(self, politica: dict[str, Any] | None = None, ambiente: str = "DEMO"):
        self.p = politica or config.carregar("politica")
        self.ambiente = ambiente

    # ───────── plano ─────────
    def avaliar_plano(self, plano: Plano, receitas_efeito: dict[str, str], acoes_operacao: list[dict]) -> dict:
        motivos, negadas = [], []
        if not self._ambiente_ok():
            negadas.append(f"ambiente {self.ambiente} não permitido")
        lim = self.p.get("limites", {})
        criacoes = sum(1 for i in plano.instancias if i.estrategia == "provisionar")
        if criacoes > lim.get("max_registros_criados_por_plano", 10 ** 6) and self.p["aprovacao_exigida"].get("volume_acima_limite"):
            motivos.append(f"volume de criação acima do limite ({criacoes})")
        for a in acoes_operacao:
            if a.get("efeito") == "consome" and self.p["aprovacao_exigida"].get("remocao"):
                motivos.append(f"operação que consome registro: {a['interface']} (cenário {a['cenario']})")
        for rid, efeito in receitas_efeito.items():
            if efeito == "nao_aprovada" and self.p["aprovacao_exigida"].get("receita_nao_aprovada"):
                motivos.append(f"receita não aprovada: {rid}")
        return {"aprovacao_necessaria": bool(motivos), "motivos": motivos, "negadas": negadas}

    def _ambiente_ok(self) -> bool:
        a = self.ambiente.upper()
        return a not in AMBIENTES_PROIBIDOS and a in [x.upper() for x in self.p.get("ambientes_permitidos", [])]

    # ───────── ações em execução ─────────
    def autorizador(self, plano: Plano | None, exigir_plano: bool = True) -> Callable[[dict], None]:
        def autorizar(acao: dict) -> None:
            try:
                ok, motivo = self._avaliar_acao(acao, plano, exigir_plano)
            except Exception as e:  # noqa: BLE001 — falha fechada
                raise FalhaPolitica(f"Guardião falhou ao avaliar a ação (negada por segurança): {e}") from e
            if not ok:
                raise FalhaPolitica(motivo)
        return autorizar

    def _avaliar_acao(self, acao: dict, plano: Plano | None, exigir_plano: bool) -> tuple[bool, str]:
        if not self._ambiente_ok():
            return False, f"ambiente {self.ambiente} não permitido"
        if acao["tipo"] == "api":
            if not any(e["metodo"] == acao["metodo"] and re.fullmatch(e["padrao"], acao["caminho"])
                       for e in self.p.get("endpoints_permitidos", [])):
                return False, f"endpoint fora da política: {acao['metodo']} {acao['caminho']}"
            assinatura = f"api:{acao['interface']}"
        elif acao["tipo"] == "tela":
            assinatura = f"tela:{acao.get('interface', '*')}"
        else:
            return False, f"tipo de ação desconhecido: {acao['tipo']}"
        if exigir_plano:
            if plano is None:
                return False, "ação sem plano"
            if plano.aprovacao_necessaria and not plano.aprovado:
                return False, "plano exige aprovação e ainda não foi aprovado"
            if acao["tipo"] == "api" and assinatura not in plano.acoes_previstas:
                return False, f"ação fora do plano aprovado: {assinatura}"
        return True, ""

    # ───────── mascaramento ─────────
    def mascarar(self, obj: Any) -> Any:
        campos = set(self.p.get("campos_mascarar", []))

        def m(o: Any, chave: str | None = None) -> Any:
            if isinstance(o, dict):
                if "campo" in o and o.get("campo") in campos and "valor" in o:
                    return {**o, "valor": _mask(o["valor"])}
                return {k: m(v, k) for k, v in o.items()}
            if isinstance(o, list):
                return [m(x, chave) for x in o]
            if chave in campos and isinstance(o, (str, int)):
                return _mask(o)
            return o
        return m(obj)


def _mask(v: Any) -> str:
    s = str(v)
    return "*" * max(len(s) - 2, 0) + s[-2:]
