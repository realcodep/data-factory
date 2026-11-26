"""sessionEnd / errorOccurred — garante o rastro para retomada e registra o erro.

O checkpoint de cada passo já está no registro de eventos do motor; aqui gravamos quais planos ficaram abertos,
para o sessionStart seguinte avisar e o agente chamar `retomar_plano`."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comum import RAIZ, ativo, entrada, log  # noqa: E402


def main() -> None:
    if not ativo():
        return
    dados = entrada()
    if "--erro" in sys.argv:
        log("auditoria_hooks.jsonl", {"hook": "errorOccurred", "erro": str(dados.get("error") or dados)[:500]})
    db = RAIZ / "estado" / "motor.db"
    abertos = []
    if db.exists():
        con = sqlite3.connect(db)
        criados = {r[0] for r in con.execute("select plano_id from eventos where tipo='plano_criado'")}
        concluidos = {r[0] for r in con.execute("select plano_id from eventos where tipo='plano_concluido'")}
        abertos = sorted(criados - concluidos)
    ret = RAIZ / "estado" / "retomar.json"
    if abertos:
        ret.parent.mkdir(parents=True, exist_ok=True)
        ret.write_text(json.dumps({"planos_abertos": abertos}, ensure_ascii=False), encoding="utf-8")
    elif ret.exists():
        ret.unlink()


if __name__ == "__main__":
    main()
