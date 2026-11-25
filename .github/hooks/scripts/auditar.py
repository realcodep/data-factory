"""postToolUse — auditoria de cada chamada ao servidor MCP `massa` (o mascaramento já é feito no servidor)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comum import ativo, entrada, ferramenta, log  # noqa: E402
from isolar_ferramentas import MCP_MASSA  # noqa: E402


def main() -> None:
    if not ativo():
        return
    dados = entrada()
    nome, args = ferramenta(dados)
    if MCP_MASSA.match(nome):
        resultado = dados.get("toolResult") or dados.get("tool_response") or {}
        log("auditoria_hooks.jsonl", {"hook": "postToolUse", "ferramenta": nome,
                                      "plano_id": args.get("plano_id"), "resultado_tipo": type(resultado).__name__})


if __name__ == "__main__":
    main()
