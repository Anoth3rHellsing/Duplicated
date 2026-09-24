@echo off
title Eliminador de Duplicados
echo Verificando dependencias...
python -m pip show customtkinter >nul 2>&1
if errorlevel 1 (
    echo Instalando customtkinter...
    python -m pip install customtkinter
)
echo Iniciando herramienta...
python "%~dp0dedup_tool.py"
pause