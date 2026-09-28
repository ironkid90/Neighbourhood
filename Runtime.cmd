@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\runtime.ps1" -InstallMissingTools %*
exit /b %ERRORLEVEL%
