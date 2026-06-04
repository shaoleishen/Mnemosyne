#!/usr/bin/env bash
set -euo pipefail

skip_build="${1:-}"

echo "== Mnemosyne / KnowCran release verification =="

python --version
python -m pip install --upgrade pip
pip install -e ".[dev]"

echo "== pytest =="
pytest -v

echo "== coverage =="
pytest --cov=knowcran --cov-report=term-missing

echo "== compileall =="
python -m compileall knowcran tests

if [[ "$skip_build" != "--skip-build" ]]; then
  echo "== package build =="
  python -m pip install build twine
  python -m build
  twine check dist/*
fi

echo "== CLI smoke =="
knowcran --help >/dev/null
mnemosyne --help >/dev/null

echo "== local service import smoke =="
python -c "from knowcran.services.manager import probe_embedding_health, probe_mineru_health; print(probe_embedding_health, probe_mineru_health)"

if [[ -f uv.lock ]]; then
  if command -v uv >/dev/null 2>&1; then
    echo "== uv lock check =="
    uv lock --check
  else
    echo "== uv lock check skipped: uv not installed =="
  fi
fi

echo "== release verification complete =="
