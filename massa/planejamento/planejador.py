"""Planejador de suíte (determinístico): mesma suíte + mesmo catálogo => mesmo plano.

- Infere o estado do alvo pela operação (origem da receita) quando o cenário não declara.
- Pré-condições compartilháveis iguais viram UMA instância usada por vários cenários.
- Pré-condições consumíveis (o alvo que será transformado/consumido) são uma por cenário.
- Ordena: leitura antes de transformação, transformação antes de consumo.
"""
from __future__ import annotations

import hashlib
import json

from massa.catalogo import Catalogo
from massa.contratos import EspecificacaoCenario, Fase, Instancia, Passo, Plano, Suite

ORDEM_EFEITO = {"leitura": 0, "cria": 1, "transforma": 2, "consome": 3}


def plano_id_para(suite: Suite, catalogo_hash: str) -> str:
    h = hashlib.sha256((json.dumps(suite.model_dump(), sort_keys=True, default=str) + catalogo_hash).encode())
    return f"PL-{h.hexdigest()[:10]}"


def efeito_operacao(cat: Catalogo, spec: EspecificacaoCenario) -> str:
    if spec.operacao == "consulta":
        return "leitura"
    r = cat.receita_da_operacao(spec.entidade, spec.operacao)
    return r.efeito if r else "transforma"


def papeis_do_cenario(cat: Catalogo, spec: EspecificacaoCenario) -> list[tuple[str, str, str]]:
    """Lista (papel, estado, uso) que o cenário precisa antes da operação."""
    out: list[tuple[str, str, str]] = []
    receita = cat.receita_da_operacao(spec.entidade, spec.operacao)
    explicitas = {(p.papel or ("alvo" if p.estado.startswith(spec.entidade + ".") else p.estado.split(":")[1].split(".")[0])): p
                  for p in spec.precondicoes}
    alvo = explicitas.pop("alvo", None)
    estado_alvo = alvo.estado if alvo else (receita.origem if receita else None)
    if estado_alvo and not estado_alvo.endswith(".inexistente"):
        uso = "compartilhavel" if spec.operacao == "consulta" else "consumivel"
        out.append(("alvo", estado_alvo, uso))
    for papel, estado_req in (receita.requer.items() if receita else []):
        if papel not in explicitas:
            out.append((papel, estado_req, "compartilhavel"))
    for papel, p in explicitas.items():
        out.append((papel, p.estado, p.uso))
    return out


