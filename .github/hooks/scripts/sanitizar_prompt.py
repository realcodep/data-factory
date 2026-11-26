"""userPromptSubmitted — detecta dados reais no cenário (CPF/CNPJ com dígito válido, números de contrato).

Os clientes não permitem reescrever o prompt de forma uniforme; por isso o hook BLOQUEIA o envio e devolve
a versão sanitizada para o usuário reenviar."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _comum import ativo, entrada, log, responder  # noqa: E402

DOC = re.compile(r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2}|\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)")
CONTRATO = re.compile(r"\b(?:contrato|ctr)\s*(?:n[ºo°.]*\s*)?(\d{6,})\b", re.I)


def _dv(b, p):
    s = sum(x * y for x, y in zip(b, p)) % 11
    return 0 if s < 2 else 11 - s


def documento_valido(doc: str) -> bool:
    d = [int(x) for x in re.sub(r"\D", "", doc)]
    if len(d) == 11 and len(set(d)) > 1:
        return d[9] == _dv(d[:9], range(10, 1, -1)) and d[10] == _dv(d[:10], range(11, 1, -1))
    if len(d) == 14:
        return d[12] == _dv(d[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) and \
            d[13] == _dv(d[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return False


def sanitizar(texto: str) -> tuple[str, int]:
    n = 0

    def doc(m):
        nonlocal n
        if documento_valido(m.group(1)):
            n += 1
            return "<DOCUMENTO>"
        return m.group(0)

    def ctr(m):
        nonlocal n
        n += 1
        return m.group(0).replace(m.group(1), "<NUMERO_CONTRATO>")

    texto = DOC.sub(doc, texto)
    texto = CONTRATO.sub(ctr, texto)
    return texto, n


def main() -> None:
    if not ativo():
        return
    dados = entrada()
    prompt = dados.get("prompt") or dados.get("userPrompt") or ""
    limpo, n = sanitizar(prompt)
    if n:
        log("auditoria_hooks.jsonl", {"hook": "userPromptSubmitted", "dados_reais_detectados": n})
        msg = (f"Detectei {n} dado(s) que parecem reais (documento válido ou número de contrato). A fábrica usa só dados "
               f"sintéticos. Reenvie assim:\n\n{limpo}")
        responder({"decision": "block", "reason": msg,
                   "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": msg}})


if __name__ == "__main__":
    main()
