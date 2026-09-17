$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Criando ambiente virtual em .venv..."
    python -m venv .venv
}

Write-Host "Atualizando pip..."
.\.venv\Scripts\python.exe -m pip install --upgrade pip

Write-Host "Instalando dependencias..."
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "Instalando Chromium do Playwright..."
.\.venv\Scripts\python.exe -m playwright install chromium

Write-Host ""
Write-Host "Ambiente pronto. Para ativar manualmente:"
Write-Host ".\.venv\Scripts\Activate.ps1"
