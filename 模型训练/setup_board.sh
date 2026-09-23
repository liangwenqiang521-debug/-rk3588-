#!/usr/bin/env bash
# ==============================================================================
#  RK3588 板端一键部署脚本
#  作用：在 RK3588 开发板（Debian/Ubuntu 官方系统）上装好 board_infer.py 的
#        全部依赖，并把推理结果服务拉起来，供 Windows 上位机通过 TCP/串口接收。
#
#  用法（在板子上执行）：
#     把整个「模型训练/」目录拷到板子（U盘 / scp / rsync），然后：
#         cd 模型训练
#         chmod +x setup_board.sh
#         ./setup_board.sh
#
#  可选参数：
#      --model best_neu_yolo11n_aug.rknn   指定 .rknn 模型（默认自动找）
#      --port 9000                         TCP 服务端口（默认 9000）
#      --serial /dev/ttyS0                 同时经串口推送（不填则只用 TCP）
#      --source 0                          数据源：0=摄像头 / 图片目录路径
#      --no-autostart                      不注册开机自启
#      --no-venv                           不用 venv，直接装进系统 Python（默认用 venv）
# ==============================================================================
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
err()  { echo -e "${RED}❌ $*${NC}"; }

# ---------------- 默认参数 ----------------
MODEL=""; PORT=9000; SERIAL=""; SOURCE="0"; AUTOSTART=1; USE_VENV=1
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)        MODEL="$2";    shift 2 ;;
        --port)         PORT="$2";     shift 2 ;;
        --serial)       SERIAL="$2";   shift 2 ;;
        --source)       SOURCE="$2";   shift 2 ;;
        --no-autostart) AUTOSTART=0;   shift 1 ;;
        --no-venv)      USE_VENV=0;    shift 1 ;;
        -h|--help)      awk 'NR>1{ if(/^# =====/){c++; if(c==2){print; exit}} if(c<2) print }' "$0" \
                          | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) warn "未知参数: $1"; shift 1 ;;
    esac
done

echo "=============================================================================="
echo "  RK3588 板端一键部署"
echo "=============================================================================="

# ---------------- 1. 环境检查 ----------------
echo
echo "[1/6] 检查系统环境..."
ARCH=$(uname -m)
echo "      架构: $ARCH"
if [[ "$ARCH" != "aarch64" ]]; then
    warn "  当前不是 aarch64（RK3588 应为 aarch64）—— 仍继续，但 NPU 不可用"
fi

# 判断是不是 RK3588
if [ -d /sys/class/rknpu ]; then
    ok "  检测到 RKNPU 设备节点 /sys/class/rknpu —— 这是 Rockchip NPU 平台"
elif grep -qi "rk3588" /proc/device-tree/model 2>/dev/null; then
    ok "  设备树型号: $(cat /proc/device-tree/model 2>/dev/null | tr -d '\0')"
else
    warn "  未检测到 RKNPU —— 可能是普通 x86 机器或驱动未加载，推理会失败"
fi

PY=python3
if ! command -v $PY >/dev/null 2>&1; then
    err "  未找到 python3"; exit 1
fi
echo "      Python: $($PY --version 2>&1)"

# ---------------- 2. 找 .rknn 模型 ----------------
echo
echo "[2/6] 查找 .rknn 模型..."
if [ -z "$MODEL" ]; then
    # 优先 NEU 六类真实模型
    for cand in best_neu_yolo11n_aug.rknn best.rknn; do
        if [ -f "$cand" ]; then MODEL="$cand"; break; fi
    done
fi
if [ -z "$MODEL" ] || [ ! -f "$MODEL" ]; then
    err "  未找到 .rknn 模型！"
    echo "      RK3588 不能跑 .pt/.onnx，必须先转成 .rknn："
    echo "        在 Ubuntu/WSL2 上执行: bash setup_rknn_env.sh"
    echo "        然后把生成的 *.rknn 拷到本目录"
    exit 1
fi
ok "  模型: $MODEL  ($(du -h "$MODEL" | cut -f1))"

# ---------------- 3. 建 venv ----------------
VENV_DIR="venv_board"
if [ "$USE_VENV" -eq 1 ]; then
    echo
    echo "[3/6] 准备 Python 虚拟环境..."
    if [ ! -d "$VENV_DIR" ]; then
        if $PY -m venv "$VENV_DIR" 2>/dev/null; then
            ok "  已创建 $VENV_DIR"
        else
            warn "  venv 创建失败（可能缺 python3-venv），尝试 --no-venv 或执行："
            echo "      sudo apt install -y python3-venv"
            exit 1
        fi
    else
        ok "  复用已有 $VENV_DIR"
    fi
    PY="$PWD/$VENV_DIR/bin/python3"
    PIP="$PWD/$VENV_DIR/bin/pip"
    $PY -m pip install --upgrade pip -q 2>/dev/null || true
else
    echo
    echo "[3/6] 使用系统 Python（未隔离）"
    PIP="pip3"
fi

# ---------------- 4. 装依赖 ----------------
echo
echo "[4/6] 安装依赖..."

