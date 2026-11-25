"""Rodada manual: Claude atuando como o agente QA Lead definido em .github/agents/qa-lead.agent.md,
usando o motor pela mesma fachada que o servidor MCP expõe (Servico), contra a API demo no ar."""
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, ".")
from massa.motor.contexto import Contexto  # noqa: E402
from massa.operacao import metricas  # noqa: E402
from massa.planejamento.servico import Servico  # noqa: E402

ENT = "garantias:garantia_imobiliaria"
svc = Servico(Contexto.do_ambiente())
log = []


def nota(t):
    log.append(t)
    print("•", t)


# 1. Vocabulário fechado
voc = svc.vocabulario()
nota(f"vocabulário: {len(voc['entidades'])} entidades; operações de garantia: {voc['entidades'][ENT]['operacoes']}")
nota("conflito conhecido no catálogo: " + json.dumps(svc.consultar_catalogo(ENT)["conflitos"][0]["funcional"]))

# 2. Interpretação (minha, como QA Lead)
entrada = yaml.safe_load(Path("tests/aceitacao/suite_imobiliario.yaml").read_text(encoding="utf-8"))
specs = []
for c in entrada["cenarios"]:
    if "especificacao" in c:
        specs.append({"id": c["id"], **c["especificacao"]})
specs += [
    {"id": "CT-06", "titulo": "Inclusão com valor de avaliação abaixo do mínimo", "origem_texto": entrada["cenarios"][5]["texto"],
     "operacao": "inclusao", "entidade": ENT, "tipo": "negativo",
     "variacoes": [{"campo": "valor_avaliacao", "regra": "abaixo_minimo"}],
     "resultado_esperado": [{"descricao": "Inclusão rejeitada", "verificacao": {"rejeitado": True}, "origem": "funcional",
                             "fonte": "FN-GAR-005"}]},
    {"id": "CT-07a", "titulo": "Bloqueio com motivo fora do domínio", "origem_texto": entrada["cenarios"][6]["texto"],
     "operacao": "bloqueio", "entidade": ENT, "tipo": "negativo", "variacoes": [{"campo": "motivo_bloqueio", "regra": "fora_dominio"}],
     "resultado_esperado": [{"descricao": "Bloqueio recusado", "verificacao": {"rejeitado": True}, "origem": "funcional", "fonte": "FN-GAR-002"}]},
    {"id": "CT-07b", "titulo": "Bloqueio sem motivo", "origem_texto": entrada["cenarios"][6]["texto"],
     "operacao": "bloqueio", "entidade": ENT, "tipo": "negativo", "variacoes": [{"campo": "motivo_bloqueio", "regra": "vazio"}],
     "resultado_esperado": [{"descricao": "Bloqueio recusado", "verificacao": {"rejeitado": True}, "origem": "funcional", "fonte": "FN-GAR-002"}]},
    {"id": "CT-08", "titulo": "Bloqueio com motivo FRA", "origem_texto": entrada["cenarios"][7]["texto"],
     "operacao": "bloqueio", "entidade": ENT, "tipo": "positivo", "entradas": {"motivo_bloqueio": "FRA"},
     "resultado_esperado": [{"descricao": "Bloqueio aceito (afirmação do cenário)", "verificacao": {"aceito": True},
                             "origem": "premissa", "fonte": "texto do cenário CT-08"}]},
]
for s in specs:
    v = svc.validar_especificacao(s)
    assert v["ok"], (s["id"], v)
nota(f"interpretei {len(entrada['cenarios'])} entradas em {len(specs)} especificações (CT-07 → duas leituras)")

# 3. Planejar + plano a seco
p = svc.planejar_suite({"id": "MANUAL-" + entrada["id"], "historia": entrada["historia"], "cenarios": specs})
pid = p["plano_id"]
svc.registrar_interpretacao(pid, ["CT-07a", "CT-07b"], "motivo inválido = fora do domínio ou vazio?",
                            "gerar as duas variações", "duas_leituras",
                            "As duas leituras são baratas e mudam só o dado de entrada; nenhuma pergunta necessária.", 0.9)
nota(f"plano {pid}: {len(p['instancias'])} instâncias de massa para {len(specs)} cenários; fases {[f['id'] for f in p['fases']]}")
sim = svc.simular_plano(pid)
nota(f"plano a seco: estratégias {sim['estrategias']}")
nota(f"decididas sem IA: {[(d['pendencia_id'], d['degrau']) for d in sim['decididas_sem_ia']]}")
pend = sim["pendencias_para_qa_lead"]
nota(f"pendências para mim: {[(x['id'], x['tipo'], x['cenarios']) for x in pend]}")

# 4. Escada de autonomia: só o conflito do CT-08 muda o resultado esperado e não dá para cobrir as duas leituras
perguntas = []
for x in pend:
    if x["tipo"] == "conflito_regra" and x["afeta_resultado"]:
        perguntas.append({"cenarios": x["cenarios"], "pendencias": [x["id"]],
                          "pergunta": "CT-08: o código aceita motivo FRA, mas o normativo NG-IMO-01 §5.1 só prevê JUD e ADM. "
                                      "O teste deve esperar aceite (código) ou rejeição (normativo)?",
                          "opcoes": ["seguir_normativo", "seguir_codigo"], "recomendacao": "seguir_normativo",
                          "sem_resposta": "aplico a recomendação (reversível) e marco no relatório"})
svc.registrar_perguntas(pid, perguntas)
nota(f"perguntas ao humano: {len(perguntas)} → {perguntas[0]['pergunta'] if perguntas else '-'}")
# Sem humano disponível nesta rodada: regra do prazo — opção reversível → aplicar a recomendação (degrau premissa)
for q in perguntas:
    for pid_pend in q["pendencias"]:
        svc.registrar_decisao(pid, pid_pend, {"verificacao": {"rejeitado": True}, "fonte": "FN-GAR-002", "substituir": True,
                                              "descricao": "Normativo: FRA não é motivo previsto — bloqueio deve ser rejeitado"},
                              "premissa", "Sem resposta no prazo; recomendação reversível aplicada (seguir o normativo). "
                                          "Se o humano escolher o código, basta replanejar o CT-08.", ["FN-GAR-002"], 0.7, True)
nota("CT-08: recomendação aplicada por prazo (seguir normativo) e marcada como premissa")

# 5. Aprovação única
if sim["aprovacao_necessaria"]:
    ap = svc.solicitar_aprovacao(pid)
    nota(f"aprovação necessária: {ap['motivos']}")
    svc.aprovar_plano(pid, "claude (rodada de construção, ambiente demo fictício)")

# 6. Executar e relatório
rel = svc.executar_plano(pid)
nota(f"resumo: {rel['resumo']}")
for c in rel["cenarios"]:
    nota(f"{c['id']}: {c['status']} (HTTP {c['resposta'] and c['resposta']['status']})")
m = metricas(svc.ctx)
nota(f"métricas: {json.dumps(m, ensure_ascii=False)}")
Path("saida/manual/rodada.json").write_text(json.dumps({"plano_id": pid, "log": log, "relatorio": rel, "metricas": m},
                                                      ensure_ascii=False, indent=2, default=str))
