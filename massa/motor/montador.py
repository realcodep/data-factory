"""Montador: payload da operação testada, roteiro de tela e pacote de massa."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from massa.contratos import VARIACOES_INVALIDAS, EspecificacaoCenario
from massa.motor.contexto import Contexto, FalhaCaminho
from massa.motor.gerador import Valor, gerar, rng, violacoes
from massa.motor.provisionador import _valor_ref


def _fmt(regra, v: Valor) -> Any:
    if regra and regra.tipo == "decimal" and isinstance(v.valor, (int, float)) and v.estrategia != "formato_invalido":
        return f"{v.valor:.{regra.decimais or 2}f}"
    return v.valor


def montar_payload(ctx: Contexto, spec: EspecificacaoCenario, alvo: dict | None, papeis: dict[str, dict],
                   chave: str) -> dict[str, Any]:
    receita = ctx.catalogo.receita_da_operacao(spec.entidade, spec.operacao)
    if receita is None:
        raise FalhaCaminho(f"sem receita/interface para {spec.entidade}.{spec.operacao}")
    passo = receita.passos[0]
    interface = ctx.catalogo.interfaces[passo.interface]
    inst = alvo or {"chave": None, "atributos": {}}
    params = {k: _valor_ref(ref, inst, papeis) for k, ref in passo.parametros.items()}
    variacoes = {v.campo: v.regra for v in spec.variacoes}
    body: dict[str, Any] = {}
    rastreio: list[dict] = []
    violados: set[str] = set()
    for c in interface.campos:
        regra = ctx.catalogo.regra(spec.entidade, c.campo)
        if c.campo in spec.entradas:
            v = Valor(c.campo, spec.entradas[c.campo], "entrada", "entrada", list(regra.fontes) if regra else [],
                      origem="entrada_cenario")
        elif c.campo in variacoes and regra:
            v = gerar(regra, variacoes[c.campo], rng(spec.seed, f"{chave}:{c.campo}"), ctx.data_base)
        elif c.campo in params:
            v = Valor(c.campo, params[c.campo], "parametro", "entrada", origem="parametro")
        elif regra:
            v = gerar(regra, "valido", rng(spec.seed, f"{chave}:{c.campo}"), ctx.data_base)
        else:
            raise FalhaCaminho(f"campo {c.campo} sem regra nem valor")
        body[c.caminho_json or c.campo] = _fmt(regra, v)
        if regra and v.origem != "parametro" and violacoes(regra, v.valor):
            violados.add(c.campo)
        rastreio.append(v.rastreio())
    invalidas = {campo for campo, r in variacoes.items() if r in VARIACOES_INVALIDAS}
    if spec.tipo != "negativo" and violados:
        raise FalhaCaminho(f"payload de cenário {spec.tipo} viola regras: {sorted(violados)}")
    if spec.tipo == "negativo" and violados != invalidas:
        raise FalhaCaminho(f"payload negativo deveria violar exatamente {sorted(invalidas)}, viola {sorted(violados)}")
    return {"interface": interface.id, "metodo": interface.metodo, "params": params,
            "body": body if interface.metodo not in ("GET", "DELETE") else None, "rastreio": rastreio}


ROTEIRO = '''# Roteiro de tela gerado pela Fábrica de Massa — reexecutável. Cenário: {cenario}
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = {base!r}
ROTA = {rota!r}
CAMPOS = {campos!r}
BOTAO, RESULTADO = {botao!r}, {resultado!r}
EVIDENCIA = Path({evidencia!r})

with sync_playwright() as p:
    nav = p.chromium.launch({lancamento})
    pg = nav.new_page()
    pg.goto(BASE + ROTA)
    for seletor, valor in CAMPOS:
        pg.fill(seletor, "" if valor is None else str(valor))
    pg.click(BOTAO)
    pg.wait_for_function("document.querySelector('" + RESULTADO + "').dataset.status !== ''", timeout=15000)
    status = int(pg.get_attribute(RESULTADO, "data-status"))
    texto = pg.inner_text(RESULTADO)
    EVIDENCIA.parent.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(EVIDENCIA), full_page=True)
    nav.close()
print(json.dumps({{"status": status, "texto": texto, "evidencia": str(EVIDENCIA)}}))
'''


def montar_roteiro_tela(ctx: Contexto, spec: EspecificacaoCenario, payload: dict, destino: Path) -> Path:
    interface = ctx.catalogo.interfaces[payload["interface"]]
    if not interface.tela:
        raise FalhaCaminho(f"interface {interface.id} não tem mapa de tela")
    valores = {**payload["params"], **(payload["body"] or {})}
    campos = [(c["seletor"], valores.get(c["campo"])) for c in interface.tela["campos"]]
    lanc = f"executable_path={ctx.navegador!r}, args=['--no-sandbox']" if ctx.navegador else "args=['--no-sandbox']"
    destino.mkdir(parents=True, exist_ok=True)
    roteiro = destino / "roteiro_tela.py"
    roteiro.write_text(ROTEIRO.format(cenario=spec.id, base=ctx.api_base, rota=interface.tela["rota"], campos=campos,
                                      botao=interface.tela["botao"], resultado=interface.tela["resultado"],
                                      evidencia=str((destino / "evidencia.png").resolve()), lancamento=lanc),
                       encoding="utf-8")
    return roteiro


def pacote_massa(spec: EspecificacaoCenario, papeis: dict[str, dict], payload: dict | None) -> dict:
    return {"cenario": spec.id, "titulo": spec.titulo,
            "massa": {p: {"registro": i.get("registro"), "estado": i.get("estado"), "chave": i.get("chave"),
                          "atributos": i.get("atributos", {})} for p, i in papeis.items()},
            "payload": payload}


def salvar_json(caminho: Path, dados: Any) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return caminho
