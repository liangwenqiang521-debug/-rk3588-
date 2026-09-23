#!/usr/bin/env bash
# ==============================================================================
#  deploy_board.sh — RK3588 板端一站式部署（转模型 + 装运行时 + 起服务 + 自启）
#
#  这是给「真板子」用的总入口。一个命令把全部事情做完：
#    ① 装 rknn-toolkit2（转模型） + rknn-toolkit-lite2（推理） + opencv/numpy
#    ② 用现成的 best.onnx 转出 best.rknn（合成 4 类，无需 torch）
#    ③ 生成 start_board.sh（起推理服务）
#    ④ 注册 systemd 开机自启 defect-board
#    ⑤ 立即启动服务，把 NPU 负载/检测结果经 TCP:9000 推给上位机
#
#  用法（在 RK3588 板子上，SSH 登录后执行）：
#      # 先把你电脑上的「模型训练/」整个目录传到板子，例如在 PC 上：
#      #   scp -r "D:\workbuddy\缺陷检测项目\模型训练" root@<板子IP>:/root/
#      # 然后在板子上：
#      cd /root/模型训练
#      chmod +x deploy_board.sh
#      ./deploy_board.sh
#
#  常用参数：
#      --port 9000               TCP 服务端口（默认 9000）
#      --source 0                数据源：0=摄像头 / 图片目录路径
#      --serial /dev/ttyS0       同时经串口推送（不填则只用 TCP）
#      --no-autostart            不注册开机自启
#      --skip-convert            跳过转模型（.rknn 已存在时）
#      --six-class               额外转 NEU 6 类模型（需要能装 ultralytics+torch）
#
#  说明：转换用 best.onnx（已存在，无需 torch）→ best.rknn，最快路径。
#        NEU 6 类模型 best_neu_yolo11n_aug.pt 需要 ultralytics 才能导出 ONNX，
#        在板子上装 torch 很重，默认跳过；需要时加 --six-class。
# ==============================================================================
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
err()  { echo -e "${RED}❌ $*${NC}"; exit 1; }

PORT=9000; SOURCE="0"; SERIAL=""; AUTOSTART=1; SKIP_CONVERT=0; SIX_CLASS=0
RKNN_VERSION="2.3.0"
# 按板子实际 Python 版本推导 cp 标签（rknn-toolkit2 2.3.0 提供 cp38/cp310，Ubuntu22.04 多为 cp310）
PYVER=$(python3 -c "import sys;print('cp%d%d'%(sys.version_info[0],sys.version_info[1]))" 2>/dev/null || echo cp310)
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)         PORT="$2";     shift 2 ;;
        --source)       SOURCE="$2";   shift 2 ;;
        --serial)       SERIAL="$2";   shift 2 ;;
        --no-autostart) AUTOSTART=0;   shift 1 ;;
        --skip-convert) SKIP_CONVERT=1; shift 1 ;;
        --six-class)    SIX_CLASS=1;   shift 1 ;;
        -h|--help)      awk 'NR>1{ if(/^# =====/){c++; if(c==2){print; exit}} if(c<2) print }' "$0" \
                          | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) warn "未知参数: $1"; shift 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=============================================================================="
echo "  RK3588 板端一站式部署  (端口=$PORT, 数据源=$SOURCE)"
echo "  工作目录: $SCRIPT_DIR"
echo "=============================================================================="

# ---------------- 0. 环境检查 ----------------
ARCH=$(uname -m)
echo
echo "[0/6] 检查环境..."
echo "      架构: $ARCH  系统: $(uname -s)"
if [ "$ARCH" != "aarch64" ]; then
    warn "  当前不是 aarch64（RK3588 应为 aarch64），NPU 将不可用"
fi
if [ -d /sys/class/rknpu ]; then
    ok "  检测到 RKNPU 设备 /sys/class/rknpu"
elif grep -qi "rk3588" /proc/device-tree/model 2>/dev/null; then
    ok "  设备树: $(cat /proc/device-tree/model 2>/dev/null | tr -d '\0')"
