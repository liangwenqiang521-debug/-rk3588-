@echo off
cd /d "%~dp0"
set "PY=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo Starting HMI with:
echo   %PY%
"%PY%" -c "import torch; torch.zeros(1); import PyQt5" >nul 2>&1
if errorlevel 1 goto DEPSFAIL
"%PY%" main.py
if errorlevel 1 goto RUNFAIL
exit /b 0
:DEPSFAIL
echo [ERROR] Missing dependencies (PyQt5/torch) or DLL conflict.
echo Fix: pip install -r requirements.txt
pause
exit /b 1
:RUNFAIL
echo [ERROR] HMI exited with code %errorlevel%.
pause
exit /b 1
