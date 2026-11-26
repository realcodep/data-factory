"""QA Lead SIMULADO (stub determinístico) para a suíte de aceitação em CI.

Reproduz as decisões que o agente QA Lead deve tomar segundo a skill `resolver-pendencias`.
Não substitui o agente real: serve para provar o fluxo ponta a ponta sem depender de LLM.
"""
from __future__ import annotations

ENT = "garantias:garantia_imobiliaria"

INTERPRETACOES = {
    "CT-06": [{
        "id": "CT-06", "titulo": "Inclusão com valor de avaliação abaixo do mínimo",
        "operacao": "inclusao", "entidade": ENT, "tipo": "negativo",
        "variacoes": [{"campo": "valor_avaliacao", "regra": "abaixo_minimo"}],
        "resultado_esperado": [{"descricao": "Inclusão rejeitada", "verificacao": {"rejeitado": True},
                                "origem": "funcional", "fonte": "FN-GAR-005"}]}],
    "CT-07": [  # duas leituras de "motivo inválido"
        {"id": "CT-07a", "titulo": "Bloqueio com motivo fora do domínio", "operacao": "bloqueio", "entidade": ENT,
         "tipo": "negativo", "variacoes": [{"campo": "motivo_bloqueio", "regra": "fora_dominio"}],
         "resultado_esperado": [{"descricao": "Bloqueio rejeitado", "verificacao": {"rejeitado": True},
                                 "origem": "funcional", "fonte": "FN-GAR-002"}]},
        {"id": "CT-07b", "titulo": "Bloqueio sem motivo", "operacao": "bloqueio", "entidade": ENT,
         "tipo": "negativo", "variacoes": [{"campo": "motivo_bloqueio", "regra": "vazio"}],
         "resultado_esperado": [{"descricao": "Bloqueio rejeitado", "verificacao": {"rejeitado": True},
                                 "origem": "funcional", "fonte": "FN-GAR-002"}]}],
    "CT-08": [{
        "id": "CT-08", "titulo": "Bloqueio com motivo FRA", "operacao": "bloqueio", "entidade": ENT,
        "tipo": "positivo", "entradas": {"motivo_bloqueio": "FRA"},
        "resultado_esperado": [{"descricao": "Bloqueio aceito", "verificacao": {"aceito": True}, "origem": "tecnica",
                                "fonte": "demo/fontes/BloqueioRequest.java:9"}]}],
}


def interpretar(entrada: dict) -> list[dict]:
    if "especificacao" in entrada:
        return [{"id": entrada["id"], **entrada["especificacao"]}]
    return INTERPRETACOES[entrada["id"]]


def decisoes_de_interpretacao() -> list[dict]:
    return [{"cenarios": ["CT-07a", "CT-07b"], "duvida": "motivo inválido = fora do domínio ou vazio?",
             "escolha": "gerar as duas variações", "degrau": "duas_leituras",
             "justificativa": "Cobrir as duas leituras é barato e não exige pergunta."}]


def decidir(pendencias: list[dict]) -> tuple[list[dict], list[dict]]:
    """Devolve (decisões tomadas sem perguntar, perguntas ao humano — agrupadas por cenário)."""
    decisoes, perguntas_por_cenario = [], {}
    for p in pendencias:
        impossivel = p["afeta_resultado"] and p["custo_cobrir_todas"] == "alto" and \
            p["tipo"] in ("conflito_regra", "oraculo_sem_fonte")
        if impossivel:
            chave = ",".join(p["cenarios"])
            q = perguntas_por_cenario.setdefault(chave, {
                "cenarios": p["cenarios"], "pendencias": [], "pergunta": "",
                "opcoes": ["seguir_normativo", "seguir_codigo"], "recomendacao": "seguir_normativo",
                "sem_resposta": "aplicar a recomendação (reversível)"})
            q["pendencias"].append(p["id"])
            q["pergunta"] += p["duvida"] + " "
        else:
            decisoes.append({"pendencia_id": p["id"], "escolha": "premissa_padrao", "degrau": "premissa",
                             "justificativa": "Leitura mais provável, reversível."})
    return decisoes, list(perguntas_por_cenario.values())


def resposta_humana(pergunta: dict, pendencias: dict[str, dict]) -> list[dict]:
    """Resposta simulada do humano: seguir o normativo (a recomendação)."""
    out = []
    for pid in pergunta["pendencias"]:
        p = pendencias[pid]
        escolha = "seguir_normativo"
        if p["tipo"] == "oraculo_sem_fonte":
            escolha = {"verificacao": {"rejeitado": True}, "fonte": "FN-GAR-002", "substituir": True,
                       "descricao": "Normativo: FRA não é motivo de bloqueio previsto — deve ser rejeitado"}
        out.append({"pendencia_id": pid, "escolha": escolha, "degrau": "humano",
                    "justificativa": "Resposta do usuário: seguir o normativo NG-IMO-01 §5.1."})
    return out
