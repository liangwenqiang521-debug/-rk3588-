# -*- coding: utf-8 -*-
"""大 buffer SFTP 上传，避免 paramiko 默认 32KB 小块导致的极慢传输。"""
import os
import sys
import time
import paramiko

import board_env
HOST = board_env.get("BOARD_IP", "") or board_env.fallback_ips()[0]
USER = "root"
KEY = os.path.expanduser(board_env.get("BOARD_KEY", r"~\.ssh\id_ed25519"))
PORT = 22

local = sys.argv[1]
remote = sys.argv[2]

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, PORT, USER, key_filename=KEY, timeout=15,
          allow_agent=False, look_for_keys=False)

sftp = c.open_sftp()
# 关键：加大每次写入块，减少往返确认次数
sftp.MAX_REQUEST_SIZE = 1 << 20          # 1MB
sftp.sock.settimeout(60)

size = os.path.getsize(local)
t0 = time.time()
sftp.put(local, remote)
dt = time.time() - t0
print("uploaded %s -> %s (%.2f MB, %.1f s, %.2f MB/s)"
      % (local, remote, size/1e6, dt, size/1e6/dt))
sftp.close()
c.close()
