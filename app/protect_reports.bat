@echo off
REM EliteMining Reports Protection Script
REM This script should be called by the installer to protect user data

setlocal EnableDelayedExpansion

REM Get the installation directory from command line or use current directory
if "%~1"=="" (
    set "INSTALL_DIR=%CD%"
) else (
    set "INSTALL_DIR=%~1"
)

REM Get the action (backup or restore)
set "ACTION=%~2"
if "%ACTION%"=="" set "ACTION=backup"

echo ========================================
echo EliteMining Reports Protection
echo ========================================
echo Installation Directory: %INSTALL_DIR%
echo Action: %ACTION%
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Warning: Python not found. Using manual backup method...
    goto :manual_backup
)

REM Use Python script for advanced protection
echo Using Python-based protection...
cd /d "%INSTALL_DIR%"

if /i "%ACTION%"=="backup" (
    echo Creating backup of Reports folder...
    python app\reports_protector.py backup
    if errorlevel 1 (
        echo Python backup failed, trying manual method...
        goto :manual_backup
    )
    echo ✅ Reports backup completed successfully
    goto :end
)

if /i "%ACTION%"=="restore" (
    echo Restoring Reports folder from backup...
    python app\reports_protector.py restore
    if errorlevel 1 (
        echo Python restore failed, trying manual method...
        goto :manual_restore
    )
    echo ✅ Reports restore completed successfully
    goto :end
)

if /i "%ACTION%"=="merge" (
    echo Merging Reports folder with backup...
    python app\reports_protector.py merge
    if errorlevel 1 (
        echo Python merge failed
        goto :end
    )
    echo ✅ Reports merge completed successfully
    goto :end
)

goto :end

:manual_backup
echo.
echo ----------------------------------------
echo Manual Backup Method
echo ----------------------------------------

set "REPORTS_DIR=%INSTALL_DIR%\app\Reports"
set "BACKUP_DIR=%TEMP%\EliteMining_Reports_Backup_%DATE:~-4%%DATE:~4,2%%DATE:~7,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "BACKUP_DIR=%BACKUP_DIR: =0%"

if not exist "%REPORTS_DIR%" (
    echo No Reports folder found to backup
    goto :end
)

echo Creating backup directory: %BACKUP_DIR%
mkdir "%BACKUP_DIR%" 2>nul

echo Copying Reports folder...
xcopy "%REPORTS_DIR%" "%BACKUP_DIR%\Reports\" /E /I /H /Y >nul 2>&1
if errorlevel 1 (
    echo ❌ Failed to create backup
    goto :end
)

REM Save backup location to a file
echo %BACKUP_DIR% > "%INSTALL_DIR%\reports_backup_location.txt"
echo ✅ Manual backup completed
echo Backup location: %BACKUP_DIR%
echo Backup location saved to: %INSTALL_DIR%\reports_backup_location.txt
goto :end

:manual_restore
echo.
echo ----------------------------------------
echo Manual Restore Method
echo ----------------------------------------

set "BACKUP_LOCATION_FILE=%INSTALL_DIR%\reports_backup_location.txt"
if exist "%BACKUP_LOCATION_FILE%" (
    set /p BACKUP_DIR=<"%BACKUP_LOCATION_FILE%"
    echo Found backup location: !BACKUP_DIR!
) else (
    echo ❌ No backup location file found
    echo Please manually restore Reports folder from your backup
    goto :end
)

set "BACKUP_REPORTS=!BACKUP_DIR!\Reports"
if not exist "!BACKUP_REPORTS!" (
    echo ❌ Backup folder not found: !BACKUP_REPORTS!
    goto :end
)

set "REPORTS_DIR=%INSTALL_DIR%\app\Reports"

REM Create app directory if it doesn't exist
if not exist "%INSTALL_DIR%\app" mkdir "%INSTALL_DIR%\app"

echo Restoring Reports folder...
xcopy "!BACKUP_REPORTS!" "%REPORTS_DIR%\" /E /I /H /Y >nul 2>&1
if errorlevel 1 (
    echo ❌ Failed to restore backup
    goto :end
)

REM Clean up backup location file
del "%BACKUP_LOCATION_FILE%" 2>nul

echo ✅ Manual restore completed
goto :end

:end
echo.
echo Reports protection script completed.
pause
