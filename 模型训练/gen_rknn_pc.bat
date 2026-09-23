@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo  RKNN .rknn 本机生成向导  (Windows PC)
echo  模型训练目录: %CD%
echo ============================================================
echo.

REM ---------- 1. 检查 WSL2 ----------
wsl --status >nul 2>&1
if errorlevel 1 (
  echo [X] 未检测到可用的 WSL2 分发版。
  echo.
  echo ===== 方案A (推荐, 仅需管理员一次) =====
  echo   1. 右键"终端"或"PowerShell" -> 以管理员身份运行
  echo   2. 执行:  wsl --install -d Ubuntu
  echo   3. 重启电脑，开机后按提示设置 Ubuntu 用户名/密码
  echo   4. 重新双击本脚本
  echo.
  echo ===== 方案B (无需管理员, 用已安装的 VMware) =====
  echo   1. 下载 Ubuntu 22.04 ISO: https://ubuntu.com/download/desktop
  echo   2. 打开 VMware -> 新建虚拟机 -> 选该 ISO
  echo      安装时勾选 "OpenSSH Server"，用户名/密码记好
  echo   3. 启动虚拟机，执行:
  echo        sudo apt update -y
  echo        sudo apt install -y python3-venv python3-pip git
  echo   4. 把本文件夹(模型训练/) 拷进虚拟机任意目录
  echo   5. 在虚拟机里:  cd 模型训练  &&  bash setup_rknn_env.sh
  echo.
  echo  本脚本完成上述任一环境后即可自动跑转换。
  echo.
  pause
  exit /b 1
)

REM ---------- 2. 取得 Windows 目录对应的 WSL 路径 ----------
for /f "delims=" %%p in ('wsl wslpath -a "%CD%"') do set "WINWSL=%%p"
echo [OK] 检测到 WSL2: %WINWSL%
echo.

REM ---------- 3. 拷进 WSL home -> 转换 -> 拷回 .rknn ----------
echo [..] 正在把模型文件拷入 Linux 并生成 .rknn (首次需联网下载依赖, 请耐心) ...
echo.
wsl bash -lc "set -e; rm -rf ~/rknn_work; mkdir -p ~/rknn_work; cp -r \"%WINWSL%\"/* ~/rknn_work/; cd ~/rknn_work; bash ./setup_rknn_env.sh; echo '--- copy back ---'; cp -v ~/rknn_work/best_neu_yolo11n_640.rknn \"%WINWSL%\"/ 2>/dev/null || true; cp -v ~/rknn_work/best.rknn \"%WINWSL%\"/ 2>/dev/null || true"

echo.
echo ============================================================
echo  完成。请检查本文件夹是否出现:
echo    - best_neu_yolo11n_640.rknn   (NEU 6 类新模型, 640, 本次目标)
echo    - best.rknn                  (合成 4 类, 可选)
echo ============================================================
echo  如需只转 4 类(最快, 不装 torch): 在 WSL 里 bash setup_rknn_env.sh --four-only
echo.
pause
