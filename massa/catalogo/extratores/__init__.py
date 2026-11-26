"""Extratores determinísticos de regras de campo (sem LLM).

Cada extrator devolve list[RegraCampo] com fontes preenchidas (arquivo:linha ou tabela.coluna).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect

from massa.contratos import Fonte, RegraCampo


# ───────────────────────── nomes ─────────────────────────

def normalizar(nome: str, prefixos: list[str] | None = None, sinonimos: dict[str, list[str]] | None = None) -> str:
    """GAR-VLR-AVALIACAO / valorAvaliacao / vlr_avaliacao -> chave comum (com sinônimos)."""
    n = nome.strip()
    for p in (prefixos or []) + ["WS-", "LK-"]:
        if n.upper().startswith(p.upper()):
            n = n[len(p):]
    n = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", n)
    n = re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")
    for canonico, alts in (sinonimos or {}).items():
        if n == canonico or n in alts:
            return canonico
    return n


# ───────────────────────── COBOL ─────────────────────────

_RE_COB = re.compile(
    r"^\s*(?P<nivel>\d{2})\s+(?P<nome>[A-Z0-9-]+)"
    r"(?:\s+PIC(?:TURE)?\s+(?P<pic>[^\s.]+)(?:\s+COMP-3)?)?"
    r"(?:\s+VALUE\s+(?P<valor>.+?))?\s*\.\s*$", re.I)


def _expandir_pic(pic: str) -> str:
    return re.sub(r"([XA9])\((\d+)\)", lambda m: m.group(1) * int(m.group(2)), pic.upper())


def _regra_pic(nome: str, pic: str) -> RegraCampo:
    p = _expandir_pic(pic)
    sinal = p.startswith("S")
    p = p.lstrip("S")
    r = RegraCampo(campo=nome)
    if "X" in p or "A" in p:
        r.tipo, r.tamanho = "str", len(p)
    elif "V" in p:
        inteiro, dec = p.split("V")
        r.tipo, r.tamanho, r.decimais = "decimal", len(inteiro) + len(dec), len(dec)
        r.maximo = float("9" * len(inteiro) + "." + "9" * len(dec))
        r.minimo = -r.maximo if sinal else 0.0
    else:
        r.tipo, r.tamanho = "int", len(p)
        r.maximo = float("9" * len(p))
        r.minimo = -r.maximo if sinal else 0.0
    return r


def extrair_copybook(caminho: str | Path, **nomes) -> list[RegraCampo]:
    regras: list[RegraCampo] = []
    ultimo: RegraCampo | None = None
    for i, linha in enumerate(Path(caminho).read_text(encoding="latin-1").splitlines(), 1):
        cod = linha[6:72] if len(linha) > 6 else linha
        if not cod.strip() or cod.lstrip().startswith("*") or linha[6:7] == "*":
            continue
        m = _RE_COB.match(cod)
        if not m:
            continue
        fonte = Fonte(origem="copybook", referencia=f"{caminho}:{i}", trecho=cod.strip())
        if m["nivel"] == "88" and ultimo is not None:
            ultimo.tipo = "enum"
            ultimo.dominio = (ultimo.dominio or []) + re.findall(r"'([^']*)'", m["valor"] or "")
            ultimo.fontes.append(fonte)
        elif m["pic"]:
            ultimo = _regra_pic(normalizar(m["nome"], **nomes), m["pic"])
            ultimo.fontes.append(fonte)
            regras.append(ultimo)
    return regras


# ───────────────────────── Java / Bean Validation ─────────────────────────

_TIPOS_JAVA = {"String": "str", "Integer": "int", "int": "int", "Long": "int", "long": "int", "BigDecimal": "decimal",
               "Double": "decimal", "LocalDate": "date", "Boolean": "bool", "boolean": "bool"}
_RE_CAMPO = re.compile(r"^\s*private\s+(?P<tipo>[\w<>.]+)\s+(?P<nome>\w+)\s*;")
_RE_ENUM = re.compile(r"enum\s+(\w+)\s*\{([^}]*)\}", re.S)
_RE_ARG = re.compile(r"(\w+)\s*=\s*(\"(?:[^\"\\]|\\.)*\"|[\w.\-]+)")


def _num_anotacao(ann: str, args: dict) -> float:
    if "value" in args:
        return float(args["value"])
    return float(re.search(r"\(\s*\"?(-?[\d.]+)", ann).group(1))


def extrair_java(caminho: str | Path, **nomes) -> list[RegraCampo]:
    texto = Path(caminho).read_text(encoding="utf-8")
    enums = {n: [v.strip().split("(")[0] for v in corpo.split(";")[0].split(",") if v.strip()]
             for n, corpo in _RE_ENUM.findall(texto)}
    regras: list[RegraCampo] = []
    pendentes: list[tuple[int, str]] = []
    for i, linha in enumerate(texto.splitlines(), 1):
        s = linha.strip()
        if s.startswith("@"):
            pendentes.append((i, s))
            continue
        m = _RE_CAMPO.match(linha)
        if not m:
            if s and not s.startswith(("//", "*", "/*")):
                pendentes = []
            continue
        r = RegraCampo(campo=normalizar(m["nome"], **nomes))
        if m["tipo"] in enums:
            r.tipo, r.dominio = "enum", enums[m["tipo"]]
        else:
            r.tipo = _TIPOS_JAVA.get(m["tipo"], "str")
        r.fontes.append(Fonte(origem="java", referencia=f"{caminho}:{i}", trecho=s))
        for j, ann in pendentes:
            nome = re.match(r"@(\w+)", ann).group(1)
            args = {k: v.strip('"').replace("\\\\", "\\") for k, v in _RE_ARG.findall(ann)}
            if nome in ("NotNull", "NotBlank", "NotEmpty"):
                r.obrigatorio = True
            elif nome == "Size" and "max" in args:
                r.tamanho = int(args["max"])
            elif nome == "Pattern":
                r.padrao = args.get("regexp")
            elif nome in ("Min", "DecimalMin"):
                r.minimo = _num_anotacao(ann, args)
            elif nome in ("Max", "DecimalMax"):
                r.maximo = _num_anotacao(ann, args)
            elif nome == "Positive":
                r.minimo = 0.01
            elif nome == "PositiveOrZero":
                r.minimo = 0.0
            elif nome == "Digits":
                r.decimais = int(args.get("fraction", 0))
                inteiro = int(args["integer"])
                r.tamanho = inteiro + r.decimais
                r.maximo = float("9" * inteiro + ("." + "9" * r.decimais if r.decimais else ""))
            elif nome in ("CPF", "CNPJ"):
                r.semantica = nome.lower()
            elif nome in ("Past", "PastOrPresent", "Future", "FutureOrPresent"):
                r.semantica = nome[0].lower() + nome[1:]
            else:
                continue
            r.fontes.append(Fonte(origem="java", referencia=f"{caminho}:{j}", trecho=ann))
        regras.append(r)
        pendentes = []
    return regras


# ───────────────────────── Banco (schema) ─────────────────────────

def extrair_banco(url: str, tabela: str, **nomes) -> list[RegraCampo]:
    eng = create_engine(url)
    insp = inspect(eng)
    regras: dict[str, RegraCampo] = {}
    pk = set(insp.get_pk_constraint(tabela)["constrained_columns"])
    for col in insp.get_columns(tabela):
        t = str(col["type"]).upper()
        r = RegraCampo(campo=normalizar(col["name"], **nomes), obrigatorio=not col["nullable"] and col["name"] not in pk)
        m = re.match(r"(?:N?VAR)?CHAR\((\d+)\)", t)
        if m:
            r.tipo, r.tamanho = "str", int(m.group(1))
        elif t.startswith(("NUMERIC", "DECIMAL")):
            p, s = (re.findall(r"\d+", t) + ["15", "2"])[:2]
            p, s = int(p), int(s)
            r.tipo, r.tamanho, r.decimais = "decimal", p, s
            r.maximo = float("9" * (p - s) + ("." + "9" * s if s else ""))
        elif "INT" in t:
            r.tipo = "int"
        elif "DATE" in t or "TIMESTAMP" in t:
            r.tipo = "date"
        r.fontes.append(Fonte(origem="banco", referencia=f"{tabela}.{col['name']}",
                              trecho=t + ("" if col["nullable"] else " NOT NULL")))
        regras[col["name"]] = r
    for ck in insp.get_check_constraints(tabela):
        m = re.search(r"(\w+)\s+IN\s*\(([^)]*)\)", ck.get("sqltext", ""), re.I)
        if m and m.group(1) in regras:
            r = regras[m.group(1)]
            r.tipo, r.dominio = "enum", re.findall(r"'([^']*)'", m.group(2))
            r.fontes.append(Fonte(origem="banco", referencia=f"{tabela}.{ck.get('name') or 'CHECK'}",
                                  trecho=ck["sqltext"]))
    eng.dispose()
    return list(regras.values())


# ───────────────────────── OpenAPI ─────────────────────────

def extrair_openapi(caminho: str | Path, esquemas: list[str], **nomes) -> list[RegraCampo]:
    doc = json.loads(Path(caminho).read_text(encoding="utf-8"))
    comps = doc.get("components", {}).get("schemas", {})
    regras = []
    for nome_esq in esquemas:
        esq = comps[nome_esq]
        obrig = set(esq.get("required", []))
        for campo, prop in esq.get("properties", {}).items():
            alvo = prop
            for alt in prop.get("anyOf", []):
                if alt.get("type") in ("number", "integer", "string") and alt.get("type") != "null":
                    alvo = {**alt, **{k: v for k, v in prop.items() if k != "anyOf"}}
                    break
            r = RegraCampo(campo=normalizar(campo, **nomes), obrigatorio=campo in obrig)
            tipo = alvo.get("type")
            fmt = alvo.get("format")
            r.tipo = {"integer": "int", "number": "decimal", "boolean": "bool"}.get(tipo, "str")
            if fmt == "date":
                r.tipo = "date"
            if "enum" in alvo:
                r.tipo, r.dominio = "enum", alvo["enum"]
            for k_api, k in (("maxLength", "tamanho"), ("minimum", "minimo"), ("maximum", "maximo"),
                             ("exclusiveMinimum", "minimo"), ("pattern", "padrao")):
                if k_api in alvo:
                    setattr(r, k, alvo[k_api])
            r.fontes.append(Fonte(origem="openapi", referencia=f"{caminho}#/components/schemas/{nome_esq}/{campo}",
                                  trecho=json.dumps(alvo, ensure_ascii=False)[:200]))
            regras.append(r)
    return regras


# ───────────────────────── Domain Pack ─────────────────────────

def extrair_domain_pack(caminho: str | Path, entidade: str, **nomes) -> tuple[list[RegraCampo], list[dict[str, Any]]]:
    """Devolve (regras funcionais por campo, fatos de regra de negócio)."""
    pack = json.loads(Path(caminho).read_text(encoding="utf-8"))
    regras, fatos_negocio = [], []
    for f in pack["fatos"]:
        if f.get("entidade") != entidade:
            continue
        ref = f"{pack['pack']}@{pack['versao']}#{f['id']}"
        if f["tipo"] == "funcional":
            r = RegraCampo(campo=normalizar(f["campo"], **nomes))
            atributo, valor = f["atributo"], f["valor"]
            if atributo == "dominio":
                r.tipo, r.dominio = "enum", valor
            else:
                setattr(r, atributo, valor)
            r.fontes.append(Fonte(origem="funcional", referencia=ref, trecho=f["texto"]))
            regras.append(r)
        else:
            fatos_negocio.append({**f, "referencia": ref})
    return regras, fatos_negocio
