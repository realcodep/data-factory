"""Execução de chamadas de API e de roteiros de tela, com classificação de falhas e nova tentativa."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from massa.contratos import InterfaceApi
from massa.motor.contexto import Contexto, FalhaCaminho, FalhaTransitoria


def resolver_caminho(interface: InterfaceApi, params: dict[str, Any]) -> str:
    caminho = interface.caminho
    for k, v in params.items():
        caminho = caminho.replace("{" + k + "}", str(v))
    if "{" in caminho:
        raise FalhaCaminho(f"parâmetro de caminho não resolvido em {interface.id}: {caminho}")
    return caminho


def chamar_api(ctx: Contexto, interface: InterfaceApi, params: dict[str, Any], body: dict[str, Any] | None,
               plano_id: str | None, chave: str, esperar_sucesso: bool = True) -> dict[str, Any]:
    """Chama a API com idempotência (chave) e nova tentativa em falha transitória.

    Se `esperar_sucesso`, status fora de `status_sucesso` vira FalhaCaminho (usado no provisionamento).
    No teste (F5), o status é devolvido como resultado — cenários negativos esperam erro.
    """
    anterior = ctx.eventos.por_chave(chave)
    if anterior:
        return anterior["dados"]["resposta"] | {"reaproveitado": True}
    caminho = resolver_caminho(interface, params)
    ctx.autorizar({"tipo": "api", "interface": interface.id, "metodo": interface.metodo, "caminho": caminho,
                   "plano_id": plano_id})
    ultimo_erro: Exception | None = None
    for tentativa in range(1, ctx.tentativas + 1):
        try:
            r = ctx.http.request(interface.metodo, caminho, json=body if interface.metodo != "GET" else None)
            if r.status_code >= 500 or r.status_code == 429:
                raise FalhaTransitoria(f"{interface.id}: HTTP {r.status_code}")
            try:
                corpo = r.json()
            except ValueError:
                corpo = {"texto": r.text}
            resposta = {"status": r.status_code, "corpo": corpo, "tentativas": tentativa}
            ctx.eventos.registrar("chamada_executada", {"interface": interface.id, "metodo": interface.metodo,
                                                         "caminho": caminho, "request": body, "resposta": resposta},
                                  plano_id, chave=chave)
            if esperar_sucesso and r.status_code not in interface.status_sucesso:
                raise FalhaCaminho(f"{interface.id} devolveu {r.status_code}: {corpo}")
            return resposta
        except (httpx.TimeoutException, httpx.TransportError, FalhaTransitoria) as e:
            ultimo_erro = e
            time.sleep(ctx.espera_base_s * (2 ** (tentativa - 1)))
    raise FalhaTransitoria(f"{interface.id}: esgotadas {ctx.tentativas} tentativas ({ultimo_erro})")


def executar_roteiro(ctx: Contexto, roteiro: Path, plano_id: str | None, chave: str, timeout_s: int = 60) -> dict:
    anterior = ctx.eventos.por_chave(chave)
    if anterior:
        return anterior["dados"]["resposta"] | {"reaproveitado": True}
    ctx.autorizar({"tipo": "tela", "roteiro": str(roteiro), "plano_id": plano_id})
    proc = subprocess.run([sys.executable, str(roteiro)], capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode != 0:
        raise FalhaCaminho(f"roteiro de tela falhou: {proc.stderr[-500:]}")
    resposta = json.loads(proc.stdout.strip().splitlines()[-1])
    ctx.eventos.registrar("chamada_executada", {"tipo": "tela", "roteiro": str(roteiro), "resposta": resposta},
                          plano_id, chave=chave)
    return resposta
