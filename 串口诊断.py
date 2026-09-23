# -*- coding: utf-8 -*-
"""RK3588 串口连通性诊断工具

用法：双击运行，或  python 串口诊断.py

它会：
  1. 列出本机所有 COM 口
  2. 让你挑一个（或直接回车用第一个）
  3. 依次用常见波特率监听 + 发回车探测对端 shell
  4. 报告每个波特率收到多少字节、内容预览
  5. 给出诊断结论和下一步建议

判断依据：
  · 全程 0 字节        → 板子没上电 / TX-RX 没接对（最常见）
  · 有乱码             → 波特率不对（换一个试试）
  · 出现 login:/#/$    → 通了！板子在跑 Linux console，可以登录跑 board_infer.py
  · 出现 {json}        → 板子已经在跑 board_infer.py，直接去上位机连就行
"""
import sys
import time

try:
    import serial
    import serial.tools.list_ports as list_ports
except ImportError:
    print("缺少 pyserial，请先安装： pip install pyserial")
    input("\n按回车退出...")
    sys.exit(1)

# 常见波特率：RK3588 debug console 标准是 1500000，放最前面
BAUDS = [1500000, 115200, 921600, 460800, 230400, 57600, 38400, 19200, 9600]

LINE = "=" * 66


def list_ports_all():
    return list(list_ports.comports())


def probe(port, baud, listen_sec=2.0, knock_times=3):
    """在一个波特率下：先静默监听，再发回车敲门，返回收到的所有字节"""
    buf = b""
    try:
        s = serial.Serial(port, baud, timeout=0.6)
    except Exception as e:
        return None, "打开失败: %s" % e
    try:
        s.reset_input_buffer()
        # 阶段一：静默监听（板子若已在持续输出，这里就能抓到）
        end = time.time() + listen_sec
        while time.time() < end:
            c = s.read(4096)
            if c:
                buf += c
        # 阶段二：发回车敲门（Linux console 会回显提示符）
        if not buf:
            for _ in range(knock_times):
                try:
                    s.write(b"\r\n")
                except Exception:
                    break
                time.sleep(0.7)
                c = s.read(4096)
                if c:
                    buf += c
                if buf:
                    break
    except Exception as e:
        return buf, "读取异常: %s" % e
    finally:
        try:
            s.close()
        except Exception:
            pass
    return buf, ""


def classify(buf):
    """根据收到的内容判断对端状态"""
    if not buf:
        return "SILENT", "对端无任何回应"
    txt = buf.decode("utf-8", "ignore")
    low = txt.lower()
    # 已经在推 JSON（board_infer.py 在跑）
    if "{" in txt and ('"core0"' in txt or '"frame"' in txt or '"defects"' in txt):
        return "JSON", "★ 板子正在推 JSON！上位机直接连即可"
    # Linux shell 提示符 / 登录提示
    for kw in ("login:", "password:", "# ", "$ ", "root@", "linaro", "ubuntu@",
               "rockchip", "rk3588", "buildroot"):
        if kw in low:
            return "SHELL", "★ 通了！板子在跑 Linux console，可登录后跑 board_infer.py"
    # U-Boot 启动日志
    for kw in ("u-boot", "uboot", "hit any key", "ddr ", "spl"):
        if kw in low:
            return "UBOOT", "板子停在 U-Boot（未进系统），等它启动完或检查烧录"
    # 有字节但不是文本 → 多半波特率不对
    printable = sum(1 for ch in txt if ch.isprintable() or ch in "\r\n\t")
    ratio = printable / max(1, len(txt))
    if ratio < 0.6:
        return "GARBAGE", "收到乱码，波特率不对（换一个试试）"
    return "TEXT", "收到文本，但不是 shell 提示符"