else
    warn "  未检测到 RKNPU —— 可能驱动未加载，NPU 推理会失败"
fi

# ---------------- 1. 准备 Python ----------------
echo
echo "[1/6] 准备 Python 环境..."
PY=python3
command -v $PY >/dev/null 2>&1 || err "未找到 python3"
echo "      系统 Python: $($PY --version 2>&1)"

# 用完全隔离的 venv，避免系统 numpy/opencv/protobuf 版本与 rknn 依赖要求冲突
VENV_DIR="$SCRIPT_DIR/.board_venv"
if [ ! -d "$VENV_DIR" ]; then
    if $PY -m venv "$VENV_DIR" 2>/dev/null; then
        ok "  已创建隔离 venv"
    else
        warn "  venv 创建失败，回退到系统 Python（需 sudo 装包）"
        VENV_DIR=""
    fi
fi
if [ -n "$VENV_DIR" ] && [ -x "$VENV_DIR/bin/python" ]; then
    PY="$VENV_DIR/bin/python"
    PIP="$PY -m pip"
    ok "  使用 venv 解释器: $PY"
else
    PIP="pip3"
    warn "  使用系统 Python（未隔离）"
fi
$PY -m pip install --upgrade pip -q 2>/dev/null || true

# ---------------- 公共：RKNN whl 安装（本地优先 → GitHub → Gitee → git 浅克隆） ----------------
# 用 --no-deps 安装 whl 本身（避免 whl 的冗余传递依赖），依赖由脚本显式装齐
install_rknn_whl() {
    # $1 = 仓库内相对路径（含 packages 或 packages/arm64），如 rknn-toolkit-lite2/packages 或 rknn-toolkit2/packages/arm64
    local relpath="$1"; local whl="$2"; local installed=0
    local urls=(
        "https://github.com/airockchip/rknn-toolkit2/raw/v${RKNN_VERSION}/${relpath}/${whl}"
        "https://gitee.com/airockchip/rknn-toolkit2/raw/v${RKNN_VERSION}/${relpath}/${whl}"
    )
    for f in "$whl" rknn_*.whl; do
        [ -f "$f" ] || continue
        echo "      使用本地 whl: $f"
        $PIP install -q --no-deps "$f" 2>/dev/null && installed=1 && break
    done
    if [ "$installed" -eq 0 ]; then
        for u in "${urls[@]}"; do
            echo "      下载: $u"
            if $PIP install -q --no-deps "$u" 2>/dev/null; then installed=1; break; fi
        done
    fi
    if [ "$installed" -eq 0 ]; then
        echo "      尝试 git 浅克隆（仅取 ${relpath}）..."
        local tmp=/tmp/rknn_tk_$$
        if git clone --depth 1 --filter=blob:none --sparse "https://github.com/airockchip/rknn-toolkit2.git" "$tmp" 2>/dev/null; then
            (cd "$tmp" && git sparse-checkout set "${relpath}" 2>/dev/null)
            $PIP install -q --no-deps "$tmp/${relpath}/${whl}" 2>/dev/null && installed=1
            rm -rf "$tmp" 2>/dev/null
        fi
    fi
    return $installed
}

# ---------------- 2. 装 opencv / numpy / RKNN 轻量依赖 ----------------
# 先装 RKNN 的轻量依赖（避免 --no-deps 时缺包）；opencv 见下方逻辑
$PY -c "import numpy, onnx, protobuf, psutil" 2>/dev/null || \
    $PIP install -q numpy onnx protobuf psutil ruamel.yaml scipy 2>/dev/null || true
echo
echo "[2/6] 安装基础依赖 opencv/numpy..."
# 板子上用 pip 装 opencv-python-headless（aarch64 预编译 wheel，隔离 venv 内无系统冲突）
if ! $PY -c "import cv2" 2>/dev/null; then
    $PIP install -q opencv-python-headless numpy 2>/dev/null && ok "  opencv/numpy 装好" \
        || warn "  opencv/numpy 装失败（可先 sudo apt install python3-opencv 再跑）"
