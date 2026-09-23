#!/bin/sh
# 板端 NPU 缺陷检测服务启动脚本
# 用法: sh /root/rknn/start_srv.sh [model] [port]   (默认 best_neu6.rknn / 9000)
# 说明: 生产模型是 NEU-DET 6 类 FP16(best_neu6.rknn)，实测 ~10FPS。
#       INT8(best_int8.rknn)在 NPU 驱动 v0.9.2 上分类头输出全 0，暂不使用。
# ⚠️ best_neu6.rknn 期望 uint8[0,255] 输入（RKNN 内部做 /255 归一化），
#    board_server.py 的 read_sample() 已按此实现，勿再叠加 host 端归一化。
MODEL=${1:-best_neu6.rknn}
PORT=${2:-9000}
shift 2
EXTRA="$@"          # 透传额外参数（如 --step 逐张模式）
LOG=/root/rknn/server.log

# 精确杀掉旧服务：匹配 python 进程且命令行含 board_server
for pid in $(ls /proc | grep -E '^[0-9]+$'); do
  cmd=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ')
  case "$cmd" in
    *python3*board_server*) echo "kill old: $pid  $cmd"; kill -9 $pid 2>/dev/null ;;
  esac
done
sleep 1

cd /root/rknn
echo "[$(date)] start board_server $MODEL $PORT $EXTRA" >> $LOG
nohup python3 board_server.py $MODEL $PORT $EXTRA >> $LOG 2>&1 &
echo "SERVER_PID=$!"