def main():
    print(LINE)
    print(" RK3588 串口连通性诊断")
    print(LINE)

    ports = list_ports_all()
    if not ports:
        print("\n[!] 本机没有任何 COM 口。")
        print("    → 先把 USB-TTL 插到电脑上，再运行本工具。")
        input("\n按回车退出...")
        return

    print("\n本机 COM 口：")
    for i, p in enumerate(ports, 1):
        print("  [%d] %-8s %s" % (i, p.device, p.description or "(无描述)"))

    if len(ports) == 1:
        choice = ports[0].device
        print("\n只有一个串口，自动选择：%s" % choice)
    else:
        raw = input("\n选择要诊断的串口编号（直接回车=1）：").strip()
        try:
            idx = int(raw) if raw else 1
            choice = ports[idx - 1].device
        except Exception:
            print("输入无效，用第一个")
            choice = ports[0].device

    print("\n" + LINE)
    print("开始诊断 %s，依次尝试 %d 种波特率（每种约 4 秒）..." % (choice, len(BAUDS)))
    print("提示：如果板子刚上电，请在看到 'U-Boot' 时立刻重新运行本工具\n" + LINE)

    results = []
    for baud in BAUDS:
        print("\n--- %s @ %d ---" % (choice, baud))
        buf, err = probe(choice, baud)
        if err:
            print("  %s" % err)
            results.append((baud, None, "ERR", err))
            continue
        kind, desc = classify(buf)
        print("  收到 %d 字节  →  %s" % (len(buf), desc))
        if buf:
            preview = buf.decode("utf-8", "ignore")[:400].replace("\r", "")
            print("  预览：")
            for ln in preview.split("\n")[:8]:
                print("    | " + ln)
        results.append((baud, len(buf), kind, desc))
        # 已经明确连通就提前结束，不必继续试
        if kind in ("SHELL", "JSON", "UBOOT"):
            print("\n  [停止] 已确认连通，不再尝试其余波特率。")
            break

    # ---- 结论 ----
    print("\n" + LINE)
    print("诊断结论")
    print(LINE)
    good = [r for r in results if r[2] in ("SHELL", "JSON", "UBOOT")]
    garbage = [r for r in results if r[2] == "GARBAGE"]
    total_bytes = sum(r[1] or 0 for r in results)

    if good:
        baud, n, kind, desc = good[0]
        print("✅ %s @ %d —— %s" % (choice, baud, desc))
        if kind == "SHELL":
            print("\n下一步：")
            print("  1) 用串口工具（MobaXterm/Putty）以 %d 连 %s，登录板子" % (baud, choice))
            print("  2) 板端执行：cd 模型训练 && python3 board_infer.py "
                  "--model best_neu_yolo11n_aug.rknn --source 0 --serial /dev/ttyS0 --baud %d" % baud)
            print("  3) 回到上位机 NPU 监控页 → 数据来源『板端串口』→ 端口 %s、波特率 %d → 连接" % (choice, baud))
        elif kind == "JSON":
            print("\n板子已经在推数据了！上位机 NPU 监控页选『板端串口』→ %s @ %d → 连接即可。"
                  % (choice, baud))
    elif garbage:
        print("⚠️  收到数据但是乱码 —— 波特率不匹配。")
        print("    上面标 GARBAGE 的波特率说明物理链路是通的，换个波特率重试。")
    elif total_bytes == 0:
        print("❌ 所有波特率都是 0 字节 —— 对端完全没有回应。")
        print("\n请按顺序排查：")
        print("  ① 板子上电了吗？（电源灯亮？风扇转？）")
        print("  ② USB-TTL 的 TX/RX 是否交叉接？（板子 TX → 模块 RX，板子 RX → 模块 TX）")
        print("  ③ GND 接了吗？（必须共地，否则数据全是噪声）")
        print("  ④ 接的是不是 debug 串口？（RK3588 通常有 uart2 debug 口，看板子丝印）")
        print("  ⑤ 电压匹配吗？（RK3588 是 3.3V，接 5V 会烧！）")
        print("\n如果板子已上电且线接对了仍无输出，多半是 TX/RX 没交叉或接错口。")
    else:
        print("⚠️  收到了一些数据但不是 shell 提示符，见上方预览自行判断。")

    print("\n" + LINE)
    input("按回车退出...")


if __name__ == "__main__":
    main()