else
    ok "  cv2 已可用"
fi
$PY -c "import numpy" 2>/dev/null || $PIP install -q numpy 2>/dev/null || warn "  numpy 装失败"
$PIP install -q pyserial 2>/dev/null || warn "  pyserial 装失败"

# ---------------- 3. 装 RKNN 运行时（lite2 推理 + toolkit2 转模型） ----------------
echo
echo "[3/6] 安装 RKNN 运行时（lite2 推理 + toolkit2 转模型）..."

# 3.1 rknn-toolkit-lite2（板端 NPU 推理运行时，必需）
if $PY -c "import rknnlite" 2>/dev/null; then
    ok "  rknn-toolkit-lite2 已安装"
else
    LITE_WHL="rknn_toolkit_lite2-${RKNN_VERSION}-${PYVER}-manylinux_2_17_aarch64.manylinux2014_aarch64.whl"
    install_rknn_whl "rknn-toolkit-lite2/packages" "$LITE_WHL" \
        && ok "  rknnlite 导入成功" \
        || warn "  lite2 未装上（NPU 推理不可用，请手动下载 whl 到本目录再跑）"
fi

# 3.2 rknn-toolkit2（完整版，仅转模型用；aarch64 需装 torch 等依赖，best-effort）
if [ "$SKIP_CONVERT" -eq 1 ]; then
    warn "  --skip-convert：跳过 rknn-toolkit2 安装与转换"
elif $PY -c "import rknn" 2>/dev/null; then
    ok "  rknn-toolkit2 已安装"
else
    echo "      装 rknn-toolkit2 依赖（含 torch，aarch64 约 200MB，稍慢）..."
    $PIP install -q "protobuf==3.20.3" "psutil" "ruamel.yaml" "scipy" "tqdm" \
        "fast-histogram" "numpy<=1.26.4" "onnx==1.14.1" "onnxoptimizer==0.3.8" \
        "onnxruntime==1.16.0" "torch>=1.13.1,<=2.2.0" 2>/dev/null \
        || warn "  部分依赖装失败（torch 等），板上转换可能失败"
    TK_WHL="rknn_toolkit2-${RKNN_VERSION}-${PYVER}-manylinux_2_17_aarch64.manylinux2014_aarch64.whl"
    install_rknn_whl "rknn-toolkit2/packages/arm64" "$TK_WHL" \
        && ok "  rknn-toolkit2 导入成功" \
        || warn "  rknn-toolkit2 未装上（板上转模型可能失败，将提示改用 x86 转换）"
fi

# ---------------- 4. 转模型 ----------------
echo
echo "[4/6] 转换模型 .rknn..."
CALIB="./datasets/neu_aug/images/val"

if [ "$SKIP_CONVERT" -eq 0 ] && [ ! -f best.rknn ]; then
    if $PY -c "import rknn" 2>/dev/null && [ -f best.onnx ] && [ -d "$CALIB" ]; then
        echo "      转 best.onnx -> best.rknn（合成 4 类，无需 torch）..."
        $PY export_rknn.py --src best.onnx --dst best.rknn \
            --calib "$CALIB" --imgsz 640 --names scratch dent missing crack \
            && ok "  best.rknn 已生成" || warn "  best.rknn 转换失败（见上方日志）"
    else
        warn "  缺 rknn-toolkit2 / best.onnx / 校准目录，跳过转换"
    fi
else
    [ -f best.rknn ] && ok "  best.rknn 已存在，跳过" || warn "  已跳过转换（--skip-convert 但无 best.rknn）"
fi

