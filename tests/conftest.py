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