# 4.1 rknn-toolkit-lite2（板端推理运行时）
echo "      → rknn-toolkit-lite2（NPU 运行时）"
if $PY -c "import rknnlite" 2>/dev/null; then
    ok "    已安装"
else
    INSTALLED=0
    # 优先用同目录下的 whl（离线场景）
    for whl in rknn_toolkit_lite2-*.whl; do
        [ -f "$whl" ] || continue
        echo "    找到本地 whl: $whl"
        $PIP install "$whl" -q && INSTALLED=1 && break
    done
    if [ "$INSTALLED" -eq 0 ]; then
        echo "    未找到本地 whl，尝试从官方仓库下载..."
        warn "    rknn-toolkit-lite2 需从 Rockchip 官方获取，若下载失败请手动下载 whl 放到本目录："
        echo "        https://github.com/airockchip/rknn-toolkit2/tree/master/rknn-toolkit-lite2/packages"
        $PIP install rknn_toolkit_lite2 -q 2>/dev/null && INSTALLED=1 || true
    fi
    if $PY -c "import rknnlite" 2>/dev/null; then
        ok "    rknnlite 导入成功"
    else
        warn "    rknnlite 未装上 —— board_infer.py 将无法做 NPU 推理"
    fi
fi

# 4.2 OpenCV / numpy / pyserial
echo "      → opencv-python / numpy / pyserial"
$PIP install -q numpy 2>/dev/null || warn "    numpy 安装失败"
if $PY -c "import cv2" 2>/dev/null; then
    ok "    cv2 已可用"
else
    # 板子上 opencv-python 编译慢，优先用系统包
    if command -v apt-get >/dev/null 2>&1; then
        echo "    尝试 apt 装 python3-opencv（比 pip 编译快很多）..."
        sudo apt-get install -y -q python3-opencv 2>/dev/null \
            && echo "     （venv 需 --system-site-packages 才能用到系统 opencv）" \
            || $PIP install -q opencv-python-headless 2>/dev/null \
            || warn "    opencv 安装失败，请手动处理"
    else
        $PIP install -q opencv-python-headless 2>/dev/null || warn "    opencv 安装失败"
    fi
fi
$PIP install -q pyserial 2>/dev/null || warn "    pyserial 安装失败"

# ---------------- 5. 生成启动脚本 ----------------
echo
echo "[5/6] 生成启动脚本 start_board.sh..."
CMD_ARGS="--model $MODEL --source $SOURCE --tcp-port $PORT"
[ -n "$SERIAL" ] && CMD_ARGS="$CMD_ARGS --serial $SERIAL"

cat > start_board.sh << EOF
#!/usr/bin/env bash
# 自动生成于 $(date '+%Y-%m-%d %H:%M:%S')
cd "\$(dirname "\$0")"
$PY board_infer.py $CMD_ARGS
EOF
chmod +x start_board.sh
ok "  已生成 start_board.sh"
echo "     内容: $PY board_infer.py $CMD_ARGS"

# ---------------- 6. 开机自启（可选） ----------------
echo
echo "[6/6] 开机自启..."
if [ "$AUTOSTART" -eq 1 ] && command -v systemctl >/dev/null 2>&1; then
    SVC=/etc/systemd/system/defect-board.service
    WD=$PWD
    USER_NAME=$(whoami)
    sudo tee "$SVC" > /dev/null << EOF
[Unit]
Description=RK3588 Defect Detection Board Service
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$WD
ExecStart=$WD/start_board.sh
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable defect-board.service >/dev/null 2>&1
    ok "  已注册 systemd 服务 defect-board（开机自启）"
    echo "     手动控制："
    echo "       sudo systemctl start   defect-board   # 立即启动"
    echo "       sudo systemctl stop    defect-board   # 停止"
    echo "       sudo systemctl status  defect-board   # 查看状态"
    echo "       journalctl -u defect-board -f         # 看实时日志"
else
    warn "  跳过自启（--no-autostart 或无 systemd）"
fi

# ---------------- 完成 ----------------
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "=============================================================================="
ok " 部署完成！"
echo "=============================================================================="
echo
echo " 板子 IP        : ${IP:-（未获取到，请 ip addr 查看）}"
echo " TCP 服务端口   : $PORT"
echo " 模型           : $MODEL"
[ -n "$SERIAL" ] && echo " 串口           : $SERIAL"
echo
echo " 现在启动服务："
echo "     ./start_board.sh"
echo
echo " 然后回到 Windows 上位机："
echo "     1) 确认 PC 与板子在同一网段（如 192.168.1.x）"
echo "     2) NPU 监控页 → 数据来源「板端TCP」→ 地址 ${IP:-<板子IP>} → 端口 $PORT → 连接"
echo "     3) 检测页     → 边缘模式「网络(TCP)」→ 同上 → 启动"
echo
echo " 若 PC 网段与板子不同，用网线直连后给 PC 设同段静态 IP，例如："
echo "     板子: 192.168.1.20/24"
echo "     PC  : 192.168.1.100/24"
echo "     验证: ping 192.168.1.20"
echo "=============================================================================="
