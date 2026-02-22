# PowerShell instalační skript pro Flexi-Bee AI
# Spustit pravým tlačítkem -> Run with PowerShell

$ErrorActionPreference = "Stop"

Write-Host "--- Instalace Flexi-Bee AI pro Windows ---" -ForegroundColor Cyan

# 1. Kontrola a instalace systémových nástrojů přes Winget
function Install-WithWinget {
    param($id, $name)
    Write-Host "Kontrola nástroje: $name ($id)..."
    try {
        & winget list --id $id | Out-Null
        Write-Host " - $name je již nainstalován." -ForegroundColor Green
    } catch {
        Write-Host " - Instalace $name ($id)..." -ForegroundColor Yellow
        & winget install -e --id $id --accept-source-agreements --accept-package-agreements
    }
}

# Instalace Pythonu, Gitu a NAPS2 (skener)
Install-WithWinget "Python.Python.3.11" "Python 3.11"
Install-WithWinget "Git.Git" "Git"
Install-WithWinget "NAPS2.NAPS2" "NAPS2 (Scanner)"

# 2. Nastavení Python virtuálního prostředí
Write-Host "`nNastavení Python virtuálního prostředí..." -ForegroundColor Cyan

# Detekce Python příkazu (py vs python)
$pythonCmd = "python"
try {
    & py --version | Out-Null
    $pythonCmd = "py"
} catch {
    try {
        & python --version | Out-Null
    } catch {
        Write-Host "Chyba: Python nebyl nalezen. Zkuste restartovat PowerShell." -ForegroundColor Red
        exit
    }
}

if (-not (Test-Path "venv")) {
    Write-Host "Vytváření virtuálního prostředí (venv) pomocí $pythonCmd..."
    & $pythonCmd -m venv venv
}

Write-Host "Instalace Python závislostí z requirements.txt..."
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\pip.exe install -r requirements.txt

# 3. Konfigurace .env
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Write-Host "Vytváření souboru .env z .env.example..."
        Copy-Item ".env.example" ".env"
        Write-Host "DŮLEŽITÉ: Nezapomeňte doplnit svůj GOOGLE_API_KEY do souboru .env!" -ForegroundColor Red
    } else {
        Write-Host "Upozornění: .env.example nebyl nalezen, .env nebylo možné vytvořit." -ForegroundColor Yellow
    }
}

# 4. Vytvoření spouštěcího souboru (Batch script)
Write-Host "`nVytváření spouštěcího souboru run_app.bat..." -ForegroundColor Cyan
$batContent = @"
@echo off
echo Spousteni Flexi-Bee AI...
.\venv\Scripts\python.exe run.py
pause
"@
$batContent | Out-File -FilePath "run_app.bat" -Encoding ascii

Write-Host "`n--- INSTALACE DOKONČENA ---" -ForegroundColor Green
Write-Host "Nyní můžete aplikaci spustit dvojklikem na 'run_app.bat' v tomto adresáři."
Write-Host "Nezapomeňte nejprve vložit API klíč do souboru .env!" -ForegroundColor Yellow
pause
