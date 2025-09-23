@echo off
cd /d "%~dp0"

echo EliteMining Smart Uninstaller
echo ============================
echo.

:: Check if running from app subdirectory
if exist "smart_uninstaller.ps1" (
    set "PS_SCRIPT=%~dp0smart_uninstaller.ps1"
    set "INSTALL_PATH=%~dp0.."
) else (
    :: Running from main directory
    set "PS_SCRIPT=%~dp0app\smart_uninstaller.ps1"
    set "INSTALL_PATH=%~dp0"
)

:: Check if PowerShell script exists
if not exist "%PS_SCRIPT%" (
    echo Error: smart_uninstaller.ps1 not found!
    echo Expected location: %PS_SCRIPT%
    pause
    exit /b 1
)

:: Run PowerShell script with execution policy bypass
powershell.exe -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -InstallPath "%INSTALL_PATH%"

pause
