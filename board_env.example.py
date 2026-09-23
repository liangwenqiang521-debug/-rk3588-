# -*- coding: utf-8 -*-
"""板端连接参数 —— 本地私有模板。

用法：
    cp board_env.example.py board_env.local.py
然后按你的实际环境填写下面的值。

`board_env.local.py` 已在 .gitignore 中，**不会**被提交到仓库。
也可以改用环境变量（优先级更高）：
    Windows:  set BOARD_IP=192.168.1.20
    Linux:    export BOARD_IP=192.168.1.20
"""

# 板子 IP（留空则走 board_env.FALLBACK_IPS 自动探测）
BOARD_IP = "192.168.1.20"

# SSH 登录
BOARD_USER = "root"
BOARD_PASS = ""          # 建议留空并改用 SSH 密钥
BOARD_PORT = "22"
BOARD_KEY = r"~\.ssh\id_ed25519"

# 服务端口
BOARD_STREAM_PORT = "9000"

# 串口
BOARD_SERIAL_PORT = "COM3"
BOARD_SERIAL_BAUD = "1500000"

# 自动探测候选（逗号分隔，可选）
# BOARD_FALLBACK_IPS = "192.168.1.20,169.254.100.100"
