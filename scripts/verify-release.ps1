param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

Write-Host "== Mnemosyne / KnowCran release verification =="

python --version
python -m pip install --upgrade pip
pip install -e ".[dev]"

Write-Host "== pytest =="
pytest -v

Write-Host "== coverage =="
pytest --cov=knowcran --cov-report=term-missing

Write-Host "== compileall =="
python -m compileall knowcran tests

if (-not $SkipBuild) {
    Write-Host "== package build =="
    python -m pip install build
    python -m build
}

Write-Host "== release verification complete =="
