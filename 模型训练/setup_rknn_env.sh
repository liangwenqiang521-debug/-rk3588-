#!/usr/bin/env bash
###############################################################################
# setup_rknn_env.sh — RKNN 转换环境一键搭建 + 生成 .rknn
#
# 适用环境（任选其一）：
#   * x86_64 Ubuntu 20.04 / 22.04 / 24.04  （物理机 / 虚拟机 / WSL2 均可，
#     RKNN-Toolkit2 是纯 CPU 库，不依赖 GPU，WSL2 的 x86_64 Linux 内核可用）
#   * aarch64 RK3588 板子（Debian/Ubuntu，直接在本机转也行，官方不保证）
#
# 用法：
#   chmod +x setup_rknn_env.sh
#   ./setup_rknn_env.sh                 # 转全部（4 类 + 6 类）
#   ./setup_rknn_env.sh --four-only     # 只转 4 类（不装 torch/ultralytics，最快）
#   ./setup_rknn_env.sh --six-only      # 只转 NEU 6 类(新, 640)
#   ./setup_rknn_env.sh --skip-deps     # 依赖已装好，跳过安装直接转
#
# 环境变量：
#   RKNN_VERSION=2.3.2   RKNN-Toolkit2 版本（须与板端 rknn-toolkit-lite2 一致）
#   PY_VER=3.10          目标 Python 版本（3.6~3.12，默认自动探测）
#
# 生成物（默认 FP16，板端 NPU 驱动 v0.9.2 跑 INT8 有 bug）：
#   best_neu_yolo11n_640.rknn   NEU 6 类(新, 640, 本次训练成果)  ← 主目标
#   best.rknn                   4 类合成(可选, 若本目录有 best.onnx)
###############################################################################
set -uo pipefail

RKNN_VERSION="${RKNN_VERSION:-2.3.2}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------- 参数 ----------------
FOUR_ONLY=0; SIX_ONLY=0; SKIP_DEPS=0
for a in "$@"; do
  case "$a" in
    --four-only)  FOUR_ONLY=1 ;;
    --six-only)   SIX_ONLY=1 ;;
    --skip-deps)  SKIP_DEPS=1 ;;
    -h|--help)    awk 'NR>1{ if($0 !~ /^#/) exit; print }' "$0" | sed 's/^#\{1,2\} \{0,1\}//'; exit 0 ;;
    *) echo "未知参数: $a（用 --help 查看）"; exit 1 ;;
  esac
done

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; BLU='\033[0;34m'; NC='\033[0m'
info(){ echo -e "${GRN}[INFO]${NC} $*"; }
warn(){ echo -e "${YEL}[WARN]${NC} $*"; }
err(){  echo -e "${RED}[ERROR]${NC} $*"; }
step(){ echo -e "\n${BLU}==== $* ====${NC}"; }

echo "============================================================"
echo " RKNN 转换环境一键搭建"
echo "   RKNN-Toolkit2 : v${RKNN_VERSION}"
echo "   工作目录      : $SCRIPT_DIR"
echo "============================================================"

# ---------- 1. 环境检查 ----------
ARCH="$(uname -m)"
KERNEL="$(uname -r)"
info "架构: $ARCH  系统: $(uname -s)  内核: $KERNEL"
case "$ARCH" in
  x86_64)  PKG_SUBDIR="rknn-toolkit2/packages/x86_64" ;;
  aarch64) PKG_SUBDIR="rknn-toolkit2/packages/arm64"
           warn "aarch64 上转换非官方保证路径，若失败请改用 x86_64 Ubuntu" ;;
  *) err "不支持的架构 $ARCH（需 x86_64 或 aarch64）"; exit 1 ;;
esac
case "$KERNEL" in
  *microsoft*|*WSL2*) info "检测到 WSL2 环境（RKNN-Toolkit2 为纯 CPU 库，可用）" ;;
esac

# ---------- 2. 选定 Python ----------
step "1/5 准备 Python 环境"

