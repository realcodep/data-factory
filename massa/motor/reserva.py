"""Reservas de massa com prazo: evitam que dois testes usem o mesmo registro.

- `consumivel`: exclusivo (o teste vai transformar ou consumir o registro).
- `compartilhavel`: vários leitores ao mesmo tempo, mas nunca junto com um consumidor.
A trava é atômica (BEGIN IMMEDIATE); toda reserva e liberação também vira evento no registro único.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from massa.eventos import RegistroEventos

_DDL = """
CREATE TABLE IF NOT EXISTS reservas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  registro TEXT NOT NULL, estado TEXT NOT NULL, plano_id TEXT NOT NULL, cenario TEXT,
  uso TEXT NOT NULL CHECK (uso IN ('compartilhavel','consumivel')),
  expira_em TEXT NOT NULL, liberada INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_reservas_registro ON reservas(registro, liberada);
"""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class Reservas:
    def __init__(self, eventos: RegistroEventos):
        self.ev = eventos
        self.con = sqlite3.connect(eventos.caminho, check_same_thread=False, isolation_level=None, timeout=10)
        self.con.executescript(_DDL)

    def _ativas(self, registro: str | None = None) -> list[sqlite3.Row]:
        self.con.row_factory = sqlite3.Row
        sql = "SELECT * FROM reservas WHERE liberada=0 AND expira_em > ?"
        args: list = [_agora().isoformat()]
        if registro:
            sql += " AND registro=?"
            args.append(registro)
        return self.con.execute(sql, args).fetchall()

    def ativas(self) -> list[dict]:
        return [dict(r) for r in self._ativas()]

    def ocupados(self, uso_pedido: str) -> set[str]:
        """Registros que NÃO podem ser entregues para o uso pedido."""
        bloqueia = self._ativas()
        if uso_pedido == "consumivel":
            return {r["registro"] for r in bloqueia}
        return {r["registro"] for r in bloqueia if r["uso"] == "consumivel"}

    def reservar(self, registro: str, estado: str, plano_id: str, uso: str, cenario: str | None = None,
                 prazo_s: int = 3600) -> bool:
        self.con.execute("BEGIN IMMEDIATE")
        try:
            ativas = self._ativas(registro)
            mesma = [r for r in ativas if r["plano_id"] == plano_id]
            if mesma:                                   # idempotente para o mesmo plano
                self.con.execute("COMMIT")
                return True
            if ativas and (uso == "consumivel" or any(r["uso"] == "consumivel" for r in ativas)):
                self.con.execute("ROLLBACK")
                return False
            expira = (_agora() + timedelta(seconds=prazo_s)).isoformat()
            self.con.execute("INSERT INTO reservas (registro, estado, plano_id, cenario, uso, expira_em) "
                             "VALUES (?,?,?,?,?,?)", (registro, estado, plano_id, cenario, uso, expira))
            self.con.execute("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise
        self.ev.registrar("reserva_feita", {"registro": registro, "estado": estado, "uso": uso, "cenario": cenario,
                                            "expira_em": expira}, plano_id, chave=f"{plano_id}:reserva:{registro}")
        return True

    def liberar(self, plano_id: str, registro: str | None = None, motivo: str = "fim_do_plano") -> int:
        sql, args = "SELECT registro FROM reservas WHERE liberada=0 AND plano_id=?", [plano_id]
        if registro:
            sql += " AND registro=?"
            args.append(registro)
        regs = [r[0] for r in self.con.execute(sql, args)]
        for reg in regs:
            self.con.execute("UPDATE reservas SET liberada=1 WHERE plano_id=? AND registro=? AND liberada=0",
                             (plano_id, reg))
            self.ev.registrar("reserva_liberada", {"registro": reg, "motivo": motivo}, plano_id)
        return len(regs)

    def expirar(self) -> int:
        vencidas = self.con.execute("SELECT plano_id, registro FROM reservas WHERE liberada=0 AND expira_em <= ?",
                                    (_agora().isoformat(),)).fetchall()
        for plano_id, reg in vencidas:
            self.con.execute("UPDATE reservas SET liberada=1 WHERE plano_id=? AND registro=?", (plano_id, reg))
            self.ev.registrar("reserva_liberada", {"registro": reg, "motivo": "expirada"}, plano_id)
        return len(vencidas)

    def invalidar_todas(self, motivo: str) -> int:
        regs = self.con.execute("SELECT plano_id, registro FROM reservas WHERE liberada=0").fetchall()
        self.con.execute("UPDATE reservas SET liberada=1 WHERE liberada=0")
        for plano_id, reg in regs:
            self.ev.registrar("reserva_liberada", {"registro": reg, "motivo": motivo}, plano_id)
        return len(regs)
