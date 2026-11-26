"""Gerador determinístico de valores e validador de valores contra regras.

Mesma regra + mesma estratégia + mesma semente (e mesma chave) => mesmo valor.
Documentos são sintéticos, com dígito verificador válido (ou inválido de propósito).
"""
from __future__ import annotations

import hashlib
import random
import re
import string
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

from massa.contratos import VARIACOES_INVALIDAS, Fonte, RegraCampo


@dataclass
class Valor:
    campo: str
    valor: Any
    estrategia: str
    destino: Literal["precondicao", "entrada"]
    fontes: list[Fonte] = field(default_factory=list)
    origem: str = "gerado"       # gerado | entrada_cenario | parametro

    def rastreio(self) -> dict:
        return {"campo": self.campo, "valor": self.valor, "estrategia": self.estrategia, "destino": self.destino,
                "origem": self.origem, "fontes": [f.referencia for f in self.fontes]}


def rng(seed: int, chave: str) -> random.Random:
    h = hashlib.sha256(f"{seed}:{chave}".encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def _dv(base: list[int], pesos: list[int]) -> int:
    s = sum(d * p for d, p in zip(base, pesos)) % 11
    return 0 if s < 2 else 11 - s


def cpf(r: random.Random, valido: bool = True) -> str:
    b = [r.randint(0, 9) for _ in range(9)]
    while len(set(b)) == 1:
        b = [r.randint(0, 9) for _ in range(9)]
    b.append(_dv(b, list(range(10, 1, -1))))
    b.append(_dv(b, list(range(11, 1, -1))))
    if not valido:
        b[-1] = (b[-1] + 1) % 10
    return "".join(map(str, b))


def cnpj(r: random.Random, valido: bool = True) -> str:
    b = [r.randint(0, 9) for _ in range(8)] + [0, 0, 0, 1]
    b.append(_dv(b, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]))
    b.append(_dv(b, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]))
    if not valido:
        b[-1] = (b[-1] + 1) % 10
    return "".join(map(str, b))


