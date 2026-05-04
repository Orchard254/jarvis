@echo off
echo ==============================================
echo   Personal Assistant Setup
echo ==============================================

REM Ensure we're in the script directory
cd /d %~dp0

REM Run PowerShell script with execution policy bypass
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1

echo.
echo Done.
pause