pick_python() {
  # 优先用 PY_VER 指定版本，否则按 3.10 → 3.11 → 3.12 → 3.8 顺序探测
  local cands=()
  [ -n "${PY_VER:-}" ] && cands+=("python${PY_VER}")
  cands+=(python3.10 python3.11 python3.12 python3.8 python3)
  for c in "${cands[@]}"; do
    if command -v "$c" >/dev/null 2>&1; then echo "$c"; return 0; fi
  done
  return 1
}

PYTHON="$(pick_python || true)"
if [ -z "$PYTHON" ]; then
  warn "未找到 python3，尝试 apt 安装 python3.10 ..."
  sudo apt-get update -y -q >/dev/null 2>&1 || true
  sudo apt-get install -y -q python3.10 python3.10-venv python3-pip 2>/dev/null || \
    sudo apt-get install -y -q python3 python3-venv python3-pip 2>/dev/null || true
  PYTHON="$(pick_python || true)"
fi
[ -z "$PYTHON" ] && { err "找不到可用的 python3，请手动安装后重试"; exit 1; }

PYVER_STR="$($PYTHON -c 'import sys;print("cp%d%d"%(sys.version_info[0],sys.version_info[1]))' 2>/dev/null || echo cp310)"
PYMM="$($PYTHON -c 'import sys;print("%d.%d"%(sys.version_info[0],sys.version_info[1]))' 2>/dev/null || echo 3.10)"
info "Python: $($PYTHON --version 2>&1)  (标签 $PYVER_STR)"

# venv 隔离（避免与系统包冲突）
if [ -z "${VIRTUAL_ENV:-}" ]; then
  VENV_DIR="${SCRIPT_DIR}/.rknn_venv"
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    info "创建虚拟环境 $VENV_DIR ..."
    sudo apt-get install -y -q "python${PYMM}-venv" >/dev/null 2>&1 || true
    "$PYTHON" -m venv "$VENV_DIR" || { err "venv 创建失败（可能缺 python${PYMM}-venv）"; exit 1; }
  fi
  PYTHON="$VENV_DIR/bin/python"
  info "已启用 venv: $PYTHON"
fi
PIP="$PYTHON -m pip"

# 提前检测本次要转的模型（决定是否需要 torch）
NEU640_ONNX="./runs/neu_yolo11n_640/weights/best.onnx"
NEU640_PT="./best_neu_yolo11n_640.pt"
FOUR_ONNX="./best.onnx"
NEED_TORCH=0
[ -f "$NEU640_PT" ] && [ ! -f "$NEU640_ONNX" ] && NEED_TORCH=1

# ---------- 3. 装依赖 ----------
step "2/5 安装依赖"

if [ "$SKIP_DEPS" -eq 1 ]; then
  warn "--skip-deps：跳过依赖安装"
