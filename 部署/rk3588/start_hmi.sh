#!/bin/sh
# ============================================================
# RK3588 板端启动「工业缺陷检测上位机」（PySide6 垫片版）
#
# 依赖：
#   - 已离线安装 PySide6-Essentials + shiboken6 + psutil + pyserial
#     （见 wheels_aarch64，安装命令见 README）
#   - 本目录含 qt_shim/（PyQt5→PySide6 兼容垫片）与全部上位机 .py
#   - 本机 board_server.py 已在 :9000 提供 NPU 推理/状态（S99board 自启）
#
# 用法：
#   ./start_hmi.sh                # 默认 eglfs（HDMI 屏）
#   QT_QPA_PLATFORM=linuxfb ./start_hmi.sh   # 无 GPU/软渲染回退
#   QT_QPA_PLATFORM=offscreen ./start_hmi.sh # 无显示（自动化/调试）
# ============================================================
set -e

HMI_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$HMI_DIR"

# 1) PyQt5→PySide6 兼容垫片优先于系统任何 PyQt5
export PYTHONPATH="$HMI_DIR/qt_shim:$PYTHONPATH"

# 2) Qt 平台插件：HDMI 接 eglfs；无 GPU 用 linuxfb；调试用 offscreen
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-eglfs}"

# 3) 指向 PySide6 自带平台插件目录（含 eglfs/linuxfb/offscreen）
PLUGIN_DIR=$(python3 -c "import os, PySide6; print(os.path.join(os.path.dirname(PySide6.__file__), 'Qt', 'plugins'))" 2>/dev/null || true)
if [ -n "$PLUGIN_DIR" ]; then
    export QT_QPA_PLATFORM_PLUGIN_PATH="$PLUGIN_DIR"
fi

# 4) 字体（板子可能没有，Qt 会回退到默认，不影响功能）
export QT_QPA_FONTDIR="${QT_QPA_FONTDIR:-/usr/share/fonts}"

# 5) 抑制 Qt 噪音日志
export QT_LOGGING_RULES="${QT_LOGGING_RULES:-*.warning=false}"

echo "[start_hmi] PYTHONPATH=$PYTHONPATH"
echo "[start_hmi] QT_QPA_PLATFORM=$QT_QPA_PLATFORM"
echo "[start_hmi] plugin=$PLUGIN_DIR"

exec python3 "$HMI_DIR/main.py" "$@"
