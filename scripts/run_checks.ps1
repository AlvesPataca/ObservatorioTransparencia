$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Ambiente .venv nao encontrado. Rode primeiro: .\scripts\bootstrap.ps1"
}

Write-Host "Inspecionando portais..."
.\.venv\Scripts\python.exe scripts\inspect_portals.py

Write-Host ""
Write-Host "Rodando coleta MVP..."
.\.venv\Scripts\python.exe scripts\collect_mvp.py

Write-Host ""
Write-Host "Inspecionando portais com navegador..."
.\.venv\Scripts\python.exe scripts\inspect_with_playwright.py

Write-Host ""
Write-Host "Rodando testes..."
.\.venv\Scripts\python.exe -m pytest

Write-Host ""
Write-Host "Tudo certo."
