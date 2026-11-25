import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)


@pytest.fixture
def db_url(tmp_path):
    from demo.banco import resetar
    url = f"sqlite:///{tmp_path}/demo.db"
    resetar(url)
    return url


@pytest.fixture
def eventos(tmp_path):
    from massa.eventos import RegistroEventos
    return RegistroEventos(tmp_path / "motor.db")


@pytest.fixture
def api(db_url):
    from fastapi.testclient import TestClient
    from demo.api import criar_app
    app = criar_app(db_url, propagacao_s=0.4)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def catalogo_construido():
    from demo.banco import resetar
    from massa import catalogo as cat
    if not Path("demo/demo.db").exists():
        resetar("sqlite:///demo/demo.db")
    dist = Path("catalogo/dist/catalogo.json")
    if not dist.exists() or cat.Catalogo.carregar().desatualizado:
        cat.construir(Path("catalogo"), "sqlite:///demo/demo.db")


@pytest.fixture
def ctx(db_url, eventos, api, tmp_path):
    from sqlalchemy import create_engine
    from massa.catalogo import Catalogo
    from massa.motor.contexto import Contexto
    return Contexto(catalogo=Catalogo.carregar(), eventos=eventos,
                    engine=create_engine(db_url, connect_args={"check_same_thread": False}),
                    http=api, espera_base_s=0.01, saida=tmp_path / "saida", navegador="/usr/bin/google-chrome")


@pytest.fixture
def servidor(db_url):
    """API demo em um servidor real (necessário para roteiros de tela)."""
    import socket
    import threading
    import time
    import uvicorn
    from demo.api import criar_app
    s = socket.socket(); s.bind(("127.0.0.1", 0)); porta = s.getsockname()[1]; s.close()
    srv = uvicorn.Server(uvicorn.Config(criar_app(db_url, propagacao_s=0.4), host="127.0.0.1", port=porta,
                                        log_level="error"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    while not srv.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{porta}"
    srv.should_exit = True
    t.join(timeout=5)
