PY ?= python3
setup:
	$(PY) -m pip install -e ".[dev]"
test:
	$(PY) -m pytest
demo-reset:
	$(PY) -m demo.banco --reset
demo-up: demo-reset
	$(PY) -m uvicorn demo.api:app --port 8765
catalogo:
	$(PY) -m massa.cli catalogo build
