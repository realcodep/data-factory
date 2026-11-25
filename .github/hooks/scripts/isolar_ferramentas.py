"""preToolUse — ISOLAMENTO do agente: só o servidor MCP `massa`, leitura do repositório e escrita em pastas permitidas.
Falha fechada: ferramenta desconhecida ou erro de avaliação = negar."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comum import RAIZ, ativo, entrada, ferramenta, negar  # noqa: E402

LEITURA = {"read", "view", "read_file", "search", "grep", "glob", "list", "ls", "codebase", "find", "usages",
           "problems", "agent", "runsubagent", "task", "todo", "todowrite", "readfile", "listdir", "file_search",
           "grep_search", "semantic_search", "list_dir"}
ESCRITA = {"edit", "write", "create", "create_file", "str_replace", "multiedit", "apply_patch", "insert_edit_into_file",
           "replace_string_in_file", "editfiles"}
PASTAS_ESCRITA = ("saida/", "catalogo/propostas/")
MCP_MASSA = re.compile(r"^(massa[/._-]|mcp__massa__|massa$)", re.I)


def avaliar(nome: str, args: dict) -> str | None:
    n = nome.strip()
    base = n.split("/")[-1].lower()
    if MCP_MASSA.match(n):
        return None
    if base in LEITURA or n.lower() in LEITURA:
        return None
    if base in ESCRITA or n.lower() in ESCRITA:
        alvo = str(args.get("path") or args.get("file_path") or args.get("filePath") or args.get("raw") or "")
        try:
            rel = str(Path(alvo).resolve().relative_to(RAIZ)).replace("\\", "/") if alvo else ""
        except ValueError:
            return f"escrita fora do repositório negada: {alvo}"
        if rel.startswith(PASTAS_ESCRITA):
            return None
        return f"escrita permitida só em {', '.join(PASTAS_ESCRITA)} (tentou {rel or alvo})"
    return (f"ferramenta '{nome}' negada: o agente de massa só usa o servidor MCP `massa` e leitura do repositório "
            "(sem terminal, sem SQL, sem chamadas diretas a APIs)")


def main() -> None:
    if not ativo():
        return
    try:
        nome, args = ferramenta(entrada())
        motivo = avaliar(nome, args)
    except Exception as e:  # noqa: BLE001 — falha fechada
        motivo = f"hook de isolamento falhou ({e}); ação negada por segurança"
    if motivo:
        negar("PreToolUse", motivo)


if __name__ == "__main__":
    main()
