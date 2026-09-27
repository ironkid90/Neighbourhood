@echo off
setlocal
set "ROOT=%~dp0.."
if defined NHOOD_PYTHON (
  "%NHOOD_PYTHON%" "%ROOT%\tools\nhood.py" %*
  exit /b %ERRORLEVEL%
)
py -3 "%ROOT%\tools\nhood.py" %* 2>nul
if not errorlevel 1 exit /b %ERRORLEVEL%
python "%ROOT%\tools\nhood.py" %*
exit /b %ERRORLEVEL%
