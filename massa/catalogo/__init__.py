"""Catálogo de massa: montado no build (por commit), federado por cluster, consultado pelo motor."""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import create_engine

from massa.catalogo.consolidacao import consolidar
from massa.catalogo.extratores import (extrair_banco, extrair_copybook, extrair_domain_pack, extrair_java,
                                       extrair_openapi)
from massa.catalogo.predicados import montar_select
from massa.contratos import Estado, InterfaceApi, Receita, RegraCampo

RAIZ_PADRAO = Path("catalogo")
VARIACOES = ["valido", "limite_inferior", "limite_superior", "abaixo_minimo", "acima_maximo", "vazio",
             "tamanho_excedido", "fora_dominio", "formato_invalido"]


class CatalogoInvalido(ValueError):
    pass


class CatalogoDesatualizado(RuntimeError):
    pass


def _yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _clusters(raiz: Path) -> dict[str, dict]:
    return _yaml(raiz / "clusters.yaml")["clusters"]


def arquivos_fonte(raiz: Path = RAIZ_PADRAO) -> list[Path]:
    """Tudo o que, se mudar, exige novo build do catálogo."""
    arqs = [raiz / "clusters.yaml", raiz / "sinonimos.yaml"]
    for cl in _clusters(raiz):
        d = raiz / cl
        arqs += sorted(p for p in d.glob("*.yaml"))
        arqs += sorted(p for p in d.glob("*.json"))
        fontes = d / "fontes.yaml"
        if fontes.exists():
            for cfg in _yaml(fontes).get("entidades", {}).values():
                for k in ("copybook", "domain_pack"):
                    if cfg.get(k):
                        arqs.append(Path(cfg[k]))
                arqs += [Path(j) for j in cfg.get("java", [])]
    return [a for a in dict.fromkeys(arqs) if a.exists()]


def hash_fontes(raiz: Path = RAIZ_PADRAO) -> str:
    h = hashlib.sha256()
    for a in arquivos_fonte(raiz):
        h.update(str(a).encode())
        h.update(a.read_bytes())
    return h.hexdigest()[:16]


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=5).stdout.strip() or None
    except Exception:
        return None


# ───────────────────────── build ─────────────────────────

def carregar_definicoes(raiz: Path = RAIZ_PADRAO) -> dict[str, Any]:
    estados, receitas, interfaces, fontes = [], [], [], {}
    for cl in _clusters(raiz):
        d = raiz / cl
        if (d / "estados.yaml").exists():
            estados += [Estado(cluster=cl, **e) for e in _yaml(d / "estados.yaml")["estados"]]
        if (d / "receitas.yaml").exists():
            receitas += [Receita(cluster=cl, **r) for r in _yaml(d / "receitas.yaml")["receitas"]]
        if (d / "interfaces.yaml").exists():
            interfaces += [InterfaceApi(**i) for i in _yaml(d / "interfaces.yaml")["interfaces"]]
        if (d / "fontes.yaml").exists():
            fontes.update(_yaml(d / "fontes.yaml")["entidades"])
    return {"estados": estados, "receitas": receitas, "interfaces": interfaces, "fontes": fontes}


def extrair_regras(fontes: dict[str, dict], banco_url: str, raiz: Path = RAIZ_PADRAO):
    cfg_nomes = _yaml(raiz / "sinonimos.yaml")
    nomes = {"prefixos": cfg_nomes.get("prefixos", []), "sinonimos": cfg_nomes.get("sinonimos", {})}
    regras: dict[str, dict[str, RegraCampo]] = {}
    conflitos: list[dict] = []
    fatos: dict[str, list[dict]] = {}
    for entidade, cfg in fontes.items():
        brutas: list[RegraCampo] = []
        if cfg.get("copybook"):
            brutas += extrair_copybook(cfg["copybook"], **nomes)
        for j in cfg.get("java", []):
            brutas += extrair_java(j, **nomes)
        if cfg.get("tabela"):
            brutas += extrair_banco(banco_url, cfg["tabela"], **nomes)
        if cfg.get("openapi"):
            brutas += extrair_openapi(cfg["openapi"]["arquivo"], cfg["openapi"]["esquemas"], **nomes)
        if cfg.get("domain_pack"):
            funcionais, negocio = extrair_domain_pack(cfg["domain_pack"], entidade, **nomes)
            brutas += funcionais
            fatos[entidade] = negocio
        consolidadas, cfs = consolidar(brutas, entidade)
        regras[entidade] = consolidadas
        conflitos += cfs
    return regras, conflitos, fatos


