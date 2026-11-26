"""Provisionamento por receitas: leva uma entidade até o estado pedido pelas interfaces oficiais.

- caminho de menor custo no grafo do catálogo;
- dependências (`requer`) atendidas por garimpo compartilhável ou provisionamento recursivo;
- cada passo idempotente (chave plano + instância + receita + passo);
- valores de pré-condição sempre válidos (nunca grava valor inválido);
- espera a propagação do estado antes do próximo passo.
"""
from __future__ import annotations

import time
from typing import Any

from massa.contratos import Receita
from massa.motor.contexto import Contexto, FalhaCaminho, FalhaDado
from massa.motor.executor import chamar_api
from massa.motor.garimpo import garimpar, reconferir, registro_id
from massa.motor.gerador import gerar, rng, violacoes


def aguardar_estado(ctx: Contexto, estado_id: str, chave: Any, espera: bool = True) -> bool:
    estado = ctx.catalogo.estados[estado_id]
    limite = time.monotonic() + (estado.propagacao_max_s if espera else 0)
    while True:
        if reconferir(ctx, estado_id, chave):
            return True
        if time.monotonic() >= limite:
            return False
        time.sleep(0.2)


def _valor_ref(ref: str, instancia: dict, papeis: dict[str, dict]) -> Any:
    papel, attr = ref.split(".", 1)
    alvo = instancia if papel == "self" else papeis.get(papel)
    if alvo is None:
        raise FalhaCaminho(f"papel '{papel}' não disponível para a referência {ref}")
    if attr == "id":
        return alvo["chave"]
    if attr not in alvo.get("atributos", {}):
        raise FalhaCaminho(f"atributo '{attr}' do papel '{papel}' desconhecido")
    return alvo["atributos"][attr]


def obter_dependencia(ctx: Contexto, estado_id: str, plano_id: str, seed: int, papel: str) -> dict:
    """Dependência compartilhável (ex.: contrato ativo): garimpa e reserva; se não houver, provisiona."""
    for cand in garimpar(ctx, estado_id, quantidade=3, uso="compartilhavel", plano_id=plano_id):
        if ctx.reservas.reservar(cand["registro"], estado_id, plano_id, "compartilhavel"):
            return cand
    entidade = estado_id.split(".")[0]
    inst = {"id": f"dep-{papel}", "chave": None, "atributos": {}, "tabela": None, "estado": f"{entidade}.inexistente"}
    return provisionar(ctx, inst, estado_id, plano_id, seed, {})


def executar_receita(ctx: Contexto, receita: Receita, instancia: dict, plano_id: str, seed: int,
                     papeis: dict[str, dict], ultima: bool = True) -> dict:
    if not receita.aprovada:
        raise FalhaCaminho(f"receita {receita.id} não aprovada")
    for papel, estado_req in receita.requer.items():
        if papel not in papeis:
            papeis[papel] = obter_dependencia(ctx, estado_req, plano_id, seed, papel)
    reaproveitados = []
    for i, passo in enumerate(receita.passos):
        interface = ctx.catalogo.interfaces[passo.interface]
        chave = f"{plano_id}:{instancia['id']}:{receita.id}:{i}"
        valores = {}
        for campo in passo.campos_gerados:
            regra = ctx.catalogo.regra(receita.entidade, campo)
            if regra is None:
                raise FalhaCaminho(f"sem regra para {receita.entidade}.{campo}")
            v = gerar(regra, "valido", rng(seed, f"{chave}:{campo}"), ctx.data_base, destino="precondicao")
            if violacoes(regra, v.valor, usar_dominio_funcional=True):
                raise FalhaCaminho(f"valor de pré-condição inválido gerado para {campo}: recusado")
            valores[campo] = f"{v.valor:.{regra.decimais or 2}f}" if regra.tipo == "decimal" else v.valor
        params = {k: _valor_ref(ref, instancia, papeis) for k, ref in passo.parametros.items()}
        corpo_campos = {c.campo for c in interface.campos}
        body = {**{k: v for k, v in params.items() if k in corpo_campos}, **valores} if interface.metodo != "DELETE" else None
        resp = chamar_api(ctx, interface, params, body, plano_id, chave)
        reaproveitados.append(bool(resp.get("reaproveitado")))
        if passo.devolve:
            instancia["chave"] = resp["corpo"][passo.devolve]
        for attr, ref in passo.registra.items():
            instancia.setdefault("atributos", {})[attr] = _valor_ref(ref, instancia, papeis)
        instancia.setdefault("atributos", {}).update({k: v for k, v in valores.items()})
    tabela = ctx.catalogo.estados[receita.destino].predicado.tabela
    instancia["tabela"] = tabela
    instancia["registro"] = registro_id(tabela, instancia["chave"])
    replay = all(reaproveitados) and reaproveitados
    # Em retomada, passos já executados não são reconferidos no estado intermediário
    # (a entidade pode já ter avançado); só o destino final é verificado.
    if not (replay and not ultima) and not aguardar_estado(ctx, receita.destino, instancia["chave"]):
        raise FalhaDado(f"{instancia['registro']} não atingiu {receita.destino} no tempo de propagação")
    instancia["estado"] = receita.destino
    if receita.efeito == "cria":
        ctx.eventos.registrar("registro_criado", {"instancia": instancia["id"], "tabela": tabela,
                                                  "chave": instancia["chave"], "estado": receita.destino,
                                                  "receita": receita.id, "atributos": instancia.get("atributos", {})},
                              plano_id, chave=f"{plano_id}:{instancia['id']}:criado")
    return instancia


def provisionar(ctx: Contexto, instancia: dict, destino: str, plano_id: str, seed: int,
                papeis: dict[str, dict]) -> dict:
    """Leva `instancia` (que está em instancia['estado']) até `destino`."""
    origem = instancia.get("estado") or ctx.catalogo.inexistente(destino.split(".")[0])
    if origem == destino:
        return instancia
    rota = ctx.catalogo.caminho(origem, destino)
    if rota is None:
        raise FalhaCaminho(f"sem caminho de {origem} até {destino}")
    for i, receita in enumerate(rota):
        executar_receita(ctx, receita, instancia, plano_id, seed, papeis, ultima=i == len(rota) - 1)
    return instancia
