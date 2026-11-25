"""sessionStart — confirma ambiente permitido, verifica catálogo e época, injeta contexto e avisa planos a retomar."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comum import RAIZ, ativo, responder  # noqa: E402


def contexto() -> tuple[str, bool]:
    sys.path.insert(0, str(RAIZ))
    import os
    os.chdir(RAIZ)
    from massa import config
    amb = config.ambiente()
    if str(amb.get("nome", "")).upper() in ("PRD", "PROD", "PRODUCAO"):
        return "Ambiente configurado é PRODUÇÃO: a fábrica de massa não opera aqui. Sessão bloqueada.", False
    linhas = [f"Fábrica de Massa — ambiente {amb.get('nome')} ({amb.get('api_base')})."]
    try:
        from massa.catalogo import Catalogo
        cat = Catalogo.carregar()
        linhas.append(f"Catálogo {cat.hash} {'DESATUALIZADO — rode `massa catalogo build`' if cat.desatualizado else 'atualizado'}.")
    except FileNotFoundError:
        linhas.append("Catálogo ainda não construído — rode `python -m massa.cli catalogo build`.")
    db = RAIZ / amb.get("estado_motor", "estado/motor.db")
    if db.exists():
        con = sqlite3.connect(db)
        criados = {r[0] for r in con.execute("select plano_id from eventos where tipo='plano_criado'")}
        concluidos = {r[0] for r in con.execute("select plano_id from eventos where tipo='plano_concluido'")}
        abertos = sorted(criados - concluidos)
        if abertos:
            linhas.append(f"Planos não concluídos (use retomar_plano): {', '.join(abertos[-5:])}.")
    ret = RAIZ / "estado" / "retomar.json"
    if ret.exists():
        linhas.append("Última sessão terminou com plano em andamento: " + ret.read_text(encoding="utf-8"))
    return " ".join(linhas), True


def main() -> None:
    if not ativo():
        return
    texto, ok = contexto()
    saida = {"additionalContext": texto, "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": texto}}
    if not ok:
        saida.update({"continue": False, "stopReason": texto})
    responder(saida)


if __name__ == "__main__":
    main()
