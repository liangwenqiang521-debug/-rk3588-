echo "=== S99board 内容 ==="
cat /etc/init.d/S99board
echo "=== 当前服务命令行 ==="
tr '\0' ' ' < /proc/$(pgrep -f board_server_cascade | head -1)/cmdline
echo
echo "=== 进程 ==="
pgrep -af board_server_cascade
