"""Fachada do motor usada pelo servidor MCP e pela CLI. Toda saída passa pelo mascaramento do Guardião."""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from massa.contratos import Decisao, Degrau, EspecificacaoCenario, Plano, Suite
from massa.guardiao import Guardiao
from massa.motor.contexto import Contexto, FalhaCaminho
from massa.planejamento.condutor import AguardandoAprovacao, Condutor
from massa.planejamento.decisoes import aplicar_decisoes_registradas, pendentes, registrar, resolver
from massa.planejamento.planejador import planejar
from massa.planejamento.simulacao import simular


class Servico:
    def __init__(self, ctx: Contexto, guardiao: Guardiao | None = None):
        self.ctx = ctx
        self.g = guardiao or Guardiao(ambiente=ctx.ambiente)
        self.condutor = Condutor(ctx, self.g)
        self.ev = ctx.eventos

    def _out(self, obj: Any) -> Any:
        return self.g.mascarar(json.loads(json.dumps(obj, default=str)))

    def _plano(self, plano_id: str) -> tuple[Plano, Suite]:
        ck = self.ev.checkpoint(plano_id)
        if not ck["plano"]:
            raise FalhaCaminho(f"plano {plano_id} não encontrado")
        plano = Plano(**ck["plano"])
        plano.aprovado = ck["aprovado"]
        aplicar_decisoes_registradas(self.ev, plano)
        return plano, Suite(**ck["suite"])

    # ───────── catálogo ─────────
    def vocabulario(self) -> dict:
        p = self.ctx.catalogo.raiz / "dist" / "vocabulario.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def consultar_catalogo(self, entidade: str | None = None, estado: str | None = None) -> dict:
        cat = self.ctx.catalogo
        if estado:
            e = cat.estados.get(estado)
            return self._out({"estado": e.model_dump() if e else None,
                              "receitas_que_chegam": [r.id for r in cat.receitas.values() if r.destino == estado]})
        if entidade:
            return self._out({"regras": {c: {k: v for k, v in r.model_dump().items() if k != "fontes"}
                                         | {"fontes": [f.referencia for f in r.fontes]}
                                         for c, r in cat.regras.get(entidade, {}).items()},
                              "fatos_negocio": cat.fatos_negocio.get(entidade, []),
                              "conflitos": [c for c in cat.conflitos if c["entidade"] == entidade]})
        return {"entidades": sorted(cat.regras), "estados": sorted(cat.estados), "receitas": sorted(cat.receitas)}

    def validar_especificacao(self, especificacao: dict) -> dict:
        try:
            e = EspecificacaoCenario(**especificacao)
            return {"ok": True, "avisos": e.avisos}
        except ValidationError as ex:
            return {"ok": False, "erros": [er["msg"] for er in ex.errors()]}

    # ───────── plano ─────────
    def planejar_suite(self, suite: dict) -> dict:
        s = Suite(**suite)
        plano = planejar(self.ctx.catalogo, s)
        self.ev.registrar("plano_criado", {"plano": plano.model_dump(mode="json"), "suite": s.model_dump(mode="json")},
                          plano.id, chave=f"{plano.id}:criado")
        return self._out({"plano_id": plano.id, "instancias": [i.model_dump() for i in plano.instancias],
                          "fases": [{"id": f.id, "nome": f.nome, "passos": len(f.passos)} for f in plano.fases],
                          "paralelizavel": plano.paralelizavel})

    def simular_plano(self, plano_id: str) -> dict:
        plano, suite = self._plano(plano_id)
        simular(self.ctx, plano, suite, self.g)
        decididas = resolver(self.ev, plano, suite)
        aplicar_decisoes_registradas(self.ev, plano)
        self.ev.registrar("plano_simulado", {"plano": plano.model_dump(mode="json")}, plano_id)
        return self._out({"plano_id": plano_id, "aprovacao_necessaria": plano.aprovacao_necessaria,
                          "estrategias": {i.id: i.estrategia for i in plano.instancias},
                          "decididas_sem_ia": [d.model_dump(mode="json") for d in decididas],
                          "pendencias_para_qa_lead": [p.model_dump(mode="json") for p in pendentes(plano)]})

    def pendencias(self, plano_id: str) -> list[dict]:
        plano, _ = self._plano(plano_id)
        return self._out([p.model_dump(mode="json") for p in pendentes(plano)])

    def registrar_decisao(self, plano_id: str, pendencia_id: str, escolha: Any, degrau: str, justificativa: str,
                          evidencias: list[str] | None = None, confianca: float = 0.7, reversivel: bool = True) -> dict:
        plano, _ = self._plano(plano_id)
        p = next((x for x in plano.pendencias if x.id == pendencia_id), None)
        if p is None:
            raise FalhaCaminho(f"pendência {pendencia_id} não existe")
        if degrau in ("fato", "convencao", "precedente"):
            raise FalhaCaminho("degraus 1–3 são resolvidos pelo motor; o agente decide a partir de 'premissa'")
        d = Decisao(pendencia_id=p.id, assinatura=p.assinatura, duvida=p.duvida, degrau=Degrau(degrau), escolha=escolha,
                    alternativas=p.opcoes, justificativa=justificativa, evidencias=evidencias or [],
                    confianca=confianca, reversivel=reversivel)
        registrar(self.ev, plano_id, d)
        return {"ok": True, "pendencia_id": p.id, "degrau": degrau}

    def registrar_perguntas(self, plano_id: str, perguntas: list[dict]) -> dict:
        for q in perguntas:
            self.ev.registrar("pergunta_feita", q, plano_id)
        return {"ok": True, "perguntas": len(perguntas)}

    def solicitar_aprovacao(self, plano_id: str) -> dict:
        plano, _ = self._plano(plano_id)
        motivos = [p.duvida for p in plano.pendencias if p.tipo == "aprovacao"]
        return {"plano_id": plano_id, "aprovacao_necessaria": plano.aprovacao_necessaria, "motivos": motivos,
                "acoes_previstas": plano.acoes_previstas}

    def aprovar_plano(self, plano_id: str, aprovador: str) -> dict:
        self.ev.registrar("plano_aprovado", {"aprovador": aprovador}, plano_id, chave=f"{plano_id}:aprovado")
        return {"ok": True}

    def executar_plano(self, plano_id: str) -> dict:
        try:
            return self._out(self.condutor.executar(plano_id))
        except AguardandoAprovacao as e:
            return {"status": "aguardando_aprovacao", "mensagem": str(e)}

    def retomar_plano(self, plano_id: str) -> dict:
        return self.executar_plano(plano_id)

    def status_plano(self, plano_id: str) -> dict:
        return self._out(self.condutor.status(plano_id))

    def relatorio(self, plano_id: str) -> dict:
        p = self.ctx.saida / "planos" / plano_id / "relatorio.json"
        if not p.exists():
            return {"status": "plano ainda não concluído", **self.status_plano(plano_id)}
        return self._out(json.loads(p.read_text(encoding="utf-8")))

    def liberar_reservas(self, plano_id: str) -> dict:
        return {"liberadas": self.ctx.reservas.liberar(plano_id, motivo="liberacao_explicita")}