def documento_valido(doc: Any) -> bool:
    doc = str(doc)
    if not doc.isdigit():
        return False
    d = [int(x) for x in doc]
    if len(d) == 11 and len(set(d)) > 1:
        return d[9] == _dv(d[:9], list(range(10, 1, -1))) and d[10] == _dv(d[:10], list(range(11, 1, -1)))
    if len(d) == 14:
        return d[12] == _dv(d[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) and \
            d[13] == _dv(d[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return False


def semantica(r: RegraCampo) -> str | None:
    n = r.campo
    if "cpf" in n or "cnpj" in n:
        return "documento"
    if r.tipo == "date" or n.startswith(("data_", "dt_")):
        return "data"
    return r.semantica


def dominio_seguro(r: RegraCampo) -> list[Any] | None:
    """Para valores VÁLIDOS: se fontes funcional e técnica divergem no domínio, usa só a interseção
    (válida para ambas). Assim o conflito só precisa de decisão quando o teste depende dele."""
    if not r.dominio:
        return None
    if r.conflito:
        for c in r.conflito["itens"]:
            if c["atributo"] == "dominio" and c.get("funcional") is not None:
                return [v for v in r.dominio if v in c["funcional"]]
    return r.dominio


def _por_padrao(padrao: str, r: random.Random, tamanho: int | None) -> str | None:
    p = padrao.strip("^$")
    m = re.fullmatch(r"\\d\{(\d+)(?:,(\d+))?\}", p)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        n = min(hi, tamanho or hi)
        return "".join(r.choice(string.digits) for _ in range(max(lo, n)))
    return None


def gerar(regra: RegraCampo, estrategia: str, r: random.Random, data_base: date = date(2026, 1, 1),
          destino: str = "entrada") -> Valor:
    sem = semantica(regra)
    lo = regra.minimo if regra.minimo is not None else 0.0
    hi = regra.maximo if regra.maximo is not None else float(10 ** min(regra.tamanho or 9, 9) - 1)
    passo = 10 ** -(regra.decimais or 0) if regra.tipo == "decimal" else 1

    def num(x: float):
        return round(x, regra.decimais if regra.decimais is not None else 2) if regra.tipo == "decimal" else int(x)

    v: Any
    if estrategia == "vazio":
        v = None
    elif estrategia == "tamanho_excedido":
        v = "9" * ((regra.tamanho or 50) + 1)
    elif estrategia == "fora_dominio":
        dom = {str(x) for x in (regra.dominio or [])}
        v = next(c for c in ("ZZZ", "ZZ", "Z", "999") if c not in dom and len(c) <= (regra.tamanho or 3))
    elif estrategia == "formato_invalido":
        v = cpf(r, valido=False) if sem == "documento" else ("31/02/2025" if sem == "data" else "ABC#")
    elif estrategia == "limite_inferior":
        m = re.fullmatch(r"\\d\{(\d+)(?:,(\d+))?\}", (regra.padrao or "").strip("^$"))
        if regra.tipo in ("int", "decimal"):
            v = num(lo)
        elif m:
            v = "".join(r.choice(string.digits) for _ in range(int(m.group(1))))
        else:
            v = "1"
    elif estrategia == "limite_superior":
        m = re.fullmatch(r"\\d\{(\d+)(?:,(\d+))?\}", (regra.padrao or "").strip("^$"))
        if regra.tipo in ("int", "decimal"):
            v = num(hi)
        elif m:
            v = "".join(r.choice(string.digits) for _ in range(int(m.group(2) or m.group(1))))
        else:
            v = "9" * (regra.tamanho or 1)
    elif estrategia == "abaixo_minimo":
        v = num(lo - passo)
    elif estrategia == "acima_maximo":
        v = num(hi + passo)
    else:  # valido
        dom = dominio_seguro(regra)
        if dom:
            v = r.choice(dom)
        elif sem == "documento":
            v = cpf(r)
        elif sem == "data":
            v = (data_base - timedelta(days=r.randint(1, 365))).isoformat()
        elif regra.tipo == "bool":
            v = r.choice([True, False])
        elif regra.tipo in ("int", "decimal"):
            teto = min(hi, max(lo, 0) + 1_000_000)
            v = num(r.uniform(lo + passo, teto)) if teto > lo + passo else num(lo + passo)
        elif regra.padrao and (gerado := _por_padrao(regra.padrao, r, regra.tamanho)):
            v = gerado
        else:
            n = min(regra.tamanho or 12, 12)
            v = "TST" + "".join(r.choice(string.ascii_uppercase + string.digits) for _ in range(max(n - 3, 1)))
    return Valor(campo=regra.campo, valor=v, estrategia=estrategia, destino=destino, fontes=list(regra.fontes))


def violacoes(regra: RegraCampo, valor: Any, usar_dominio_funcional: bool = False) -> list[str]:
    """Lista as regras que o valor viola (vazia = válido)."""
    out: list[str] = []
    if valor is None or valor == "":
        return ["obrigatorio"] if regra.obrigatorio else []
    s = str(valor)
    if regra.tipo == "str" and regra.tamanho and len(s) > regra.tamanho:
        out.append("tamanho")
    if regra.tipo in ("int", "decimal"):
        try:
            x = float(valor)
        except (TypeError, ValueError):
            return ["formato"]
        if regra.minimo is not None and x < regra.minimo:
            out.append("minimo")
        if regra.maximo is not None and x > regra.maximo:
            out.append("maximo")
    if regra.tipo == "date" or semantica(regra) == "data":
        try:
            date.fromisoformat(s)
        except ValueError:
            out.append("formato")
    dom = dominio_seguro(regra) if usar_dominio_funcional else regra.dominio
    if dom and s not in {str(d) for d in dom}:
        out.append("dominio")
    if regra.padrao and regra.tipo == "str" and not re.fullmatch(regra.padrao, s):
        out.append("padrao")
    if semantica(regra) == "documento" and not documento_valido(s):
        out.append("documento")
    if regra.tamanho and regra.tipo == "str" and len(s) > regra.tamanho and "tamanho" not in out:
        out.append("tamanho")
    return out
