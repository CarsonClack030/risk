Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "[1/4] Installing backend build dependencies if needed"
python -m pip install -r backend/requirements-build.txt

Write-Host "[2/4] Building Python sidecar"
python backend/build_sidecar.py

Write-Host "[3/4] Building frontend"
npm run build:web

Write-Host "[4/4] Building Windows NSIS installer (.exe)"
npm run build:release:windows

Write-Host ""
Write-Host "Windows build ready."
Write-Host "NSIS installer: $root\src-tauri\target\release\bundle\nsis"
Write-Host "Release binary: $root\src-tauri\target\release\risk_studio.exe"
Write-Host "Sidecar: $root\backend\bin"
