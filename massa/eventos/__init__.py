"""Registro único de eventos (somente-acréscimo).

Checkpoint, massa criada, auditoria e precedentes são projeções deste registro.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

TIPOS = {
    "plano_criado", "plano_simulado", "plano_aprovado", "plano_replanejado", "decisao_tomada", "decisao_contestada",
    "fase_iniciada", "fase_concluida", "passo_concluido", "reserva_feita", "reserva_liberada", "registro_criado",
    "chamada_executada", "verificacao_concluida", "falha_registrada", "epoca_detectada", "garimpo_vazio",
    "pergunta_feita", "receita_quebrada", "receita_saudavel", "plano_concluido",
}

_DDL = """
CREATE TABLE IF NOT EXISTS eventos (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  momento TEXT NOT NULL,
  plano_id TEXT,
  tipo TEXT NOT NULL,
  dados_json TEXT NOT NULL,
  chave_idempotencia TEXT UNIQUE
);
CREATE TRIGGER IF NOT EXISTS eventos_sem_update BEFORE UPDATE ON eventos
BEGIN SELECT RAISE(ABORT, 'registro de eventos é somente-acréscimo'); END;
CREATE TRIGGER IF NOT EXISTS eventos_sem_delete BEFORE DELETE ON eventos
BEGIN SELECT RAISE(ABORT, 'registro de eventos é somente-acréscimo'); END;
"""


class RegistroEventos:
    def __init__(self, caminho: str | Path):
        self.caminho = str(caminho)
        if self.caminho != ":memory:":
            Path(self.caminho).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.caminho, check_same_thread=False, isolation_level=None)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(_DDL)

    def registrar(self, tipo: str, dados: dict[str, Any], plano_id: str | None = None,
                  chave: str | None = None) -> int | None:
        """Grava um evento. Se a chave de idempotência já existe, não duplica e devolve None."""
        if tipo not in TIPOS:
            raise ValueError(f"tipo de evento desconhecido: {tipo}")
        try:
            cur = self.con.execute(
                "INSERT INTO eventos (momento, plano_id, tipo, dados_json, chave_idempotencia) VALUES (?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), plano_id, tipo,
                 json.dumps(dados, ensure_ascii=False, default=str), chave),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def por_chave(self, chave: str) -> dict | None:
        r = self.con.execute("SELECT seq, momento, plano_id, tipo, dados_json FROM eventos WHERE chave_idempotencia=?",
                             (chave,)).fetchone()
        return self._row(r) if r else None

    def listar(self, plano_id: str | None = None, tipos: Iterable[str] | None = None) -> list[dict]:
        sql, args = "SELECT seq, momento, plano_id, tipo, dados_json FROM eventos WHERE 1=1", []
        if plano_id:
            sql += " AND plano_id=?"
            args.append(plano_id)
        if tipos:
            tipos = list(tipos)
            sql += f" AND tipo IN ({','.join('?' * len(tipos))})"
            args += tipos
        return [self._row(r) for r in self.con.execute(sql + " ORDER BY seq", args)]

    @staticmethod
    def _row(r) -> dict:
        return {"seq": r[0], "momento": r[1], "plano_id": r[2], "tipo": r[3], "dados": json.loads(r[4])}

    # ───────── projeções ─────────
    def checkpoint(self, plano_id: str) -> dict:
        """Reconstrói o estado de execução de um plano a partir dos eventos."""
        estado: dict[str, Any] = {"plano": None, "fases_concluidas": [], "passos_concluidos": {}, "registros": {},
                                  "reservas": {}, "decisoes": {}, "aprovado": False, "concluido": False, "falhas": []}
        for e in self.listar(plano_id):
            d, t = e["dados"], e["tipo"]
            if t == "plano_criado":
                estado["plano"] = d["plano"]
            elif t == "plano_replanejado":
                estado["plano"] = d["plano"]
                validas = set(d.get("fases_validas", []))
                estado["fases_concluidas"] = [f for f in estado["fases_concluidas"] if f in validas]
                estado["passos_concluidos"] = {p: r for p, r in estado["passos_concluidos"].items()
                                               if p.split(".")[0] in validas}
            elif t == "plano_aprovado":
                estado["aprovado"] = True
            elif t == "fase_concluida":
                estado["fases_concluidas"].append(d["fase"])
            elif t == "passo_concluido":
                estado["passos_concluidos"][d["passo"]] = d.get("resultado")
            elif t == "registro_criado":
                estado["registros"][d["instancia"]] = d
            elif t == "reserva_feita":
                estado["reservas"][d["registro"]] = d
            elif t == "reserva_liberada":
                estado["reservas"].pop(d["registro"], None)
            elif t == "decisao_tomada":
                estado["decisoes"][d["pendencia_id"]] = d
            elif t == "falha_registrada":
                estado["falhas"].append(d)
            elif t == "plano_concluido":
                estado["concluido"] = True
        return estado

    def massa_criada(self, plano_id: str | None = None) -> list[dict]:
        return [e["dados"] | {"plano_id": e["plano_id"]} for e in self.listar(plano_id, ["registro_criado"])]

    def precedentes(self, minimo_aplicacoes: int = 2) -> dict[str, dict]:
        """Decisões aplicadas N vezes sem contestação, por assinatura."""
        contagem: dict[str, list[dict]] = {}
        contestadas = {e["dados"]["assinatura"] for e in self.listar(tipos=["decisao_contestada"])}
        for e in self.listar(tipos=["decisao_tomada"]):
            d = e["dados"]
            if d["assinatura"] in contestadas or d["degrau"] in ("humano",):
                # decisões humanas viram precedente na primeira vez
                if d["degrau"] == "humano" and d["assinatura"] not in contestadas:
                    contagem.setdefault(d["assinatura"], []).extend([d] * minimo_aplicacoes)
                continue
            contagem.setdefault(d["assinatura"], []).append(d)
        return {k: v[-1] for k, v in contagem.items() if len(v) >= minimo_aplicacoes}

    def auditoria(self, plano_id: str | None = None) -> list[dict]:
        return self.listar(plano_id)
