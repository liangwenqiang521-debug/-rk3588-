# -*- coding: utf-8 -*-
"""PC <-> RK3588 直连链路体检"""
import subprocess, socket, sys, platform

# 目标网段与静态地址来自 board_env（避免在公开仓库里写死内网拓扑）
try:
    import board_env
    _fb = board_env.fallback_ips()
    BOARD_STATIC_IP = board_env.get("BOARD_STATIC_IP", "") or (_fb[1] if len(_fb) > 1 else "192.0.2.2")
except Exception:
    BOARD_STATIC_IP = "192.0.2.2"
BOARD_NET = ".".join(BOARD_STATIC_IP.split(".")[:3]) + "."

def hr(t):
    print("\n" + "=" * 60)
    print(t)
    print("=" * 60)

hr("1. PC 网卡与 IPv4 地址 (ipconfig)")
try:
    r = subprocess.run(["ipconfig"], capture_output=True, text=True,
                       encoding="gbk", errors="replace", timeout=30)
    cur = None
    for line in r.stdout.splitlines():
        s = line.strip()
        if not s:
            continue
        if "适配器" in s and ":" in s:
            cur = s
            print("\n-- " + s)
        elif ("IPv4" in s or "自动配置 IPv4" in s or "自动配置" in s) or "媒体已断开" in s or "媒体状态" in s:
            print("   " + s)
except Exception as e:
    print("ERR:", e)

hr("2. 网线直连网段的网卡")
try:
    r = subprocess.run(["ipconfig"], capture_output=True, text=True,
                       encoding="gbk", errors="replace", timeout=30)
    blocks = r.stdout.split("适配器")
    for b in blocks:
        if BOARD_NET in b:
            print("适配器" + b.strip())
except Exception as e:
    print("ERR:", e)

hr("3. PING %s" % BOARD_STATIC_IP)
try:
    r = subprocess.run(["ping", "-n", "4", "-w", "1000", BOARD_STATIC_IP],
                       capture_output=True, text=True, encoding="gbk",
                       errors="replace", timeout=40)
    print(r.stdout.strip())
except Exception as e:
    print("ERR:", e)

hr("4. ARP 表 (%s)" % BOARD_STATIC_IP)
try:
    r = subprocess.run(["arp", "-a"], capture_output=True, text=True,
                       encoding="gbk", errors="replace", timeout=20)
    hit = [l for l in r.stdout.splitlines() if BOARD_NET in l]
    print("\n".join(hit) if hit else "(ARP 中无 %s 条目 -> 二层未通)" % BOARD_NET)
except Exception as e:
    print("ERR:", e)

hr("5. TCP 端口连通性")
for port, name in [(22, "SSH"), (9000, "板端推理服务"), (9001, "备用")]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(4)
    try:
        s.connect((BOARD_STATIC_IP, port))
        print(f"  TCP {port:5d} ({name})  -> ✅ 可达")
    except socket.timeout:
        print(f"  TCP {port:5d} ({name})  -> ❌ 超时")
    except ConnectionRefusedError:
        print(f"  TCP {port:5d} ({name})  -> ⚠️ 拒绝(主机在, 端口未监听)")
    except OSError as e:
        print(f"  TCP {port:5d} ({name})  -> ❌ {e}")
    finally:
        s.close()

hr("6. 结论")
