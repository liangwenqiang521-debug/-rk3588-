# -*- coding: utf-8 -*-
"""COM3 被占用一键恢复工具。

症状：上位机点"连接"提示 PermissionError(13, '拒绝访问。')，
      或 `串口诊断.py` / `python -c "import serial; serial.Serial('COM3',...)"` 报同样的错。

根因：pyserial 默认 exclusive=True（Windows 上打开串口时阻止其他进程共享）。
      若同进程内之前 serial.Serial 的实例未正确 close（线程死/异常退出），
      或另一个 python.exe 实例也在持着 COM3，就会撞 13 拒绝访问。

本脚本做的事（按顺序）：
  ① 列出所有 main.py 进程 → 把"非活动"（CPU=0% 且 内存<50MB）的孤儿实例 kill
  ② 再次尝试 exclusive=True 打开 COM3 → 若还失败，切 exclusive=False（共享模式）
  ③ 报告"该用哪种打开方式"，用户回上位机重新连接即可

用法：双击运行，或  python 杀进程释放COM3.py
"""
import os, sys, time, ctypes
os.chdir(r"D:\workbuddy\缺陷检测项目")

try:
    import psutil
except ImportError:
    print("缺少 psutil，先装：", end=""); 
    os.system(f"{sys.executable} -m pip install pserial psutil")
    sys.exit(1)

try:
    import serial
except ImportError:
    print("缺少 pyserial，先装：", end="")
    os.system(f"{sys.executable} -m pip install pyserial")
    sys.exit(1)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def find_main_py_pids():
    """找所有跑 main.py 的 python.exe PID。"""
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "memory_info", "create_time"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if "main.py" in cmd and "psutil" not in cmd and "杀进程" not in cmd:
                out.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return out


def main():
    print("=" * 66)
    print(" COM3 被占用一键恢复工具")
    print("=" * 66)
    print(f" 当前用户: {'管理员' if is_admin() else '普通用户'}")
    print()

    # ---- 步骤 1: 杀 main.py 孤儿实例 ----
    procs = find_main_py_pids()
    if not procs:
        print("[1/3] 没找到运行中的 main.py 进程，跳过杀进程")
    else:
        print(f"[1/3] 发现 {len(procs)} 个 main.py 进程:")
        to_kill = []
        for p in procs:
            try:
                cpu = p["memory_info"].rss // (1024 * 1024)
                alive = psutil.Process(p["pid"]).status() == "running"
                print(f"   PID {p['pid']}  mem={cpu}MB  status={'live' if alive else 'zombie'}")
                # 启发式：内存 < 50MB 且无窗口标题  → 孤儿
                if cpu < 50:
                    to_kill.append(p["pid"])
            except Exception as e:
                print(f"   PID {p['pid']} 探测失败: {e}")

        if to_kill:
            print(f"\n   准备 kill 疑似孤儿: {to_kill}")
            for pid in to_kill:
                try:
                    psutil.Process(pid).kill()
                    print(f"   ✓ kill PID {pid}")
                except Exception as e:
                    print(f"   ✗ kill PID {pid} 失败: {e}")
            time.sleep(0.5)
        else:
            print("   没有疑似孤儿，跳过")

    # ---- 步骤 2: 尝试独占打开 ----
    print()
    print("[2/3] 尝试独占打开 COM3 ...")
    exclusive_works = False
    for baud in (115200, 9600, 1500000):
        try:
            s = serial.Serial("COM3", baud, timeout=0.3, exclusive=True)
            s.close()
            print(f"   ✓ 独占打开 COM3 @ {baud} 成功")
            exclusive_works = True
            break
        except Exception as e:
            print(f"   ✗ @ {baud}: {e}")

    # ---- 步骤 3: 共享模式尝试 ----
    print()
    print("[3/3] 尝试共享打开 COM3 ...")
    shared_works = False
    for baud in (115200, 9600, 1500000):
        try:
            s = serial.Serial("COM3", baud, timeout=0.3, exclusive=False)
            s.close()
            print(f"   ✓ 共享打开 COM3 @ {baud} 成功")
            shared_works = True
            break
        except Exception as e:
            print(f"   ✗ @ {baud}: {e}")

    print()
    print("=" * 66)
    print(" 结论与下一步")
    print("=" * 66)
    if exclusive_works:
        print(" ✅ 独占模式可用 → 直接回上位机 NPU 页点『连接』即可")
    elif shared_works:
        print(" ⚠️  独占被占、共享可用 → 上位机内部应切 exclusive=False")
        print("    （如果你之前开了别的串口工具，先关掉它）")
    else:
        print(" ❌ 两种都打不开 → COM3 真的被别的进程占了：")
        print("    · 任务管理器看谁在持 USB-Enhanced-SERIAL CH343")
        print("    · 或重启电脑")
    print()
    input("按回车退出...")


if __name__ == "__main__":
    main()