def validar(defs: dict[str, Any], raiz: Path = RAIZ_PADRAO, banco_url: str | None = None) -> list[str]:
    erros: list[str] = []
    clusters = _clusters(raiz)
    estados = {e.id: e for e in defs["estados"]}
    interfaces = {i.id for i in defs["interfaces"]}

    def ref_ok(dono: str, alvo: str, onde: str):
        cl_alvo = alvo.split(":")[0]
        if alvo not in estados:
            erros.append(f"{onde}: estado inexistente {alvo}")
        elif cl_alvo != dono and cl_alvo not in clusters[dono].get("depende_de", []):
            erros.append(f"{onde}: cluster {dono} referencia {cl_alvo} sem declarar dependência")

    for r in defs["receitas"]:
        for alvo in (r.origem, r.destino, *r.requer.values()):
            ref_ok(r.cluster, alvo, f"receita {r.id}")
        for p in r.passos:
            if p.interface not in interfaces:
                erros.append(f"receita {r.id}: interface inexistente {p.interface}")
    for e in defs["estados"]:
        if e.cluster not in clusters:
            erros.append(f"estado {e.id}: cluster não declarado")
    # alcançabilidade: todo estado com predicado deve ser alcançável a partir do 'inexistente' da sua entidade
    adj = defaultdict(list)
    for r in defs["receitas"]:
        adj[r.origem].append(r.destino)
    for e in defs["estados"]:
        if e.predicado is None or e.somente_garimpo:
            continue
        inicio = f"{e.id.split('.')[0]}.inexistente"
        vistos, fila = {inicio}, deque([inicio])
        while fila:
            for n in adj[fila.popleft()]:
                if n not in vistos:
                    vistos.add(n)
                    fila.append(n)
        if e.id not in vistos:
            erros.append(f"estado {e.id} inalcançável a partir de {inicio}")
    if banco_url:
        eng = create_engine(banco_url)
        for e in defs["estados"]:
            if e.predicado:
                try:
                    with eng.connect() as c:
                        c.execute(montar_select(eng, e.predicado, limite=1)).all()
                except Exception as ex:  # noqa: BLE001
                    erros.append(f"estado {e.id}: predicado não executa ({ex.__class__.__name__}: {ex})")
        eng.dispose()
    return erros


def vocabulario(defs: dict[str, Any], regras: dict[str, dict[str, RegraCampo]]) -> dict[str, Any]:
    ents: dict[str, Any] = {}
    for e in defs["estados"]:
        ent = ents.setdefault(e.entidade, {"estados": [], "operacoes": [], "campos": []})
        ent["estados"].append({"id": e.id, "descricao": e.descricao, "sinonimos": e.sinonimos})
    for r in defs["receitas"]:
        if r.operacao and r.operacao not in ents[r.entidade]["operacoes"]:
            ents[r.entidade]["operacoes"].append(r.operacao)
    for ent, rs in regras.items():
        ents.setdefault(ent, {"estados": [], "operacoes": [], "campos": []})["campos"] = sorted(rs)
    return {"entidades": ents, "variacoes": VARIACOES,
            "modos_execucao": ["somente_massa", "payload", "api", "tela"],
            "origens_expectativa": ["funcional", "tecnica", "premissa"]}


