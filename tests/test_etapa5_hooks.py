import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(".github/hooks/scripts")


def rodar(script, dados, ativo=True, *args):
    env = {**os.environ, "MASSA_HOOKS": "on" if ativo else "off"}
    p = subprocess.run([sys.executable, str(SCRIPTS / script), *args], input=json.dumps(dados), text=True,
                       capture_output=True, env=env, timeout=30)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else None


def test_configuracao_de_hooks_valida():
    cfg = json.loads(Path(".github/hooks/massa.json").read_text())
    assert cfg["version"] == 1
    assert {"sessionStart", "userPromptSubmitted", "preToolUse", "postToolUse", "subagentStop",
            "sessionEnd", "errorOccurred"} <= set(cfg["hooks"])
    for lista in cfg["hooks"].values():
        for h in lista:
            assert (Path(h["bash"].split()[1])).exists()


def test_hooks_inativos_por_padrao():
    assert rodar("isolar_ferramentas.py", {"toolName": "bash", "toolArgs": "{}"}, ativo=False) is None


@pytest.mark.parametrize("nome,args,negado", [
    ("bash", {"command": "rm -rf /"}, True),
    ("run_in_terminal", {"command": "sqlplus"}, True),
    ("massa/planejar_suite", {"suite": {}}, False),
    ("mcp__massa__executar_plano", {"plano_id": "x"}, False),
    ("read", {"path": "catalogo/clusters.yaml"}, False),
    ("edit", {"path": "catalogo/garantias/estados.yaml"}, True),
    ("edit", {"path": "catalogo/propostas/nova.yaml"}, False),
    ("create", {"path": "saida/notas.md"}, False),
    ("web_fetch", {"url": "http://x"}, True),
])
def test_isolamento(nome, args, negado):
    r = rodar("isolar_ferramentas.py", {"toolName": nome, "toolArgs": json.dumps(args)})
    assert (r is not None and r["permissionDecision"] == "deny") == negado


def test_sanitizacao_de_prompt():
    r = rodar("sanitizar_prompt.py", {"prompt": "bloquear garantia do cliente 529.982.247-25, contrato 12345678"})
    assert r["decision"] == "block" and "<DOCUMENTO>" in r["reason"] and "<NUMERO_CONTRATO>" in r["reason"]
    assert rodar("sanitizar_prompt.py", {"prompt": "bloquear garantia com motivo JUD"}) is None


def test_validacao_da_proposta_do_investigador(tmp_path, monkeypatch):
    pasta = Path("catalogo/propostas")
    ruim = pasta / "zz-teste-ruim.yaml"
    ruim.write_text("tipo: estado\nproposta: {id: x}\nevidencias: [{arquivo: a.cbl}]\n")
    try:
        r = rodar("validar_proposta.py", {"agentName": "investigador-catalogo"})
        assert r["decision"] == "block" and "linha" in r["reason"]
        ruim.write_text("tipo: estado\nproposta: {id: x}\nevidencias: [{arquivo: a.cbl, linha: 10, trecho: t}]\n")
        assert rodar("validar_proposta.py", {"agentName": "investigador-catalogo"}) is None
    finally:
        ruim.unlink()


def test_session_start_injeta_contexto():
    r = rodar("session_start.py", {})
    assert "Fábrica de Massa" in r["additionalContext"]
