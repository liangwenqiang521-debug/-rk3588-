@echo off
REM NEU-DET 真实钢材缺陷模型 · GPU 续训（热启动 + 延长 + 增强）
REM 依赖 venv_cuda（CUDA torch，对应 RTX 5060）。若无独显会自动回退 CPU。
cd /d %~dp0
set PY=%~dp0venv_cuda\Scripts\python.exe
if not exist "%PY%" set PY=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe
if not exist "%PY%" set PY=python

"%PY%" continue_neu.py
pause
