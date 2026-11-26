"""subagentStop — a saída do investigador precisa ser uma proposta com evidências (arquivo e linha)."""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from _comum import RAIZ, ativo, entrada, responder  # noqa: E402


def problemas(arquivo: Path) -> list[str]:
    try:
        p = yaml.safe_load(arquivo.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        return [f"YAML inválido: {e}"]
    erros = []
    if p.get("tipo") not in ("estado", "regra", "receita"):
        erros.append("campo 'tipo' deve ser estado, regra ou receita")
    if not p.get("proposta"):
        erros.append("campo 'proposta' vazio")
    evid = p.get("evidencias") or []
    if not evid or any(not (e.get("arquivo") and e.get("linha")) for e in evid):
        erros.append("toda evidência precisa de 'arquivo' e 'linha'")
    return erros


def main() -> None:
    if not ativo():
        return
    dados = entrada()
    nome = (dados.get("agentName") or dados.get("agent_name") or dados.get("subagent_type") or "").lower()
    if nome and "investigador" not in nome:
        return
    pasta = RAIZ / "catalogo" / "propostas"
    props = sorted(pasta.glob("*.y*ml"), key=lambda p: p.stat().st_mtime)
    if not props:
        responder({"decision": "block", "reason": "O investigador terminou sem escrever proposta em catalogo/propostas/."})
        return
    erros = problemas(props[-1])
    if erros:
        responder({"decision": "block", "reason": f"Proposta {props[-1].name} incompleta: " + "; ".join(erros)})


if __name__ == "__main__":
    main()
