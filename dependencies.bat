@echo off
setlocal
cd /d "%~dp0"
set "HERE=%~dp0"
title osu! Recommender - Dependencies
echo ================================================
echo   osu! Recommender - instalacion de dependencias
echo ================================================
echo.

set "PY="
python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    py -3 --version >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    echo [ERROR] No se encontro Python.
    echo Instalalo desde https://www.python.org/downloads/ y marca "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

echo Python detectado:
%PY% --version
echo.

echo [1/3] Actualizando pip...
%PY% -m pip install --upgrade pip
echo.

echo [2/3] Instalando paquetes (requests, python-dotenv, rosu-pp-py, pillow, PySide6, customtkinter)...
echo      PySide6 pesa varios cientos de MB: puede tardar unos minutos.
%PY% -m pip install requests python-dotenv rosu-pp-py pillow PySide6 customtkinter
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion.
    echo Si el error menciona rosu-pp-py o PySide6, prueba con Python 3.12 o 3.13.
    echo.
    pause
    exit /b 1
)
echo.

echo [3/3] Verificando...
%PY% -c "import requests, dotenv, rosu_pp_py, PIL, PySide6, customtkinter; print('Todo OK')"
if errorlevel 1 (
    echo.
    echo [ERROR] Alguno de los paquetes no se pudo importar.
    echo.
    pause
    exit /b 1
)
%PY% -c "import sys; open('.python_path.txt','w').write(sys.executable)"

echo.
echo Instalacion completada. Ya puedes abrir el programa con o!br.vbs
echo.
choice /c SN /m "Crear acceso directo en el escritorio (S/N)"
if errorlevel 2 goto fin

if not exist "%HERE%assets\icon.ico" (
    if exist "%HERE%assets\icon.png" (
        echo Creando icono desde assets\icon.png ...
        %PY% -c "from PIL import Image; Image.open(r'%HERE%assets\icon.png').convert('RGBA').save(r'%HERE%assets\icon.ico', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
    )
)
wscript.exe "%HERE%create_DA.vbs"

:fin
echo.
pause
endlocal