if [ "$SIX_CLASS" -eq 1 ] && [ ! -f best_neu_yolo11n_aug.rknn ]; then
    echo "      转 best_neu_yolo11n_aug.pt -> .rknn（NEU 6 类，需 ultralytics）..."
    $PIP install -q ultralytics 2>/dev/null || warn "  ultralytics 装失败（6 类模型无法转）"
    if $PY -c "import rknn" 2>/dev/null && [ -f best_neu_yolo11n_aug.pt ] && [ -d "$CALIB" ]; then
        $PY export_rknn.py --src best_neu_yolo11n_aug.pt --dst best_neu_yolo11n_aug.rknn \
            --calib "$CALIB" --imgsz 640 \
            --names crazing inclusion patches pitted_surface rolled-in_scale scratches \
            && ok "  best_neu_yolo11n_aug.rknn 已生成" || warn "  6 类模型转换失败"
    fi
fi

# 确定最终模型
MODEL=""
for cand in best_neu_yolo11n_aug.rknn best.rknn; do
    [ -f "$cand" ] && MODEL="$cand" && break
done
if [ -z "$MODEL" ]; then
    err "  没有可用的 .rknn 模型！板上转换失败的话，请在 PC 的 WSL/Ubuntu 跑 setup_rknn_env.sh 生成 best.rknn，再 scp 过来，然后 ./deploy_board.sh --skip-convert"
fi
ok "  最终模型: $MODEL  ($(du -h "$MODEL" | cut -f1))"

# ---------------- 5. 生成启动脚本 ----------------
echo
echo "[5/6] 生成启动脚本 start_board.sh..."
CMD_ARGS="--model $MODEL --source $SOURCE --tcp-port $PORT"
[ -n "$SERIAL" ] && CMD_ARGS="$CMD_ARGS --serial $SERIAL"
# 默认给合成 4 类模型配上类别名（若用 6 类模型会自动带不同 names，用户可自行改）
NAMES_ARG=""
if [ "$MODEL" = "best.rknn" ]; then
    NAMES_ARG="--names scratch dent missing crack"
elif [ "$MODEL" = "best_neu_yolo11n_aug.rknn" ]; then
    NAMES_ARG="--names crazing inclusion patches pitted_surface rolled-in_scale scratches"
fi

cat > start_board.sh << EOF
#!/usr/bin/env bash
# 自动生成于 $(date '+%Y-%m-%d %H:%M:%S')
cd "\$(dirname "\$0")"
exec $PY board_infer.py $CMD_ARGS $NAMES_ARG
EOF
chmod +x start_board.sh
ok "  已生成 start_board.sh"
echo "      $PY board_infer.py $CMD_ARGS $NAMES_ARG"

# ---------------- 6. 开机自启 + 立即启动 ----------------
echo
echo "[6/6] 开机自启 + 启动服务..."
if [ "$AUTOSTART" -eq 1 ] && command -v systemctl >/dev/null 2>&1; then
    SVC=/etc/systemd/system/defect-board.service
    WD=$SCRIPT_DIR
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
else
    warn "  跳过自启（--no-autostart 或无 systemd）"
fi

# ---------------- 完成 ----------------
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "=============================================================================="
ok " 部署完成！板子 IP: ${IP:-（未获取，请 ip addr 查看）}"
echo "=============================================================================="
echo
echo " 模型      : $MODEL"
echo " TCP 端口  : $PORT"
[ -n "$SERIAL" ] && echo " 串口      : $SERIAL"
echo
echo " 启动服务（二选一）："
echo "     ./start_board.sh                         # 前台，直接看日志"
echo "     sudo systemctl start defect-board        # 后台服务"
echo "     journalctl -u defect-board -f            # 看实时日志"
echo
echo " 回到 Windows 上位机："
echo "     1) NPU 监控页 → 数据来源「板端TCP」→ 地址 ${IP:-<板子IP>} → 端口 $PORT → 连接"
echo "     2) 检测页     → 边缘模式「网络(TCP)」→ 地址 ${IP:-<板子IP>}:$PORT → 启动"
echo
echo " 验证板子是否在发数据（在板子上再开一个终端）："
echo "     python3 -c \"import socket,json; s=socket.create_connection(('127.0.0.1',$PORT),3); print(s.recv(4096).decode()); s.close()\""
echo "=============================================================================="