else
  $PIP install --upgrade pip -q 2>/dev/null || true

  # 3.1 RKNN-Toolkit2 的运行依赖（对齐官方 requirements_cp310-2.3.0.txt）
  #     x86_64 版已注释掉 tensorflow，无需安装；numpy 必须 <=1.26.4
  info "安装 RKNN-Toolkit2 基础依赖（onnx/onnxruntime/numpy<=1.26.4/opencv...）"
  $PIP install -q \
    "numpy<=1.26.4" \
    "protobuf>=4.21.6,<=4.25.4" \
    "onnx>=1.10.0" "onnxruntime>=1.12.0" \
    "opencv-python-headless>=4.5.5.64" \
    "psutil>=5.9.0" "ruamel.yaml>=0.17.21" "scipy>=1.9.3" \
    "tqdm>=4.64.1" "fast-histogram>=0.11" \
    2>&1 | tail -5 || warn "  部分基础依赖安装失败（继续尝试）"

  # 3.2 RKNN-Toolkit2 本体
  info "安装 RKNN-Toolkit2 v${RKNN_VERSION} ..."
  if $PYTHON -c "import rknn" 2>/dev/null; then
    warn "  rknn 已安装，跳过"
  else
    # 注意：cp36/cp37 的 ABI 标签带 m（cp36m/cp37m），其余不带
    case "$PYVER_STR" in
      cp36|cp37) ABI="${PYVER_STR}m" ;;
      *)         ABI="${PYVER_STR}" ;;
    esac
    WHL="rknn_toolkit2-${RKNN_VERSION}-${PYVER_STR}-${ABI}-manylinux_2_17_${ARCH}.manylinux2014_${ARCH}.whl"

    install_whl() {
      # 本地优先 → GitHub raw → Gitee raw → git 稀疏克隆
      for f in "$WHL" rknn_toolkit2-*.whl; do
        [ -f "$f" ] || continue
        info "  使用本地 whl: $f"
        $PIP install -q --no-deps "$f" && return 0
      done
      for base in \
        "https://github.com/airockchip/rknn-toolkit2/raw/v${RKNN_VERSION}/${PKG_SUBDIR}" \
        "https://gitee.com/airockchip/rknn-toolkit2/raw/v${RKNN_VERSION}/${PKG_SUBDIR}" ; do
        info "  下载: ${base}/${WHL}"
        $PIP install -q --no-deps "${base}/${WHL}" && return 0
      done
      info "  尝试 git 稀疏克隆（仅取 whl 所在目录）..."
      local tmp="/tmp/_rknn_tk_$$"
      if git clone --depth 1 --filter=blob:none --sparse \
           "https://github.com/airockchip/rknn-toolkit2.git" "$tmp" >/dev/null 2>&1; then
        ( cd "$tmp" && git sparse-checkout set "$PKG_SUBDIR" >/dev/null 2>&1 )
        if [ -f "$tmp/$PKG_SUBDIR/$WHL" ]; then
          $PIP install -q --no-deps "$tmp/$PKG_SUBDIR/$WHL" && { rm -rf "$tmp"; return 0; }
        fi
      fi
      rm -rf "$tmp" 2>/dev/null
      return 1
    }

    if install_whl; then
      $PYTHON -c "import rknn" 2>/dev/null \
        && info "  ✅ rknn 导入成功" \
        || warn "  ⚠ whl 已装但 import rknn 失败，可能缺依赖"
    else
      err "  RKNN-Toolkit2 安装失败。可手动下载放到本目录后重跑："
      err "    ${PKG_SUBDIR}/${WHL}"
      exit 1
    fi
  fi

  # 3.3 转 .pt 模型需要 ultralytics（拉 torch，约 200MB+）；本次 6 类用 ONNX 直转可免 torch
  if [ "$FOUR_ONLY" -eq 1 ]; then
    warn "--four-only：跳过 torch/ultralytics"
  elif [ "$NEED_TORCH" -eq 0 ]; then
    warn "本次用 ONNX 直转（免 torch），跳过 torch/ultralytics 安装以加速"
  else
    if $PYTHON -c "import ultralytics" 2>/dev/null; then
      info "ultralytics 已安装，跳过"
    else
      info "安装 torch(CPU 版) + ultralytics（转 6 类 .pt 模型用，约 200MB~2GB，请耐心）"
      $PIP install -q "torch>=1.10.1,<=2.4.0" --index-url https://pypi.tuna.tsinghua.edu.cn/simple 2>&1 | tail -3 \
        || $PIP install -q "torch>=1.10.1,<=2.4.0" 2>&1 | tail -3 \
        || warn "  torch 安装失败（6 类模型将无法转换）"
      $PIP install -q ultralytics 2>&1 | tail -3 || warn "  ultralytics 安装失败"
    fi
  fi
fi

# ---------- 4. 校验输入 ----------
step "3/5 校验输入文件"
CALIB="./datasets/neu_aug/images/val"
# FP16 不量化，校准集仅 INT8 用；缺失只提示不致命
if [ -d "$CALIB" ]; then
  N_CALIB="$(find "$CALIB" -maxdepth 1 -type f \( -iname '*.jpg' -o -iname '*.png' \) 2>/dev/null | wc -l)"
  info "校准集: $CALIB （${N_CALIB} 张图）"
