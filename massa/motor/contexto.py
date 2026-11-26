"""Contexto de execução do motor: catálogo, banco, registro de eventos, cliente HTTP, reservas e política."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from datetime import date
from pathlib import Path
from typing import Any, Callable

import httpx
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from massa import config
from massa.catalogo import Catalogo
from massa.eventos import RegistroEventos


class FalhaMotor(Exception):
    classe = "caminho"


class FalhaTransitoria(FalhaMotor):
    classe = "transitoria"


class FalhaDado(FalhaMotor):
    classe = "dado"


class FalhaCaminho(FalhaMotor):
    classe = "caminho"


class FalhaPolitica(FalhaMotor):
    classe = "politica"


AMBIENTES_PROIBIDOS = {"PRD", "PROD", "PRODUCAO", "PRODUÇÃO"}


@dataclass
class Contexto:
    catalogo: Catalogo
    eventos: RegistroEventos
    engine: Engine
    http: httpx.Client
    ambiente: str = "DEMO"
    data_base: date = date(2026, 1, 1)
    navegador: str | None = None
    api_base: str = "http://127.0.0.1:8765"
    saida: Path = Path("saida")
    autorizar: Callable[[dict[str, Any]], None] = field(default=lambda acao: None)
    tentativas: int = 3
    espera_base_s: float = 0.2
    _reservas: Any = None

    def __post_init__(self):
        if self.ambiente.upper() in AMBIENTES_PROIBIDOS:
            raise FalhaPolitica("O motor de massa não opera em produção.")
        self.catalogo.exigir_atualizado()

    @property
    def reservas(self):
        if self._reservas is None:
            from massa.motor.reserva import Reservas
            self._reservas = Reservas(self.eventos)
        return self._reservas

    @classmethod
    def do_ambiente(cls, http: httpx.Client | None = None, **kw) -> "Contexto":
        amb = config.ambiente()
        eng = create_engine(amb["banco_url"], connect_args={"check_same_thread": False}
                            if amb["banco_url"].startswith("sqlite") else {})
        nav = os.environ.get("MASSA_NAVEGADOR") or amb.get("navegador")
        return cls(
            catalogo=Catalogo.carregar(Path(kw.pop("raiz_catalogo", "catalogo"))),
            eventos=RegistroEventos(amb.get("estado_motor", "estado/motor.db")),
            engine=eng,
            http=http or httpx.Client(base_url=amb["api_base"], timeout=15),
            ambiente=amb.get("nome", "DEMO"),
            data_base=date.fromisoformat(str(amb.get("data_base", "2026-01-01"))),
            navegador=nav if nav and nav != "chromium" and Path(nav).exists() else None,
            api_base=amb["api_base"],
            **kw,
        )
