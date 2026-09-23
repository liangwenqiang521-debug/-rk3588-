@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:\Users\21191\.workbuddy\binaries\python\envs\default\Scripts\python.exe
if not exist "%PY%" set PY=python
"%PY%" "串口诊断.py"
pause
