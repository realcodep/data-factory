"""Plano a seco: executa o plano SOMENTE com leituras e levanta todas as pendências antes de qualquer escrita."""
from __future__ import annotations

from massa.contratos import VARIACOES_INVALIDAS, Pendencia, Plano, Suite
from massa.guardiao import Guardiao
from massa.motor.contexto import Contexto, FalhaCaminho
from massa.motor.garimpo import garimpar
from massa.motor.montador import montar_payload
from massa.planejamento.planejador import efeito_operacao

PLACEHOLDER = {"chave": 0, "atributos": {"id_contrato_vigente": 0}}


def _pend(plano: Plano, **kw) -> Pendencia:
    p = Pendencia(id=f"PD-{len(plano.pendencias) + 1:02d}", **kw)
    plano.pendencias.append(p)
    return p


def simular(ctx: Contexto, plano: Plano, suite: Suite, guardiao: Guardiao) -> Plano:
    cat = ctx.catalogo
    plano.pendencias = []
    specs = {s.id: s for s in suite.cenarios}

    # F0 — termos do cenário contra o vocabulário fechado
    for s in suite.cenarios:
        if s.entidade not in cat.regras and not any(e.entidade == s.entidade for e in cat.estados.values()):
            _pend(plano, tipo="termo_desconhecido", assinatura=f"entidade:{s.entidade}", cenarios=[s.id],
                  duvida=f"Entidade '{s.entidade}' não existe no catálogo", afeta_resultado=True, reversivel=True)
            continue
        if s.operacao != "consulta" and cat.receita_da_operacao(s.entidade, s.operacao) is None:
            _pend(plano, tipo="lacuna_catalogo", assinatura=f"operacao:{s.entidade}:{s.operacao}", cenarios=[s.id],
                  duvida=f"Operação '{s.operacao}' de {s.entidade} não tem receita/interface no catálogo",
                  afeta_resultado=True)
        for pre in s.precondicoes:
            if pre.estado not in cat.estados:
                _pend(plano, tipo="termo_desconhecido", assinatura=f"estado:{pre.estado}", cenarios=[s.id],
                      duvida=f"Estado '{pre.estado}' não existe no catálogo", afeta_resultado=True,
                      opcoes=[e for e in cat.estados if e.startswith(pre.estado.split(".")[0])])
        campos = set(cat.regras.get(s.entidade, {}))
        for campo in [v.campo for v in s.variacoes] + list(s.entradas):
            if campo not in campos:
                _pend(plano, tipo="termo_desconhecido", assinatura=f"campo:{s.entidade}:{campo}", cenarios=[s.id],
                      duvida=f"Campo '{campo}' não existe em {s.entidade}", opcoes=sorted(campos),
                      afeta_resultado=True)
        # conflito funcional × técnico em campo que o teste exercita
        for campo in {v.campo for v in s.variacoes} | set(s.entradas):
            regra = cat.regra(s.entidade, campo)
            if not regra or not regra.conflito:
                continue
            for c in regra.conflito["itens"]:
                valor = s.entradas.get(campo)
                variacao = next((v.regra for v in s.variacoes if v.campo == campo), None)
                ambiguo = (valor is not None and c["atributo"] == "dominio"
                           and (valor in c["tecnico"]) != (valor in c["funcional"]))
                ambiguo |= variacao in ("limite_inferior", "limite_superior", "abaixo_minimo", "acima_maximo") \
                    and c["atributo"] in ("minimo", "maximo")
                if ambiguo:
                    _pend(plano, tipo="conflito_regra",
                          assinatura=f"conflito:{s.entidade}:{campo}:{c['atributo']}:{valor or variacao}",
                          cenarios=[s.id],
                          duvida=(f"'{campo}'={valor!r}: o código aceita ({c['tecnico']}), o normativo não "
                                  f"({c['funcional']}). Qual comportamento o teste deve esperar?"),
                          opcoes=["seguir_normativo", "seguir_codigo"],
                          evidencias=c.get("evidencias_funcionais", []) + c.get("evidencias_tecnicas", [])[:3],
                          afeta_resultado=True, custo_cobrir_todas="alto", reversivel=True)
        # oráculo
        if s.modo_execucao in ("api", "tela"):
            if not s.resultado_esperado:
                _pend(plano, tipo="oraculo_sem_fonte", assinatura=f"oraculo:{s.entidade}:{s.operacao}:{s.tipo}:vazio",
                      cenarios=[s.id], duvida="Cenário executável sem resultado esperado", afeta_resultado=True,
                      opcoes=[f["id"] for f in cat.fatos_negocio.get(s.entidade, []) if f.get("operacao") == s.operacao])
            for esp in s.resultado_esperado:
                if esp.origem == "funcional" and not (esp.fonte and cat.fato(esp.fonte)):
                    _pend(plano, tipo="oraculo_sem_fonte", assinatura=f"fonte:{esp.fonte}", cenarios=[s.id],
                          duvida=f"Expectativa '{esp.descricao}' cita fonte funcional inexistente: {esp.fonte}",
                          afeta_resultado=True)
            if "oraculo_nao_independente" in s.avisos:
                _pend(plano, tipo="oraculo_sem_fonte",
                      assinatura=f"oraculo_tecnico:{s.entidade}:{s.operacao}:{s.tipo}", cenarios=[s.id],
                      duvida="Todas as expectativas vêm só do código (oráculo não independente)",
                      opcoes=[f["id"] for f in cat.fatos_negocio.get(s.entidade, []) if f.get("operacao") == s.operacao],
                      afeta_resultado=True)
        # F4 a seco: payload coerente com o tipo do cenário
        if s.modo_execucao != "somente_massa" and s.operacao != "consulta" and \
                cat.receita_da_operacao(s.entidade, s.operacao):
            try:
                papeis = {p: PLACEHOLDER for p in ["contrato"]}
                montar_payload(ctx, s, PLACEHOLDER, papeis, f"{plano.id}:seco:{s.id}")
            except FalhaCaminho as e:
                _pend(plano, tipo="especificacao_incoerente", assinatura=f"payload:{s.id}", cenarios=[s.id],
                      duvida=str(e), afeta_resultado=True)

    # F1/F2 a seco — estratégia de cada instância (garimpo sem reservar)
    usados: set[str] = set()
    for inst in plano.instancias:
        consumiveis = inst.uso == "consumivel"
        achados = garimpar(ctx, inst.estado, quantidade=1, uso=inst.uso, excluir=usados, telemetria=False)
        if achados:
            inst.estrategia = "garimpar"
            if consumiveis:
                usados.add(achados[0]["registro"])
        elif inst.caminho:
            inst.estrategia = "provisionar"
            for rid in inst.caminho:
                r = cat.receitas[rid]
                if not r.aprovada:
                    _pend(plano, tipo="receita_nao_aprovada", assinatura=f"receita:{rid}", cenarios=inst.cenarios,
                          duvida=f"Receita {rid} não está aprovada", afeta_resultado=False)
                if cat.saude.get(rid) == "quebrada":
                    _pend(plano, tipo="sem_caminho", assinatura=f"receita_quebrada:{rid}", cenarios=inst.cenarios,
                          duvida=f"Receita {rid} marcada como quebrada pelos canários", afeta_resultado=True)
        else:
            _pend(plano, tipo="sem_caminho", assinatura=f"sem_caminho:{inst.estado}", cenarios=inst.cenarios,
                  duvida=f"Nenhum registro em {inst.estado} e nenhuma receita leva até ele", afeta_resultado=True)

    # F3 só é necessária se alguma instância precisar provisionar (pode reaparecer na execução)
    if all(i.estrategia != "provisionar" for i in plano.instancias):
        for f in plano.fases:
            if f.id == "F3":
                f.passos = []

    # Guardião avalia o plano inteiro
    acoes_op = []
    for s in suite.cenarios:
        if s.modo_execucao in ("api", "tela") and efeito_operacao(cat, s) == "consome":
            r = cat.receita_da_operacao(s.entidade, s.operacao)
            acoes_op.append({"interface": r.passos[0].interface, "efeito": "consome", "cenario": s.id})
    nao_aprov = {rid: "nao_aprovada" for i in plano.instancias for rid in i.caminho if not cat.receitas[rid].aprovada}
    av = guardiao.avaliar_plano(plano, nao_aprov, acoes_op)
    plano.aprovacao_necessaria = av["aprovacao_necessaria"]
    if av["negadas"]:
        _pend(plano, tipo="falha_politica", assinatura="politica:ambiente", cenarios=list(specs),
              duvida="; ".join(av["negadas"]), afeta_resultado=True, reversivel=False)
    if av["aprovacao_necessaria"]:
        _pend(plano, tipo="aprovacao", assinatura=f"aprovacao:{plano.id}", cenarios=list(specs),
              duvida="O plano exige aprovação única: " + "; ".join(av["motivos"]), afeta_resultado=False,
              reversivel=False)
    return plano
