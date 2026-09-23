# -*- coding: utf-8 -*-
"""串口控制台后台服务：
- 持续读取 COM 口数据，追加写入 serial_rx.log
- 监视 serial_tx.cmd 文件，有内容则发送到串口后清空
用法: python serial_console.py [COMx] [baud]
"""
import sys
import os
import time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM3"
BAUD = int(sys.argv[2]) if len(sys.argv) > 2 else 1500000
BASE = os.path.dirname(os.path.abspath(__file__))
RX_LOG = os.path.join(BASE, "serial_rx.log")
TX_CMD = os.path.join(BASE, "serial_tx.cmd")

ser = serial.Serial(PORT, BAUD, bytesize=8, parity="N", stopbits=1, timeout=0.2)
with open(RX_LOG, "ab") as f:
    f.write(("\n===== console opened %s @%d %s =====\n"
             % (PORT, BAUD, time.strftime("%H:%M:%S"))).encode())

while True:
    try:
        data = ser.read(4096)
        if data:
            with open(RX_LOG, "ab") as f:
                f.write(data)
        if os.path.exists(TX_CMD):
            try:
                with open(TX_CMD, "rb") as f:
                    cmd = f.read()
                if cmd:
                    ser.write(cmd)
                    with open(RX_LOG, "ab") as f:
                        f.write(b"\n>>> " + cmd)
                open(TX_CMD, "wb").close()
            except Exception:
                pass
    except serial.SerialException:
        break
    time.sleep(0.05)
