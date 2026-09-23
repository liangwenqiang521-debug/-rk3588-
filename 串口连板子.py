# -*- coding: utf-8 -*-
"""串口连板子 —— 命令行版 RK3588 串口终端（MobaXterm 不可用时的兜底）。

用途
--------------------------------------------------------------------
MobaXterm 是 GUI 程序，本沙箱无法代你启动；若你不想开 MobaXterm，
用本脚本即可在终端里直接用串口连上 RK3588（1500000 波特，与板端调试口一致）。

用法
--------------------------------------------------------------------
  python 串口连板子.py                # 交互式终端（Ctrl+C 退出）
  python 串口连板子.py -c "ip addr"   # 只跑一条命令后退出
  python 串口连板子.py -c "ls /root/rknn" -c "ps aux | grep board"
  python 串口连板子.py --interrupt    # 先发 Ctrl+C 打断卡住的命令
  python 串口连板子.py -b "ip addr"   # 后台跑（不阻塞等待），输出落 /tmp/_sb.log

参数
--------------------------------------------------------------------
  --port COM3        串口设备（默认 COM3）
  --baud 1500000     波特率（板端 CH343 调试口实际值，勿改）
  -c, --cmd CMD      执行命令（可重复）；不给则进交互模式
  -w, --wait 3.0     每条命令的等待/收集秒数
  -i, --interrupt    先发送 Ctrl+C（\x03），用于打断卡住的交互命令
  -b, --bg CMD       后台执行：`CMD > /tmp/_sb.log 2>&1 &`，立即返回

说明
--------------------------------------------------------------------
* 板端登录：root / <你的密码>（串口通常已自动登录为 root）
* 板端数据串口设备名是 /dev/ttyS3（不是 ttyS0），跑 board_infer.py 时用它：
    python3 /root/rknn/board_infer.py --model best.rknn --source 0 \
        --serial /dev/ttyS3 --baud 1500000 --names scratch dent missing crack
"""
import argparse
import sys
import time

import serial


def open_port(port, baud):
    try:
        s = serial.Serial(port, baud, timeout=0.5,
                          bytesize=8, parity="N", stopbits=1)
    except Exception as e:
        print("❌ 打不开串口 %s @ %d: %s" % (port, baud, e))
        print("   提示：若被 MobaXterm/MoTTY 占用，先关掉它们（或跑 杀进程释放COM3.py）")
        sys.exit(1)
    s.reset_input_buffer()
    return s


def drain(s, seconds):
    """持续读取 seconds 秒，返回解码文本。"""
    buf = b""
    t0 = time.time()
    while time.time() - t0 < seconds:
        c = s.read(8192)
        if c:
            buf += c
        elif buf:
            # 有一阵子没新数据了，提前收工
            break
    return buf.decode("utf-8", "ignore")


def send(s, cmd, wait):
    s.write((cmd + "\r\n").encode("utf-8"))
    s.flush()
    time.sleep(wait)
    return drain(s, wait)


def main():
    ap = argparse.ArgumentParser(description="RK3588 串口终端")
    ap.add_argument("--port", default="COM3")
    ap.add_argument("--baud", type=int, default=1500000)
    ap.add_argument("-c", "--cmd", action="append", default=[],
                    help="执行命令（可重复）；不给则进入交互模式")
    ap.add_argument("-w", "--wait", type=float, default=3.0)
    ap.add_argument("-i", "--interrupt", action="store_true",
                    help="先发 Ctrl+C 打断板端卡住的命令")
    ap.add_argument("-b", "--bg", action="append", default=[],
                    help="后台执行命令，输出落 /tmp/_sb.log（可重复）")
    args = ap.parse_args()

    s = open_port(args.port, args.baud)
    print("✅ 已连接 %s @ %d（Ctrl+C 退出）\n" % (args.port, args.baud))

    try:
        # 先敲个回车，确认板子在
        s.write(b"\r\n")
        s.flush()
        banner = drain(s, 1.0)
        if banner:
            print(banner, end="")
        else:
            print("（板子暂无回显，可能未上电或该口不是控制台口）\n")

        if args.interrupt:
            s.write(b"\x03")
            s.flush()
            print(send(s, "", max(args.wait, 1.5)), end="")

        if args.bg:
            for cmd in args.bg:
                full = '%s > /tmp/_sb.log 2>&1 &' % cmd
                print("\n$ [BG] %s" % cmd)
                s.write((full + "\r\n").encode("utf-8"))
                s.flush()
                time.sleep(1.0)
                drain(s, 1.0)

        if args.cmd:
            for cmd in args.cmd:
                print("\n$ %s" % cmd)
                print(send(s, cmd, args.wait), end="")
        else:
            # 交互模式：键盘输入 -> 串口，串口输出 -> 屏幕
            while True:
                try:
                    line = input("$ ")
                except EOFError:
                    break
                if line.strip() in ("exit", "quit"):
                    break
                if not line.strip():
                    continue
                print(send(s, line, args.wait), end="")
    except KeyboardInterrupt:
        print("\n（已退出）")
    finally:
        s.close()


if __name__ == "__main__":
    main()
