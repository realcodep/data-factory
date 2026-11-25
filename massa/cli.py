"""CLI da Fábrica de Massa: `python -m massa.cli <comando>`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from massa import config


def cmd_catalogo(a) -> int:
    from massa import catalogo as cat
    amb = config.ambiente()
    raiz = Path(a.raiz)
    if a.acao == "exportar-openapi":
        from demo.api import criar_app
        doc = criar_app(amb["banco_url"]).openapi()
        for cl in ("credito", "garantias"):
            (raiz / cl / "openapi.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print("openapi exportado")
        return 0
    if a.acao == "build":
        d = cat.construir(raiz, amb["banco_url"])
        print(f"catálogo {d['hash']} (commit {d['commit']}) — {len(d['estados'])} estados, "
              f"{len(d['receitas'])} receitas, {len(d['conflitos'])} conflitos")
        return 0
    if a.acao == "validar":
        erros = cat.validar(cat.carregar_definicoes(raiz), raiz, amb["banco_url"])
        print("\n".join(erros) or "catálogo válido")
        status = cat.Catalogo.carregar(raiz)
        if status.desatualizado:
            print("ATENÇÃO: catálogo desatualizado em relação às fontes — rode `massa catalogo build`")
        return 1 if erros else 0
    if a.acao == "diff":
        ver = raiz / "dist" / "versoes"
        A = json.loads((ver / f"{a.versoes[0]}.json").read_text())
        B = json.loads((ver / f"{a.versoes[1]}.json").read_text())
        print(json.dumps(cat.diff(A, B), indent=2, ensure_ascii=False))
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="massa")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("catalogo")
    c.add_argument("acao", choices=["build", "validar", "diff", "exportar-openapi"])
    c.add_argument("versoes", nargs="*")
    c.add_argument("--raiz", default="catalogo")
    c.set_defaults(func=cmd_catalogo)
    from massa import cli_extra
    cli_extra.registrar(sub)
    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
