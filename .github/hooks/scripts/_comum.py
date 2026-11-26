"""Utilidades comuns dos hooks. Os hooks são INATIVOS por padrão: só agem com MASSA_HOOKS=on
ou com o arquivo config/hooks.ativos. Assim não bloqueiam quem está desenvolvendo a própria fábrica."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def ativo() -> bool:
    return os.environ.get("MASSA_HOOKS", "").lower() == "on" or (RAIZ / "config" / "hooks.ativos").exists()


def entrada() -> dict:
    try:
        bruto = sys.stdin.read()
        return json.loads(bruto) if bruto.strip() else {}
    except json.JSONDecodeError:
        return {}


def ferramenta(dados: dict) -> tuple[str, dict]:
    nome = dados.get("toolName") or dados.get("tool_name") or ""
    args = dados.get("toolArgs") or dados.get("tool_input") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"raw": args}
    return nome, args


def responder(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def negar(evento: str, motivo: str) -> None:
    # Formato aceito pelo Copilot (permissionDecision) e pelo Claude Code (hookSpecificOutput).
    responder({"permissionDecision": "deny", "permissionDecisionReason": motivo,
               "hookSpecificOutput": {"hookEventName": evento, "permissionDecision": "deny",
                                      "permissionDecisionReason": motivo}})


def log(arquivo: str, registro: dict) -> None:
    p = RAIZ / "estado" / arquivo
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"momento": datetime.now(timezone.utc).isoformat(), **registro}, ensure_ascii=False) + "\n")
