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
    python -m pip install build twine
    python -m build
    twine check dist/*
}

Write-Host "== CLI smoke =="
knowcran --help | Out-Null
mnemosyne --help | Out-Null

Write-Host "== local service import smoke =="
python -c "from knowcran.services.manager import probe_embedding_health, probe_mineru_health; print(probe_embedding_health, probe_mineru_health)"

if (Test-Path "uv.lock") {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        Write-Host "== uv lock check =="
        uv lock --check
    } else {
        Write-Host "== uv lock check skipped: uv not installed =="
    }
}

Write-Host "== release verification complete =="
