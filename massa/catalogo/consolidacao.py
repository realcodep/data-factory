"""Consolidação de regras do mesmo campo vindas de fontes diferentes.

- Entre fontes técnicas (copybook, java, banco, openapi): a mais restritiva vence.
- Entre fonte funcional (normativo/Domain Pack) e técnica: se divergem, é CONFLITO.
  O conflito não é resolvido aqui: fica registrado com as duas evidências, porque define o oráculo do teste.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from massa.contratos import RegraCampo

ATRIBUTOS = ("tamanho", "decimais", "minimo", "maximo", "dominio", "padrao")
_MAIS_RESTRITIVO = {"tamanho": min, "decimais": min, "maximo": min, "minimo": max}


def _mesclar_tecnicas(regras: list[RegraCampo]) -> tuple[RegraCampo, list[dict]]:
    base = RegraCampo(campo=regras[0].campo)
    conflitos: list[dict] = []
    tipos = [r.tipo for r in regras]
    base.tipo = "enum" if "enum" in tipos else next((t for t in tipos if t != "str"), "str")
    for r in regras:
        base.obrigatorio = base.obrigatorio or r.obrigatorio
        base.padrao = base.padrao or r.padrao
        base.semantica = base.semantica or r.semantica
        for attr, escolher in _MAIS_RESTRITIVO.items():
            a, b = getattr(base, attr), getattr(r, attr)
            if b is not None:
                setattr(base, attr, b if a is None else escolher(a, b))
        if r.dominio:
            if base.dominio is None:
                base.dominio = list(r.dominio)
            else:
                inter = [v for v in base.dominio if v in r.dominio]
                if not inter:
                    conflitos.append({"campo": base.campo, "atributo": "dominio", "tipo": "tecnico_x_tecnico",
                                      "valores": [base.dominio, r.dominio],
                                      "evidencias": [f.referencia for f in r.fontes]})
                else:
                    base.dominio = inter
        base.fontes.extend(r.fontes)
    return base, conflitos


def consolidar(regras: list[RegraCampo], entidade: str) -> tuple[dict[str, RegraCampo], list[dict[str, Any]]]:
    por_campo: dict[str, list[RegraCampo]] = defaultdict(list)
    for r in regras:
        por_campo[r.campo].append(r)
    resultado: dict[str, RegraCampo] = {}
    conflitos: list[dict[str, Any]] = []
    for campo, lista in por_campo.items():
        tecnicas = [r for r in lista if not any(f.origem == "funcional" for f in r.fontes)]
        funcionais = [r for r in lista if any(f.origem == "funcional" for f in r.fontes)]
        base, cfs = _mesclar_tecnicas(tecnicas or funcionais)
        for func in funcionais if tecnicas else []:
            for attr in ATRIBUTOS:
                vf, vt = getattr(func, attr), getattr(base, attr)
                if vf is None:
                    continue
                divergente = (sorted(map(str, vf)) != sorted(map(str, vt))) if attr == "dominio" and vt else (vt is not None and vf != vt)
                if divergente:
                    cfs.append({"campo": campo, "atributo": attr, "tipo": "funcional_x_tecnico",
                                "tecnico": vt, "funcional": vf,
                                "evidencias_tecnicas": [f.referencia for f in base.fontes],
                                "evidencias_funcionais": [f.referencia for f in func.fontes]})
                elif vt is None:
                    setattr(base, attr, vf)
            base.fontes.extend(func.fontes)
        base.entidade = entidade
        for c in cfs:
            c["entidade"] = entidade
        if cfs:
            base.conflito = {"itens": cfs}
        resultado[campo] = base
        conflitos.extend(cfs)
    return resultado, conflitos
