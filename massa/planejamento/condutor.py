"""Condutor de fases: máquina de estados determinística, com checkpoint por passo e retomada.

Para cada fase: executar passos -> validar critério de saída -> gravar checkpoint -> avançar sozinho.
Falhas: transitória (o executor já tentou de novo) | dado (regarimpar/reprovisionar) |
        caminho e política (viram pendência para o QA Lead, sem parar os ramos independentes).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from massa.contratos import EspecificacaoCenario, Plano, ResultadoEsperado, Suite
from massa.guardiao import Guardiao
from massa.motor.contexto import Contexto, FalhaCaminho, FalhaDado, FalhaMotor, FalhaPolitica, FalhaTransitoria
from massa.motor.epoca import verificar_epoca
from massa.motor.executor import chamar_api, executar_roteiro
from massa.motor.garimpo import garimpar, reconferir, registro_id
from massa.motor.montador import montar_payload, montar_roteiro_tela, pacote_massa, salvar_json
from massa.motor.provisionador import provisionar
from massa.motor.verificador import verificar
from massa.planejamento.decisoes import aplicar_decisoes_registradas, cenarios_bloqueados


class Interrompido(RuntimeError):
    """Usado para simular queda de sessão no meio da execução."""


class AguardandoAprovacao(RuntimeError):
    pass


def spec_efetiva(spec: EspecificacaoCenario, plano: Plano) -> EspecificacaoCenario:
    """Aplica ao cenário as decisões que acrescentam expectativas (convenção, premissa, resposta humana)."""
    extras = []
    for p in plano.pendencias:
        if spec.id in p.cenarios and p.decisao and isinstance(p.decisao.escolha, dict) and "verificacao" in p.decisao.escolha:
            origem = "funcional" if p.decisao.escolha.get("fonte") else "premissa"
            extras.append(ResultadoEsperado(descricao=p.decisao.escolha.get("descricao", p.duvida),
                                            verificacao=p.decisao.escolha["verificacao"], origem=origem,
                                            fonte=p.decisao.escolha.get("fonte") or f"decisao:{p.id}"))
    if not extras:
        return spec
    return spec.model_copy(update={"resultado_esperado": [*spec.resultado_esperado, *extras]})


class Condutor:
    def __init__(self, ctx: Contexto, guardiao: Guardiao):
        self.ctx = ctx
        self.g = guardiao
        self.ev = ctx.eventos

    # ───────── carga de estado ─────────
    def _carregar(self, plano_id: str) -> tuple[Plano, Suite, dict]:
        ck = self.ev.checkpoint(plano_id)
        if not ck["plano"]:
            raise FalhaCaminho(f"plano {plano_id} não encontrado")
        plano = Plano(**ck["plano"])
        plano.aprovado = ck["aprovado"]
        aplicar_decisoes_registradas(self.ev, plano)
        return plano, Suite(**ck["suite"]), ck

    def _saida(self, plano_id: str, cenario: str | None = None) -> Path:
        d = self.ctx.saida / "planos" / plano_id
        return d / cenario if cenario else d

    # ───────── execução ─────────
    def executar(self, plano_id: str, interromper_apos: str | None = None) -> dict[str, Any]:
        plano, suite, ck = self._carregar(plano_id)
        if ck["concluido"]:
            return self.status(plano_id)
        if plano.aprovacao_necessaria and not plano.aprovado:
            raise AguardandoAprovacao("O plano exige aprovação única antes da execução.")
        if verificar_epoca(self.ctx) and ck["passos_concluidos"]:
            self.ev.registrar("plano_replanejado", {"plano": plano.model_dump(mode="json"), "fases_validas": ["F0", "F1"],
                                                    "motivo": "ambiente recarregado"}, plano_id)
            plano, suite, ck = self._carregar(plano_id)
        self.ctx.autorizar = self.g.autorizador(plano)
        specs = {s.id: spec_efetiva(s, plano) for s in suite.cenarios}
        bloqueados = cenarios_bloqueados(plano)
        feitos: dict[str, Any] = dict(ck["passos_concluidos"])
        insts: dict[str, dict] = {}
        self._revalidar(plano, feitos, insts)
        falhas: dict[str, str] = {}
        seed = suite.cenarios[0].seed if suite.cenarios else 42

        for fase in plano.fases:
            self.ev.registrar("fase_iniciada", {"fase": fase.id}, plano_id, chave=f"{plano_id}:{fase.id}:iniciada:v{plano.versao}")
            for passo in fase.passos:
                cenarios_passo = [passo.cenario] if passo.cenario else next(
                    (i.cenarios for i in plano.instancias if i.id == passo.instancia), [])
                if all(c in bloqueados or c in falhas for c in cenarios_passo):
                    continue
                if passo.id in feitos:
                    continue
                resultado = self._executar_passo(plano, specs, passo, insts, feitos, seed, fase.tentativas,
                                                 falhas, cenarios_passo)
                if resultado is not None:
                    feitos[passo.id] = resultado
                    self.ev.registrar("passo_concluido", {"passo": passo.id, "resultado": resultado}, plano_id)
                if interromper_apos == passo.id:
                    raise Interrompido(f"interrompido após {passo.id}")
            self.ev.registrar("fase_concluida", {"fase": fase.id, "falhas": falhas}, plano_id,
                              chave=f"{plano_id}:{fase.id}:concluida:v{plano.versao}:{len(feitos)}")
        rel = self.relatorio(plano_id, plano, suite, feitos, bloqueados, falhas)
        salvar_json(self._saida(plano_id) / "relatorio.json", rel)
        self.ev.registrar("plano_concluido", {"cenarios_ok": rel["resumo"]["ok"], "parciais": rel["resumo"]["bloqueados"]},
                          plano_id, chave=f"{plano_id}:concluido")
        return rel

    def _revalidar(self, plano: Plano, feitos: dict, insts: dict) -> None:
        """Retomada: reconstrói instâncias e descarta as que perderam reserva ou estado."""
        ativas = {r["registro"] for r in self.ctx.reservas.ativas() if r["plano_id"] == plano.id}
        for inst in plano.instancias:
            res = feitos.get(f"F3.provisionar.{inst.id}") or feitos.get(f"F2.reservar.{inst.id}")
            if not res or not res.get("chave"):
                continue
            ok = res["registro"] in ativas and reconferir(self.ctx, inst.estado, res["chave"])
            if ok or self._ja_executado(plano, inst):
                insts[inst.id] = res
            else:
                feitos.pop(f"F2.reservar.{inst.id}", None)
                feitos.pop(f"F3.provisionar.{inst.id}", None)

    def _ja_executado(self, plano: Plano, inst) -> bool:
        """Se a operação do cenário já rodou, a instância mudou de estado de propósito — não é perda."""
        return any(f"F5.executar.{c}" in self.ev.checkpoint(plano.id)["passos_concluidos"] for c in inst.cenarios)

    def _executar_passo(self, plano, specs, passo, insts, feitos, seed, tentativas, falhas, cenarios_passo):
        for tentativa in range(1, tentativas + 1):
            try:
                return self._passo(plano, specs, passo, insts, feitos, seed)
            except FalhaDado as e:
                if passo.instancia:
                    feitos.pop(f"F2.reservar.{passo.instancia}", None)
                    insts.pop(passo.instancia, None)
                if tentativa == tentativas:
                    self._falhar(plano, passo, e, falhas, cenarios_passo)
            except (FalhaCaminho, FalhaPolitica, FalhaTransitoria) as e:
                self._falhar(plano, passo, e, falhas, cenarios_passo)
                return None
        return None

    def _falhar(self, plano, passo, e: FalhaMotor, falhas, cenarios):
        for c in cenarios:
            falhas[c] = f"{e.classe}: {e}"
        self.ev.registrar("falha_registrada", {"passo": passo.id, "classe": e.classe, "erro": str(e),
                                               "cenarios": cenarios,
                                               "pendencia": {"tipo": f"falha_{'politica' if e.classe == 'politica' else 'caminho'}",
                                                             "duvida": str(e)} if e.classe in ("caminho", "politica") else None},
                          plano.id)

    def _papeis(self, passo) -> dict[str, dict]:
        return passo.dados.get("papeis", {})

    def _passo(self, plano: Plano, specs, passo, insts: dict, feitos: dict, seed: int) -> Any:
        ctx = self.ctx
        inst_def = next((i for i in plano.instancias if i.id == passo.instancia), None)
        if passo.acao == "validar":
            if passo.cenario:
                EspecificacaoCenario.model_validate(specs[passo.cenario].model_dump())
                return {"ok": True}
            return {"estrategia": inst_def.estrategia, "caminho": inst_def.caminho}
        if passo.acao == "reservar":
            usados = {v["registro"] for k, v in insts.items() if v.get("registro")}
            for cand in garimpar(ctx, inst_def.estado, quantidade=5, uso=inst_def.uso, excluir=usados, plano_id=plano.id):
                if reconferir(ctx, inst_def.estado, cand["chave"]) and \
                        ctx.reservas.reservar(cand["registro"], inst_def.estado, plano.id, inst_def.uso,
                                              ",".join(inst_def.cenarios)):
                    res = {**cand, "id": inst_def.id, "origem": "garimpo", "uso": inst_def.uso}
                    insts[inst_def.id] = res
                    return res
            return {"provisionar": True}
        if passo.acao == "provisionar":
            if inst_def.id in insts:
                return insts[inst_def.id]
            base = {"id": inst_def.id, "estado": ctx.catalogo.inexistente(inst_def.estado.split(".")[0]),
                    "chave": None, "atributos": {}}
            inst = provisionar(ctx, base, inst_def.estado, plano.id, seed, {})
            ctx.reservas.reservar(inst["registro"], inst_def.estado, plano.id, inst_def.uso, ",".join(inst_def.cenarios))
            res = {"id": inst_def.id, "registro": inst["registro"], "tabela": inst["tabela"], "chave": inst["chave"],
                   "estado": inst["estado"], "atributos": inst.get("atributos", {}), "origem": "provisionado",
                   "uso": inst_def.uso}
            insts[inst_def.id] = res
            return res
        spec = specs[passo.cenario]
        papeis = {p: insts[i] for p, i in self._papeis(passo).items() if i in insts}
        faltando = [p for p, i in self._papeis(passo).items() if i not in insts]
        if faltando:
            raise FalhaDado(f"papéis sem massa: {faltando}")
        destino = self._saida(plano.id, spec.id)
        if passo.acao == "montar":
            payload = montar_payload(ctx, spec, papeis.get("alvo"), papeis, f"{plano.id}:{spec.id}")
            out = {"payload": payload}
            if spec.modo_execucao == "tela":
                out["roteiro"] = str(montar_roteiro_tela(ctx, spec, payload, destino))
            salvar_json(destino / "pacote_massa.json", pacote_massa(spec, papeis, payload))
            return out
        if passo.acao == "executar":
            montado = feitos.get(f"F4.montar.{spec.id}")
            if spec.modo_execucao == "tela":
                return executar_roteiro(ctx, Path(montado["roteiro"]), plano.id, f"{plano.id}:{spec.id}:executar")
            pl = montado["payload"]
            interface = ctx.catalogo.interfaces[pl["interface"]]
            resp = chamar_api(ctx, interface, pl["params"], pl["body"], plano.id, f"{plano.id}:{spec.id}:executar",
                              esperar_sucesso=False)
            self._registrar_criacao(plano, spec, resp)
            return resp
        if passo.acao == "verificar":
            resp = feitos.get(f"F5.executar.{spec.id}")
            criado = self._criado_pela_operacao(spec, resp)
            if criado is not None and "alvo" not in papeis:
                papeis["alvo"] = {"chave": criado}
            return verificar(ctx, spec, resp, papeis, plano.id)
        if passo.acao == "entregar":
            exe = feitos.get(f"F5.executar.{spec.id}")
            pacote = {**pacote_massa(spec, papeis, (feitos.get(f"F4.montar.{spec.id}") or {}).get("payload")),
                      "resposta": exe, "verificacao": feitos.get(f"F6.verificar.{spec.id}")}
            salvar_json(destino / "pacote_massa.json", pacote)
            exportar_cenario_executavel(ctx, spec, plano)
            return {"entregue": str(destino)}
        raise FalhaCaminho(f"ação desconhecida: {passo.acao}")

    def _criado_pela_operacao(self, spec, resp) -> Any:
        receita = self.ctx.catalogo.receita_da_operacao(spec.entidade, spec.operacao)
        if not resp or not receita or receita.efeito != "cria" or not receita.passos[0].devolve:
            return None
        corpo = resp.get("corpo") or {}
        return corpo.get(receita.passos[0].devolve) if 200 <= resp.get("status", 0) < 300 else None

    def _registrar_criacao(self, plano, spec, resp) -> None:
        chave = self._criado_pela_operacao(spec, resp)
        if chave is None:
            return
        receita = self.ctx.catalogo.receita_da_operacao(spec.entidade, spec.operacao)
        tabela = self.ctx.catalogo.estados[receita.destino].predicado.tabela
        self.ev.registrar("registro_criado", {"instancia": f"op:{spec.id}", "tabela": tabela, "chave": chave,
                                              "estado": receita.destino, "receita": f"operacao:{receita.id}"},
                          plano.id, chave=f"{plano.id}:{spec.id}:op_criado")

    # ───────── consultas ─────────
    def status(self, plano_id: str) -> dict:
        ck = self.ev.checkpoint(plano_id)
        return {"plano_id": plano_id, "aprovado": ck["aprovado"], "concluido": ck["concluido"],
                "fases_concluidas": sorted(set(ck["fases_concluidas"])), "passos_concluidos": len(ck["passos_concluidos"]),
                "reservas": list(ck["reservas"]), "falhas": ck["falhas"]}

    def relatorio(self, plano_id, plano: Plano, suite: Suite, feitos: dict, bloqueados: set, falhas: dict) -> dict:
        cenarios = []
        for s in suite.cenarios:
            ver = feitos.get(f"F6.verificar.{s.id}")
            exe = feitos.get(f"F5.executar.{s.id}")
            if s.id in bloqueados:
                status = "bloqueado"
            elif s.id in falhas:
                status = "falhou"
            elif ver is not None:
                status = "ok" if ver["ok"] else "divergencia"
            else:
                status = "massa_entregue" if f"F7.entregar.{s.id}" in feitos else "pendente"
            cenarios.append({"id": s.id, "titulo": s.titulo, "status": status, "modo": s.modo_execucao,
                             "resposta": exe and {"status": exe.get("status")}, "verificacao": ver,
                             "falha": falhas.get(s.id),
                             "alertas": (["oraculo_nao_independente"] if "oraculo_nao_independente" in s.avisos else [])})
        decisoes = [p.decisao.model_dump(mode="json") for p in plano.pendencias if p.decisao]
        abertas = [p.model_dump(mode="json") for p in plano.pendencias if p.decisao is None and p.tipo != "aprovacao"]
        massa = [{"instancia": i.id, "estado": i.estado, "uso": i.uso, "cenarios": i.cenarios,
                  **{k: v for k, v in (feitos.get(f"F3.provisionar.{i.id}") or feitos.get(f"F2.reservar.{i.id}") or {}).items()
                     if k in ("registro", "origem")}} for i in plano.instancias]
        resumo = {"cenarios": len(cenarios), "ok": sum(c["status"] in ("ok", "massa_entregue") for c in cenarios),
                  "divergencias": sum(c["status"] == "divergencia" for c in cenarios),
                  "bloqueados": sum(c["status"] == "bloqueado" for c in cenarios),
                  "falhas": sum(c["status"] == "falhou" for c in cenarios),
                  "garimpadas": sum(m.get("origem") == "garimpo" for m in massa),
                  "provisionadas": sum(m.get("origem") == "provisionado" for m in massa)}
        return {"plano_id": plano_id, "suite": suite.id, "catalogo": plano.catalogo_hash, "resumo": resumo,
                "cenarios": cenarios, "massa": massa, "decisoes": decisoes, "pendencias_abertas": abertas}


def exportar_cenario_executavel(ctx: Contexto, spec: EspecificacaoCenario, plano: Plano) -> Path:
    """Cenário executável: especificação + modelo de plano. Reexecutar gera massa NOVA (nunca reaproveita IDs)."""
    d = ctx.saida / "cenarios" / spec.id
    salvar_json(d / "especificacao.json", spec.model_dump(mode="json"))
    modelo = {"catalogo": plano.catalogo_hash, "fases": [f.id for f in plano.fases],
              "instancias": [{"estado": i.estado, "uso": i.uso} for i in plano.instancias if spec.id in i.cenarios]}
    salvar_json(d / "plano_modelo.json", modelo)
    (d / "LEIA-ME.md").write_text(
        f"# Cenário executável {spec.id}\n\n{spec.titulo}\n\nReexecute com:\n\n"
        f"```\npython -m massa.cli rodar {d}\n```\n\nCada execução garimpa ou provisiona massa nova.\n", encoding="utf-8")
    return d
