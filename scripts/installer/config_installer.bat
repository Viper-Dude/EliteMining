@echo off
setlocal enabledelayedexpansion

:: Simple config migration for systems without Python
:: Args: %1 = source config, %2 = target directory

set "source_config=%~1"
set "target_dir=%~2"
set "target_config=%target_dir%\config.json"

if not exist "%target_dir%" mkdir "%target_dir%"

:: Check if target config exists
if exist "%target_config%" (
    echo Existing config found - checking compatibility...
    
    :: Simple check for version field
    findstr /C:"config_version" "%target_config%" >nul 2>&1
    if errorlevel 1 (
        echo Config needs migration - backing up existing config
        copy "%target_config%" "%target_config%.backup" >nul 2>&1
        echo Installing updated config with migration support
        copy "%source_config%" "%target_config%" >nul 2>&1
        exit /b 3
    ) else (
        echo Config appears compatible - preserving existing settings
        exit /b 2
    )
) else (
    echo No existing config - installing fresh config
    copy "%source_config%" "%target_config%" >nul 2>&1
    exit /b 0
)