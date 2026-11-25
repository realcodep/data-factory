"""Carregamento de configuração (ambiente, política, convenções, pool)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CONFIG = Path(os.environ.get("MASSA_CONFIG", "config"))


def carregar(nome: str) -> dict[str, Any]:
    p = CONFIG / f"{nome}.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def ambiente() -> dict[str, Any]:
    amb = carregar("ambiente")
    for chave, env in (("banco_url", "MASSA_BANCO_URL"), ("api_base", "MASSA_API_BASE"),
                       ("estado_motor", "MASSA_ESTADO"), ("nome", "MASSA_AMBIENTE")):
        if os.environ.get(env):
            amb[chave] = os.environ[env]
    return amb
