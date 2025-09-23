@echo off
REM Change to project root (where this .bat sits)
cd /d "%~dp0"

REM Clean previous build artifacts
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Run PyInstaller using the properly configured spec file
python -m PyInstaller --clean Configurator.spec

pause
