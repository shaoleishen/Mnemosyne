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
  python -m pip install build
  python -m build
fi

echo "== release verification complete =="
