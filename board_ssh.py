# -*- coding: utf-8 -*-
"""RK3588 开发板(ATK-DLRK3588)远程运维工具。

默认走 SSH 密钥免密登录（已部署本机公钥到板子 /root/.ssh/authorized_keys），
密钥不可用时自动回落到密码登录。

用法:
    python board_ssh.py "ip addr; uname -a"          # 执行任意命令(; 分隔多条)
    python board_ssh.py --script cmds.txt            # 批量执行(每行一条, 支持多行命令)
    python board_ssh.py --net                        # 查看网络/WiFi 状态
    python board_ssh.py --put local.file /root/x     # 上传
    python board_ssh.py --get /root/x local.file     # 下载

环境变量覆盖: BOARD_IP / BOARD_USER / BOARD_PASS / BOARD_KEY
（也可写入 board_env.local.py，见 board_env.example.py）
"""
import os
import sys
import stat
import socket
import argparse

import paramiko

import board_env

# 连接参数统一来自 board_env（环境变量 > board_env.local.py > 占位默认值）。
# 真实 IP / 密码请不要写进代码——见 board_env.example.py。
HOST = board_env.get("BOARD_IP", "")
FALLBACKS = board_env.fallback_ips()
USER = board_env.get("BOARD_USER", "root")
PASS = board_env.get("BOARD_PASS", "")
PORT = board_env.get_int("BOARD_PORT", 22)
KEY = os.path.expanduser(board_env.get("BOARD_KEY", r"~\.ssh\id_ed25519"))
TIMEOUT = 15


def candidates():
    """去重后的候选地址列表，BOARD_IP 排最前。"""
    seen, out = set(), []
    for h in ([HOST] if HOST else []) + FALLBACKS:
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _tcp_alive(host, wait=1.5):
    """快速 TCP 探活，避免对不可达地址白等 SSH 超时。"""
    s = socket.socket()
    s.settimeout(wait)
    try:
        s.connect((host, PORT))
        return True
    except Exception:
        return False
    finally:
        s.close()


def connect(verbose=True):
    """依次探测候选地址；每个可达地址先试密钥认证，失败回落密码。"""
    last = None
    for host in candidates():
        if not _tcp_alive(host):
            if verbose:
                print("[板子] %s 不可达，跳过" % host)
            continue
        use_keys = [True, False] if (KEY and os.path.exists(KEY)) else [False]
        for use_key in use_keys:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                kw = dict(timeout=TIMEOUT, allow_agent=False, look_for_keys=False)
                if use_key:
                    c.connect(host, PORT, USER, key_filename=KEY, **kw)
                else:
                    c.connect(host, PORT, USER, PASS, **kw)
                if verbose:
                    print("[板子] 已连接 %s:%d（%s认证）"
                          % (host, PORT, "密钥" if use_key else "密码"))
                return c
            except Exception as e:
                last = e
                c.close()
    raise SystemExit(
        "[板子] 所有候选地址均无法连接：%s\n最后错误：%s\n"
        "提示：确认网线插好；或先运行 配置板子直连.bat（需管理员权限）。"
        % (", ".join(candidates()), last))


def run(c, cmd, timeout=None):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout or TIMEOUT)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    return out, err, code


def run_many(c, cmds, show_cmd=True, timeout=None):
    for cmd in cmds:
        cmd = cmd.rstrip("\n").strip()
        if not cmd or cmd.startswith("#"):
            continue
        out, err, code = run(c, cmd, timeout)
        if show_cmd:
            print(f"\n$ {cmd}   [exit={code}]")
        if out.strip():
            print(out.rstrip())
        if err.strip():
            print("[stderr]", err.rstrip())
    print()


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("cmd", nargs="?", help="要执行的命令(支持用 ; 分隔多条)")
    ap.add_argument("--script", help="命令脚本文件，每行一条")
    ap.add_argument("--net", action="store_true", help="查看网络/WiFi 状态")
    ap.add_argument("--put", nargs=2, metavar=("LOCAL", "REMOTE"))
    ap.add_argument("--get", nargs=2, metavar=("REMOTE", "LOCAL"))
    ap.add_argument("--timeout", type=int, default=TIMEOUT)
    args = ap.parse_args()

    c = connect()
    try:
        if args.put:
            local, remote = args.put
            sftp = c.open_sftp()
            sftp.put(local, remote)
            st = sftp.stat(remote)
            sftp.chmod(remote, st.st_mode | stat.S_IXUSR)
            sftp.close()
            print(f"uploaded {local} -> {remote}")
            return
        if args.get:
            remote, local = args.get
            sftp = c.open_sftp()
            sftp.get(remote, local)
            sftp.close()
            print(f"downloaded {remote} -> {local}")
            return
        if args.net:
            cmds = ["ip -br addr", "ip route", "connmanctl services | head -6",
                    "iw dev wlan0 link", "rfkill list | grep -A2 'Wireless LAN'"]
            run_many(c, cmds)
            return
        if args.script:
            with open(args.script, "r", encoding="utf-8") as f:
                cmds = f.readlines()
            run_many(c, cmds, timeout=args.timeout)
            return
        if args.cmd:
            cmds = [x for x in args.cmd.split(";") if x.strip()]
            run_many(c, cmds, timeout=args.timeout)
            return
        ap.print_help()
    finally:
        c.close()


if __name__ == "__main__":
    main()