def planejar(cat: Catalogo, suite: Suite) -> Plano:
    plano = Plano(id=plano_id_para(suite, cat.hash), suite_id=suite.id, catalogo_hash=cat.hash)
    compartilhadas: dict[str, Instancia] = {}
    vinculos: dict[str, dict[str, str]] = {}           # cenário -> papel -> instância
    for spec in suite.cenarios:
        vinculos[spec.id] = {}
        for papel, estado, uso in papeis_do_cenario(cat, spec):
            if uso == "compartilhavel":
                inst = compartilhadas.get(estado)
                if inst is None:
                    inst = Instancia(id=f"I-{len(plano.instancias) + 1:02d}", estado=estado, uso=uso, cenarios=[])
                    compartilhadas[estado] = inst
                    plano.instancias.append(inst)
                inst.cenarios.append(spec.id)
            else:
                inst = Instancia(id=f"I-{len(plano.instancias) + 1:02d}", estado=estado, uso=uso, cenarios=[spec.id])
                plano.instancias.append(inst)
            rota = cat.caminho(cat.inexistente(estado.split(".")[0]), estado)
            inst.caminho = [r.id for r in rota] if rota else []
            vinculos[spec.id][papel] = inst.id

    ordenados = sorted(suite.cenarios, key=lambda s: (ORDEM_EFEITO[efeito_operacao(cat, s)], s.id))
    modos = {s.modo_execucao for s in suite.cenarios}
    fases = [
        Fase(id="F0", nome="Entendimento", criterio_saida="Especificações válidas contra o vocabulário do catálogo",
             passos=[Passo(id=f"F0.validar.{s.id}", fase="F0", acao="validar", cenario=s.id) for s in suite.cenarios]),
        Fase(id="F1", nome="Estratégia", criterio_saida="Cada pré-condição com estratégia e caminho",
             passos=[Passo(id=f"F1.estrategia.{i.id}", fase="F1", acao="validar", instancia=i.id)
                     for i in plano.instancias]),
        Fase(id="F2", nome="Garimpo e reserva", criterio_saida="Reservas ativas com estado reconferido",
             risco="baixo", compensacao="liberar reservas do plano",
             passos=[Passo(id=f"F2.reservar.{i.id}", fase="F2", acao="reservar", instancia=i.id)
                     for i in plano.instancias]),
        Fase(id="F3", nome="Provisionamento", criterio_saida="Instâncias faltantes no estado-alvo, verificadas",
             risco="medio", compensacao="massa criada fica marcada no registro de eventos e expira com a reserva",
             passos=[Passo(id=f"F3.provisionar.{i.id}", fase="F3", acao="provisionar", instancia=i.id,
                           dados={"caminho": i.caminho}) for i in plano.instancias]),
    ]
    precisa_payload = [s for s in ordenados if s.modo_execucao in ("payload", "api", "tela")]
    executa = [s for s in ordenados if s.modo_execucao in ("api", "tela")]
    if precisa_payload:
        fases.append(Fase(id="F4", nome="Dados de entrada", criterio_saida="Payload/roteiro válidos contra o contrato",
                          passos=[Passo(id=f"F4.montar.{s.id}", fase="F4", acao="montar", cenario=s.id,
                                        dados={"papeis": vinculos[s.id]}) for s in precisa_payload]))
    if executa:
        fases.append(Fase(id="F5", nome="Execução", criterio_saida="Resposta e evidência registradas", risco="medio",
                          passos=[Passo(id=f"F5.executar.{s.id}", fase="F5", acao="executar", cenario=s.id,
                                        dados={"papeis": vinculos[s.id]}) for s in executa]))
    if any(s.resultado_esperado for s in executa):
        fases.append(Fase(id="F6", nome="Verificação", criterio_saida="Resultado confirmado ou divergência documentada",
                          passos=[Passo(id=f"F6.verificar.{s.id}", fase="F6", acao="verificar", cenario=s.id,
                                        dados={"papeis": vinculos[s.id]}) for s in executa if s.resultado_esperado]))
    fases.append(Fase(id="F7", nome="Entrega", criterio_saida="Pacote, relatório e cenários executáveis gerados",
                      passos=[Passo(id=f"F7.entregar.{s.id}", fase="F7", acao="entregar", cenario=s.id,
                                    dados={"papeis": vinculos[s.id]}) for s in ordenados]))
    plano.fases = fases

    acoes = set()
    for i in plano.instancias:
        for rid in i.caminho:
            for p in cat.receitas[rid].passos:
                acoes.add(f"api:{p.interface}")
            for estado_req in cat.receitas[rid].requer.values():
                rota = cat.caminho(cat.inexistente(estado_req.split(".")[0]), estado_req) or []
                acoes |= {f"api:{p.interface}" for r in rota for p in r.passos}
    for s in executa:
        r = cat.receita_da_operacao(s.entidade, s.operacao)
        if r:
            acoes.add(f"{'tela' if s.modo_execucao == 'tela' else 'api'}:{r.passos[0].interface}")
            if s.modo_execucao == "tela":
                acoes.add(f"api:{r.passos[0].interface}")
    plano.acoes_previstas = sorted(acoes)
    leitura = [s.id for s in ordenados if efeito_operacao(cat, s) == "leitura"]
    outros = [s.id for s in ordenados if s.id not in leitura]
    plano.paralelizavel = [g for g in (leitura, outros) if g]
    return plano
