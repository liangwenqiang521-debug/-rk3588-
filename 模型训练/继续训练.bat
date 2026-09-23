@echo off
REM 从断点续训 NEU 增强模型（neu_yolo11n_aug，已训 17/60 轮）
REM 双击本文件即可在上位机同款 Python 环境下续训，自动从 last.pt 接着跑到 60 轮
REM 注意：请勿额外加 --epochs 参数，轮数由该 run 的原始 args.yaml(epochs=60) 决定

cd /d %~dp0
REM 优先用本目录的 GPU 训练环境（CUDA 版 torch，自动吃 RTX 5060），否则回退
set PY=%~dp0venv\Scripts\python.exe
if not exist "%PY%" set PY=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe
if not exist "%PY%" set PY=python

"%PY%" train.py --resume neu_yolo11n_aug
pause