def construir(raiz: Path = RAIZ_PADRAO, banco_url: str = "sqlite:///demo/demo.db") -> dict[str, Any]:
    defs = carregar_definicoes(raiz)
    erros = validar(defs, raiz, banco_url)
    if erros:
        raise CatalogoInvalido("; ".join(erros))
    regras, conflitos, fatos = extrair_regras(defs["fontes"], banco_url, raiz)
    dist = {
        "hash": hash_fontes(raiz),
        "commit": _commit(),
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "clusters": _clusters(raiz),
        "estados": [e.model_dump() for e in defs["estados"]],
        "receitas": [r.model_dump() for r in defs["receitas"]],
        "interfaces": [i.model_dump() for i in defs["interfaces"]],
        "regras": {ent: {c: r.model_dump() for c, r in rs.items()} for ent, rs in regras.items()},
        "fatos_negocio": fatos,
        "conflitos": conflitos,
    }
    saida = raiz / "dist"
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "catalogo.json").write_text(json.dumps(dist, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (saida / "vocabulario.json").write_text(json.dumps(vocabulario(defs, regras), ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    hist = saida / "versoes"
    hist.mkdir(exist_ok=True)
    (hist / f"{dist['hash']}.json").write_text(json.dumps(dist, ensure_ascii=False, default=str), encoding="utf-8")
    (raiz / "conflitos.yaml").write_text(
        "# GERADO pelo build do catálogo. Conflitos NÃO são resolvidos automaticamente.\n"
        + yaml.safe_dump({"conflitos": conflitos}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return dist


def diff(a: dict, b: dict) -> dict[str, Any]:
    def ids(d, k):
        return {x["id"] for x in d[k]}
    out = {}
    for k in ("estados", "receitas", "interfaces"):
        out[k] = {"adicionados": sorted(ids(b, k) - ids(a, k)), "removidos": sorted(ids(a, k) - ids(b, k))}
    mud = []
    for ent, rs in b["regras"].items():
        for c, r in rs.items():
            antes = a["regras"].get(ent, {}).get(c)
            if antes and {k: v for k, v in antes.items() if k != "fontes"} != {k: v for k, v in r.items() if k != "fontes"}:
                mud.append(f"{ent}.{c}")
    out["regras_alteradas"] = mud
    return out


# ───────────────────────── consulta (usada pelo motor) ─────────────────────────

class Catalogo:
    def __init__(self, dados: dict[str, Any], raiz: Path = RAIZ_PADRAO, verificar_defasagem: bool = True):
        self.dados = dados
        self.raiz = raiz
        self.hash = dados["hash"]
        self.estados = {e["id"]: Estado(**e) for e in dados["estados"]}
        self.receitas = {r["id"]: Receita(**r) for r in dados["receitas"]}
        self.interfaces = {i["id"]: InterfaceApi(**i) for i in dados["interfaces"]}
        self.regras = {ent: {c: RegraCampo(**r) for c, r in rs.items()} for ent, rs in dados["regras"].items()}
        self.fatos_negocio = dados.get("fatos_negocio", {})
        self.conflitos = dados.get("conflitos", [])
        self.desatualizado = verificar_defasagem and hash_fontes(raiz) != self.hash
        self.saude = self._saude()

    @classmethod
    def carregar(cls, raiz: Path = RAIZ_PADRAO, verificar_defasagem: bool = True) -> "Catalogo":
        return cls(json.loads((raiz / "dist" / "catalogo.json").read_text(encoding="utf-8")), raiz, verificar_defasagem)

    def exigir_atualizado(self) -> None:
        if self.desatualizado:
            raise CatalogoDesatualizado("Fontes do catálogo mudaram desde o último build. Rode `massa catalogo build`.")

    # saúde das receitas (canários) — fora do hash, muda sem novo build
    def _saude(self) -> dict[str, str]:
        p = self.raiz / "dist" / "saude.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def marcar_saude(self, receita_id: str, status: str) -> None:
        self.saude[receita_id] = status
        (self.raiz / "dist" / "saude.json").write_text(json.dumps(self.saude, indent=2))

    def regra(self, entidade: str, campo: str) -> RegraCampo | None:
        return self.regras.get(entidade, {}).get(campo)

    def receita_da_operacao(self, entidade: str, operacao: str) -> Receita | None:
        return next((r for r in self.receitas.values() if r.entidade == entidade and r.operacao == operacao), None)

    def fato(self, ref: str) -> dict | None:
        for fs in self.fatos_negocio.values():
            for f in fs:
                if f["id"] == ref or f["referencia"] == ref:
                    return f
        for ent, rs in self.regras.items():
            for r in rs.values():
                for f in r.fontes:
                    if f.origem == "funcional" and (f.referencia == ref or f.referencia.endswith("#" + ref)):
                        return {"id": ref, "referencia": f.referencia, "texto": f.trecho}
        return None

    def caminho(self, origem: str, destino: str, evitar_quebradas: bool = True) -> list[Receita] | None:
        """Caminho de menor custo (Dijkstra simples) no grafo de receitas."""
        import heapq
        fila = [(0, origem, [])]
        vistos = set()
        while fila:
            custo, no, rota = heapq.heappop(fila)
            if no == destino:
                return rota
            if no in vistos:
                continue
            vistos.add(no)
            for r in self.receitas.values():
                if r.origem != no or not r.aprovada:
                    continue
                if evitar_quebradas and self.saude.get(r.id) == "quebrada":
                    continue
                heapq.heappush(fila, (custo + r.custo, r.destino, rota + [r]))
        return None

    def inexistente(self, entidade: str) -> str:
        return f"{entidade}.inexistente"
