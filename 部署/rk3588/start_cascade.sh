#!/bin/sh
# 启动双模型级联服务（板端）
# 用法: sh /root/rknn/start_cascade.sh
cd /root/rknn
# 杀掉可能残留的旧服务
for p in $(ps aux | grep -E 'board_server' | grep -v grep | awk '{print $2}'); do
  kill $p 2>/dev/null
done
sleep 1
nohup python3 /root/rknn/board_server_cascade.py 9000 >> /root/rknn/server_cascade.log 2>&1 &
echo "cascade started, pid=$!"
