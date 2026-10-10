$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --onefile --windowed --name OsuRecommender `
  --icon "assets\icon.ico" --add-data "assets;assets" `
  --collect-all customtkinter --collect-all rosu_pp_py app.py
Write-Host "Listo: dist\OsuRecommender.exe"