else
  warn "校准目录缺失（FP16 不量化可忽略；仅 --dtype int8 才需要）"
fi

HAVE_NEU640=0; HAVE_FOUR=0
[ -f "$NEU640_ONNX" ] || [ -f "$NEU640_PT" ] && HAVE_NEU640=1
[ -f "$FOUR_ONNX" ] && HAVE_FOUR=1
info "NEU 6类(新640): ONNX=$([ -f "$NEU640_ONNX" ] && echo 1 || echo 0) / PT=$([ -f "$NEU640_PT" ] && echo 1 || echo 0) ; 4类合成 ONNX=$HAVE_FOUR"
[ "$HAVE_NEU640" -eq 0 ] && [ "$HAVE_FOUR" -eq 0 ] && \
  { err "没有任何可转换的模型（需 best_neu_yolo11n_640.pt 或 runs/neu_yolo11n_640/weights/best.onnx 或 best.onnx）"; exit 1; }

# ---------- 5. 执行转换 ----------
step "4/5 转换模型"
DONE4=0; DONE6=0

# 【主】NEU 6 类(新, 640): 优先用已导出的 ONNX(免 torch)，否则用 .pt
if [ "$FOUR_ONLY" -eq 0 ] && [ "$HAVE_NEU640" -eq 1 ]; then
  if [ -f "$NEU640_ONNX" ]; then SRC6="$NEU640_ONNX"; else SRC6="$NEU640_PT"; fi
  info "【主】NEU 6类(640): $SRC6 -> best_neu_yolo11n_640.rknn (FP16, 默认)"
  if $PYTHON export_rknn.py --src "$SRC6" --dst best_neu_yolo11n_640.rknn \
       --imgsz 640 --names crazing inclusion patches pitted_surface rolled-in_scale scratches; then
    DONE6=1; info "  ✅ best_neu_yolo11n_640.rknn 生成成功"
  else
    warn "  ❌ 6类转换失败（多为 rknn-toolkit2 未装好）"
  fi
elif [ "$FOUR_ONLY" -eq 0 ]; then
  warn "缺少 NEU 6类模型（best_neu_yolo11n_640.pt 或 runs/neu_yolo11n_640/weights/best.onnx）"
fi

# 【次】4 类合成(可选): 仅当本目录有 best.onnx
if [ "$SIX_ONLY" -eq 0 ] && [ "$HAVE_FOUR" -eq 1 ] && [ ! -f best.rknn ]; then
  info "【次】4类合成: $FOUR_ONNX -> best.rknn (FP16)"
  if $PYTHON export_rknn.py --src "$FOUR_ONNX" --dst best.rknn \
       --imgsz 640 --names scratch dent missing crack; then
    DONE4=1; info "  ✅ best.rknn 生成成功"
  else
    warn "  ❌ 4类转换失败"
  fi
elif [ -f best.rknn ]; then
  DONE4=1; info "  best.rknn 已存在，跳过"
fi

# ---------- 6. 汇总 ----------
step "5/5 完成"
echo
if [ "$DONE4" -eq 1 ] || [ "$DONE6" -eq 1 ]; then
  echo -e "${GRN}生成的文件：${NC}"
  ls -lh best_neu_yolo11n_640.rknn 2>/dev/null
  ls -lh best.rknn 2>/dev/null
  echo
  echo "下一步：把 best_neu_yolo11n_640.rknn 拷到 RK3588 板子覆盖 /root/rknn/best.rknn，"
  echo "        并同步把 board_server.py 的 NAMES 改为 6 类 NEU（crazing inclusion patches pitted_surface rolled-in_scale scratches）"
else
  echo -e "${RED}没有生成任何 .rknn，请根据上方日志排查${NC}"
  exit 1
fi
echo "============================================================"
