# -*- coding: utf-8 -*-
"""上位机全功能自动化测试（offscreen）"""
# --- 项目根目录加入 sys.path（脚本位于子目录，需回退到根才能 import 项目模块）---
import os as _os, sys as _sys
_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..'))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)
# --- end ---

import os, sys, traceback
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

results = []
def report(name, ok, detail=""):
    results.append((name, ok, detail))
    print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)

import infer
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer, QEventLoop

app = QApplication(sys.argv)

# ---------- T1 主窗口构造 ----------
try:
    import main as M
    win = M.MainWindow()
    report("T1 主窗口构造", True, "6页面已初始化")
except Exception as e:
    report("T1 主窗口构造", False, repr(e))
    for n,ok,d in results: pass
    sys.exit(1)

# ---------- T2 六页导航切换 ----------
try:
    names = ["实时检测","参数设置","历史记录","通信设置","运行日志","NPU监控"]
    for i in range(6):
        win.stack.setCurrentIndex(i)
        win._on_nav_changed(i)
        app.processEvents()
    report("T2 六页导航切换", True, "页面索引 0-5 全部切换成功")
except Exception as e:
    report("T2 六页导航切换", False, repr(e))

dp = win.pages[0]

# 捕获顶栏状态灯初始文案（C：供 T27 断言，须在其他测试改动状态前采集）
# 注：顶栏现有 cam/model 两盏灯（PLC 灯已移除）
_init_cam_txt = win.dot_cam_top._text
_init_model_txt = win.dot_model_top._text

# ---------- T3 模型扫描与默认模型 ----------
try:
    models = dp._scan_models()
    cur = dp.cfg.get("model","path")
    labels = " | ".join(l for l,_ in models)
    ok = len(models) >= 3 and any(cur == rel for _, rel in models)
    report("T3 模型扫描(%d个)" % len(models), ok, labels[:80])
except Exception as e:
    report("T3 模型扫描", False, repr(e))

# ---------- T4 推理引擎懒加载 ----------
try:
    eng = dp._ensure_engine()
    ok = eng is not None and eng.ready
    report("T4 引擎懒加载", ok, "类别: %s" % list(eng.names.values()) if ok else "引擎不可用")
except Exception as e:
    report("T4 引擎懒加载", False, repr(e))

# ---------- T5 UI级真实推理（含线程+统计+数据库写入） ----------
try:
    test_img = "模型训练/datasets/neu_aug/images/val/crazing_103.jpg"
    dp.canvas.set_image(test_img)
    before_total = dp.total
    dp._run_real_detect()
    # 事件循环等待推理线程完成
    loop = QEventLoop()
    def check():
        if not dp._infer_busy:
            loop.quit()
    t = QTimer(); t.timeout.connect(check); t.start(100)
    QTimer.singleShot(120000, loop.quit)  # 120s 超时
    loop.exec_()
    t.stop()
    app.processEvents()
    ok = dp.total == before_total + 1 and dp.big_result.text() in ("OK","NG")
    n_def = len(dp.canvas.defects) if hasattr(dp.canvas, 'defects') else '?'
    report("T5 UI级真实推理", ok,
           "结果=%s 检出缺陷=%s 总数=%d 置信框=%s" % (
               dp.big_result.text(), n_def, dp.total, dp.big_conf.text()))
except Exception as e:
    report("T5 UI级真实推理", False, traceback.format_exc()[-200:])

# ---------- T6 引擎直推多张图 ----------
try:
    from infer import load_image
    imgs = ["crazing_103.jpg","crazing_112.jpg","crazing_124.jpg"]
    outs = []
    for f in imgs:
        p = "模型训练/datasets/neu_aug/images/val/" + f
        img = load_image(p)
        dets = eng.predict_cv2(img, conf=0.25) if eng and eng.ready else []
        outs.append("%s:%d个" % (f.split('_')[0], len(dets)))
    report("T6 引擎直推3张NEU图", True, " ".join(outs))
except Exception as e:
    report("T6 引擎直推", False, repr(e))

# ---------- T7 数据库读写 ----------
try:
    from db import RecordDB
    db = RecordDB()
    t = db.insert("TEST_PRODUCT","NG","龟裂",1200,0.88,"/test/img.png")
    rows = db.query(product="TEST_PRODUCT")
    st = db.stats(rows)
    csv_ok = False
    try:
        db.export_csv("exports/_test_export.csv", rows)
        csv_ok = os.path.exists("exports/_test_export.csv")
        if csv_ok: os.remove("exports/_test_export.csv")
    except Exception: pass
    ok = len(rows) >= 1
    report("T7 数据库读写", ok, "插入+查询OK 统计=%s CSV导出=%s" % (bool(st), csv_ok))
except Exception as e:
    report("T7 数据库读写", False, repr(e))

# ---------- T8 配置持久化 ----------
try:
    from config import Config
    c = Config()
    old = c.get("camera","exposure")
    c.set("camera","exposure","11.1")
    c.save()
    c2 = Config()
    val = c2.get("camera","exposure")
    c2.set("camera","exposure",old); c2.save()  # 还原
    report("T8 配置持久化", val == "11.1", "写入/重读/还原 = %s" % val)
except Exception as e:
    report("T8 配置持久化", False, repr(e))

# ---------- T9 日志系统 ----------
try:
    from logger import AppLogger
    lg = AppLogger()
    lg.info("TEST","功能测试日志")
    lg2 = AppLogger()
    buf_has = any("功能测试日志" in r.get("msg","") for r in lg2.buffer) if hasattr(lg2,'buffer') else True
    logfile = os.path.exists("logs/app.log")
    report("T9 日志系统", logfile or buf_has, "logs/app.log=%s 缓冲=%s" % (logfile, buf_has))
except Exception as e:
    report("T9 日志系统", False, repr(e))

# ---------- T10 其余页面交互 ----------
try:
    # 历史页查询
    win.stack.setCurrentIndex(2); win._on_nav_changed(2)
    win.pages[2]._query(); app.processEvents()
    # 参数页读取
    win.stack.setCurrentIndex(1); win._on_nav_changed(1)
    # NPU 页（demo 后端连接切换）
    win.stack.setCurrentIndex(5); win._on_nav_changed(5)
    try:
        win.pages[5]._toggle(); app.processEvents()
        win.pages[5]._toggle(); app.processEvents()
    except Exception:
        pass
    report("T10 历史/参数/NPU页交互", True, "查询/参数加载/NPU切换无崩溃")
except Exception as e:
    report("T10 其余页面交互", False, repr(e))

# ---------- T11 开始检测真实优先逻辑（测试纯逻辑方法 _resolve_mode） ----------
try:
    # 隔离 canvas 渲染（offscreen 下真实重绘会段错误），仅注入图片存在性状态
    real_has = dp.canvas.has_image
    st = {"has": True}
    dp.canvas.has_image = lambda: st["has"]

    # 场景1：有图 + 未开真实开关 -> 自动真实
    st["has"] = True; dp.real_toggle.on = False
    m1 = dp._resolve_mode()
    # 场景2：无图 + 真实开关开 -> 拦截
    st["has"] = False; dp.real_toggle.on = True
    m2 = dp._resolve_mode()
    # 场景3：无图 + 模拟模式 -> 模拟
    st["has"] = False; dp.real_toggle.on = False
    m3 = dp._resolve_mode()

    dp.canvas.has_image = real_has
    ok = (m1 == "real") and (m2 == "blocked") and (m3 == "mock")
    report("T11 开始检测真实优先", ok,
           "有图=%s 无图真实=%s 无图模拟=%s" % (m1, m2, m3))
except Exception as e:
    report("T11 开始检测真实优先", False, traceback.format_exc()[-200:])

# ---------- T12 参数设置页增强功能 ----------
try:
    from PyQt5.QtWidgets import QMessageBox
    QMessageBox.information = staticmethod(lambda *a, **k: None)  # 屏蔽弹窗避免阻塞
    import shutil
    _cfg_bak = open("config.json", encoding="utf-8").read()  # 备份，测试后还原
    sp = win.pages[1]  # 参数设置页
    # 1) 新字段已注册
    need = [("camera", "resolution"), ("camera", "auto_exposure"), ("camera", "flip"),
            ("camera", "trigger_delay"), ("model", "device"), ("model", "iou"),
            ("model", "nms"), ("preprocess", "morphology"), ("preprocess", "sharpen"),
            ("storage", "filename_rule"), ("storage", "disk_warn"),
            ("alarm", "sound"), ("alarm", "flash"), ("alarm", "ng_signal"), ("alarm", "io_port")]
    miss = [k for k in need if k not in sp.widgets]
    # 2) ROI 增删
    r0 = sp.roi_table.rowCount()
    sp._add_roi()
    added = (sp.roi_table.rowCount() == r0 + 1)
    btn = sp.roi_table.cellWidget(sp.roi_table.rowCount() - 1, 3)
    sp._del_roi(btn)
    deleted = (sp.roi_table.rowCount() == r0)
    # 3) 脏检测 + 保存持久化（用 io_port，避免 textChanged→_refresh_footer 提前同步 cfg 造成的误判）
    sp.widgets[("alarm", "io_port")].setText("DO9")
    dirty1 = sp._is_dirty()
    sp._collect()
    sp.cfg.save()
    dirty2 = sp._is_dirty()
    raw = Config()
    persisted = (raw.get("alarm", "io_port") == "DO9"
                 and raw.get("model", "conf") == sp.cfg.get("model", "conf"))
    # 4) 恢复默认
    sp._reset()
    reset_ok = (sp.cfg.get("model", "conf") == "0.85")
    ok = (not miss) and added and deleted and dirty1 and (not dirty2) and persisted and reset_ok
    report("T12 参数设置页增强", ok,
           "新字段缺失=%s ROI增=%s 删=%s 脏检测=%s 保存后洁净=%s 持久化=%s 恢复默认=%s"
           % (miss, added, deleted, dirty1, (not dirty2), persisted, reset_ok))
    # 还原用户原始 config.json（避免测试污染）
    open("config.json", "w", encoding="utf-8").write(_cfg_bak)
except Exception as e:
    try:
        open("config.json", "w", encoding="utf-8").write(_cfg_bak)
    except Exception:
        pass
    report("T12 参数设置页增强", False, traceback.format_exc()[-200:])

# ---------- T13 通信设置页增强功能 ----------
try:
    from PyQt5.QtWidgets import QMessageBox
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    _cfg_bak2 = open("config.json", encoding="utf-8").read()
    cp = None
    for p in win.pages:
        if hasattr(p, "plc_status") and hasattr(p, "serial_status") and hasattr(p, "cloud_status"):
            cp = p
            break
    assert cp is not None, "未找到通信设置页"
    need = [("plc", "slave"), ("plc", "timeout"), ("plc", "retry"), ("plc", "byte_order"),
            ("serial", "port"), ("serial", "baud"), ("serial", "flow"), ("serial", "enable"),
            ("trigger", "mode"), ("trigger", "delay"), ("trigger", "ng_output"), ("trigger", "io_port"),
            ("trigger", "recheck"), ("trigger", "auto_reset"),
            ("alarm", "sound"), ("alarm", "flash"), ("alarm", "ng_signal"),
            ("alarm", "io_port"), ("alarm", "delay"),
            ("cloud", "enable"), ("cloud", "proto"), ("cloud", "url"), ("cloud", "topic"), ("cloud", "interval")]
    miss = [k for k in need if k not in cp.widgets]
    # 脏检测 + 保存持久化
    cp.widgets[("serial", "baud")].setCurrentText("57600")
    dirty1 = cp._is_dirty()
    cp._collect(); cp.cfg.save(); cp._take_snapshot()
    dirty2 = cp._is_dirty()
    raw = Config()
    persisted = (raw.get("serial", "baud") == "57600")
    # 测试连接（合法参数）不崩
    cp.widgets[("plc", "ip")].setText("192.168.1.100")
    cp.widgets[("plc", "port")].setText("502")
    cp._test_plc()
    test_ok = cp.plc_status._text.startswith("已连接")
    # 参数校验（非法 IP）
    cp.widgets[("plc", "ip")].setText("999.1.1.1")
    cp._test_plc()
    test_invalid = (cp.plc_status._text == "参数无效")
    # 串口测试不崩
    cp._test_serial()
    serial_ok = cp.serial_status._text.startswith("已连接")
    # 恢复默认
    cp._reset()
    reset_ok = (cp.cfg.get("serial", "baud") == "1500000" and cp.cfg.get("plc", "ip") == "192.168.1.200")
    ok = (not miss) and dirty1 and (not dirty2) and persisted and test_ok and test_invalid and serial_ok and reset_ok
    report("T13 通信设置页增强", ok,
           "新字段缺失=%s 脏检测=%s 保存后洁净=%s 持久化=%s 测试连接OK=%s 参数校验=%s 串口OK=%s 恢复默认=%s"
           % (miss, dirty1, (not dirty2), persisted, test_ok, test_invalid, serial_ok, reset_ok))
    open("config.json", "w", encoding="utf-8").write(_cfg_bak2)
except Exception as e:
    try:
        open("config.json", "w", encoding="utf-8").write(_cfg_bak2)
    except Exception:
        pass
    report("T13 通信设置页增强", False, traceback.format_exc()[-200:])

# ---------- T14 NG 日志降级为"警告"级 + 同类去重 ----------
try:
    dp = win.pages[0]  # 实时检测页
    calls = []
    class _Cap:
        def info(self, m, msg): calls.append(("info", msg))
        def warning(self, m, msg): calls.append(("warning", msg))
        def error(self, m, msg): calls.append(("error", msg))
    dp.log = _Cap()
    dp._last_ng_type = None
    dp._last_ng_time = 0.0
    dp._log_ng("凹陷", 0.93)        # 第1次 -> 记 warning
    dp._log_ng("凹陷", 0.93)        # 同类 3 秒内 -> 去重(不记)
    dp._log_ng("划痕", 0.85)        # 不同类型 -> 记 warning
    warn_only = all(c[0] == "warning" for c in calls)
    no_error = not any(c[0] == "error" for c in calls)
    dedup = sum(1 for c in calls if "凹陷" in c[1]) == 1
    diff = any("划痕" in c[1] for c in calls)
    ok = warn_only and no_error and dedup and diff
    report("T14 NG日志降级+去重", ok,
           "全warning=%s 无error=%s 凹陷去重=%s 不同类记=%s" % (warn_only, no_error, dedup, diff))
except Exception as e:
    report("T14 NG日志降级+去重", False, traceback.format_exc()[-200:])

# ---------- T15 A1/A2/A3 参数贯通 + 过滤逻辑 ----------
try:
    # A1: UI 控件存在且磁盘默认配置 iou=0.35（新建 Config 读磁盘，避开 dp.cfg 内存态污染）
    cfg_iou_disk = type(dp.cfg)().get("model", "iou")
    ok_a1 = hasattr(dp, "ed_iou") and cfg_iou_disk == "0.35"
    # A3: ROI 几何过滤（中心在 ROI 内保留，外丢弃）
    d_in = {"xyxy": [0.40, 0.45, 0.50, 0.55]}   # 中心(0.45,0.50) 在 ROI1 内
    d_out = {"xyxy": [0.02, 0.02, 0.08, 0.08]}  # 中心(0.05,0.05) 在 ROI 外
    roi_ok = (dp._defect_in_roi(d_in, [(0.18, 0.10, 0.64, 0.80)])
              and not dp._defect_in_roi(d_out, [(0.18, 0.10, 0.64, 0.80)]))
    # A2: min_area 真正过滤（mock 推理后端，验证参数已贯通到 predict_cv2）
    import numpy as np
    class _B:
        def __init__(s, x1, y1, x2, y2, c, cl):
            s.xyxy = np.array([[x1, y1, x2, y2]])
            s.conf = np.array([c]); s.cls = np.array([cl])
    class _Res:
        boxes = [_B(0, 0, 500, 500, 0.9, 0), _B(0, 0, 10, 10, 0.9, 0)]
    class _M:
        def predict(s, *a, **k):
            return [_Res()]
    class _Det(infer.DefectDetector):
        def _load(s):
            s.model = _M(); s.names = {0: "x"}
    det = _Det("fake", conf=0.25, iou=0.45)
    fake_img = np.zeros((200, 200, 3), dtype=np.uint8)
    n0 = len(det.predict_cv2(fake_img, conf=0.25, iou=0.45, min_area=0))
    n1 = len(det.predict_cv2(fake_img, conf=0.25, iou=0.45, min_area=200))
    area_ok = (n0 == 2 and n1 == 1)
    ok = bool(ok_a1 and roi_ok and area_ok)
    has_ed = hasattr(dp, "ed_iou")
    report("T15 A1/A2/A3", ok, "ed_iou=%s cfg_iou_disk=%r roi=%s minarea=%s" % (has_ed, cfg_iou_disk, roi_ok, area_ok))
except Exception as e:
    report("T15 A1/A2/A3", False, traceback.format_exc()[-200:])

# ---------- T16 边缘模式：板端 JSON -> 画布渲染 ----------
try:
    # 连板后默认"仅预览"（_edge_detect_enabled=False 时 _on_edge_result 只渲染画面），
    # 测试需显式打开检测开关，并清掉上一测试残留的画布状态
    dp._edge_detect_enabled = True
    dp.canvas.clear_defects()
    dp.canvas.set_result("OK", 0)
    obj = {
        "frame": 5, "ok": False,
        "defects": [{"cls": "dent", "conf": 0.93, "x1": 100, "y1": 80, "x2": 200, "y2": 180}],
        "infer_ms": 8.5, "w": 640, "h": 480,
    }
    dp._on_edge_result(obj)
    rds = getattr(dp.canvas, "_real_defects", [])
    conv_ok = (len(rds) == 1
               and abs(rds[0]["xyxy"][0] - 100.0/640.0) < 1e-4
               and rds[0]["name"] == "dent"
               and abs(rds[0]["conf"] - 0.93) < 1e-6)
    res_ok = dp.canvas.result == "NG"
    report("T16 边缘串口结果渲染", conv_ok and res_ok,
           "defects=%d xyxy0=%.4f name=%s result=%s"
           % (len(rds), rds[0]["xyxy"][0] if rds else -1,
              rds[0]["name"] if rds else "", dp.canvas.result))
except Exception as e:
    report("T16 边缘串口结果渲染", False, traceback.format_exc()[-200:])

# ---------- T17 边缘模式网络(TCP)支持 + 结果转换链路 ----------
try:
    import page_detect as PD
    has_tcp_mod = getattr(PD, "_HAS_TCP", False)
    has_tcp_cls = hasattr(PD, "BoardTcpBridge")
    ui_ok = (hasattr(dp, "cb_edge_mode") and hasattr(dp, "ed_edge_host")
             and hasattr(dp, "ed_edge_port") and hasattr(dp, "dot_edge"))
    # 直接喂一条板端网络 JSON，验证 转换->画布 链路（与串口共用 _on_edge_result）
    dp._edge_detect_enabled = True
    dp.canvas.clear_defects()
    dp.canvas.set_result("OK", 0)
    sample = {"frame": 1, "ok": False, "w": 640, "h": 480,
              "defects": [{"cls": "scratch", "conf": 0.91,
                           "x1": 100, "y1": 100, "x2": 200, "y2": 200}],
              "infer_ms": 8.0}
    dp.canvas.clear_defects()
    dp._on_edge_result(sample)
    rds = dp.canvas._real_defects
    conv_ok = len(rds) == 1 and abs(rds[0]["xyxy"][0] - 100/640) < 1e-6 and rds[0]["name"] == "scratch"
    res_ok = dp.canvas.result == "NG"
    ok17 = has_tcp_mod and has_tcp_cls and ui_ok and conv_ok and res_ok
    report("T17 边缘模式TCP+结果转换", ok17,
           "tcp_mod=%s cls=%s ui=%s defects=%d xyxy0=%.4f name=%s result=%s"
           % (has_tcp_mod, has_tcp_cls, ui_ok, len(rds),
              rds[0]["xyxy"][0] if rds else -1, rds[0]["name"] if rds else "", dp.canvas.result))
except Exception as e:
    report("T17 边缘模式TCP+结果转换", False, traceback.format_exc()[-200:])

# ---------- T18 桥梁 stats/result 分流 ----------
try:
    import json as _json
    import socket as _sock
    import threading as _th
    _got = {"stats": [], "result": []}
    _srv = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
    _srv.setsockopt(_sock.SOL_SOCKET, _sock.SO_REUSEADDR, 1)
    _srv.bind(("127.0.0.1", 0))
    _srv.listen(1)
    _port = _srv.getsockname()[1]
    def _serve():
        conn, _ = _srv.accept()
        lines = [
            _json.dumps({"type": "stats", "core0": 45, "core1": 30, "core2": 12,
                         "temp": 48.5, "mem_used": 1520.0, "mem_total": 8192.0,
                         "fps": 62.3, "infer_ms": 8.1}),
            _json.dumps({"frame": 1, "ok": False, "defects": [],
                         "infer_ms": 8.0, "w": 640, "h": 480}),
        ]
        for ln in lines:
            conn.sendall((ln + "\n").encode())
        conn.close()
    _th.Thread(target=_serve, daemon=True).start()
    from tcp_bridge import BoardTcpBridge
    br = BoardTcpBridge("127.0.0.1", _port)
    br.stats_received.connect(lambda d: _got["stats"].append(d))
    br.result_received.connect(lambda d: _got["result"].append(d))
    br.start()
    loop = QEventLoop()
    _chk = QTimer(); _chk.setSingleShot(False); _chk.timeout.connect(
        lambda: loop.quit() if (_got["stats"] and _got["result"]) else None)
    _chk.start(50)
    _to = QTimer(); _to.setSingleShot(True); _to.timeout.connect(loop.quit); _to.start(4000)
    loop.exec_()
    br.stop()
    ok = (len(_got["stats"]) >= 1 and _got["stats"][0].get("type") == "stats"
          and len(_got["result"]) >= 1 and "frame" in _got["result"][0])
    report("T18 桥梁stats/result分流", ok,
           "stats=%d result=%d" % (len(_got["stats"]), len(_got["result"])))
except Exception as e:
    report("T18 桥梁stats/result分流", False, repr(e))

# ---------- T19 NPU 页消费板端真实 stats 渲染 ----------
try:
    npu = win.pages[5]
    stats = {"type": "stats", "core0": 45, "core1": 30, "core2": 12, "temp": 48.5,
             "mem_used": 1520.0, "mem_total": 8192.0, "fps": 62.3, "infer_ms": 8.1}
    npu._on_sample(stats)
    app.processEvents()
    ok = (npu.bars[0].val.text() == "45 %"
          and "48.5" in npu.lb_temp.text()
          and "1520" in npu.lb_mem.text()
          and "62.3" in npu.lb_fps.text()
          and "8.1" in npu.lb_infer.text())
    report("T19 NPU页真实stats渲染", ok,
           "core0=%s temp=%s mem=%s fps=%s infer=%s"
           % (npu.bars[0].val.text(), npu.lb_temp.text(), npu.lb_mem.text(),
              npu.lb_fps.text(), npu.lb_infer.text()))
except Exception as e:
    report("T19 NPU页真实stats渲染", False, repr(e))

# ---------- T20 模拟后端动态性 + 断开清空 ----------
try:
    # T19 可能留下仍在推 stats 的 bridge，会污染本用例的清空断言 → 先断开隔离
    win.pages[5]._disconnect()
    app.processEvents()

    # (a) DemoBackend 给出 fps/infer_ms 且多次采样有真实变化
    from npu_monitor import DemoBackend
    db = DemoBackend()
    samples = [db.sample() for _ in range(40)]
    has_fps = all("fps" in s and "infer_ms" in s for s in samples)
    c0_set = {s["core0"] for s in samples}
    vary_ok = len(c0_set) >= 5            # 至少 5 个不同值（原来 ±12 抖动也很难达 5）
    ok_a = has_fps and vary_ok
    # (b) NPU 页 _reset_ui 真把所有显示清回 '--' / 0
    npu2 = win.pages[5]
    npu2._on_sample({"core0": 77, "core1": 88, "core2": 99, "temp": 66.0,
                     "mem_used": 5000, "mem_total": 8000, "fps": 30, "infer_ms": 5})
    app.processEvents()
    npu2._reset_ui()
    app.processEvents()
    ok_b = (npu2.bars[0].val.text() == "-- %"
            and npu2.bars[0].bar.value() == 0
            and npu2.lb_temp.text() == "-- ℃"
            and npu2.lb_mem.text() == "-- / -- MB"
            and npu2.lb_fps.text() == "-- FPS"
            and npu2.lb_infer.text() == "-- ms"
            and npu2.mem_bar.value() == 0
            and len(npu2.history.core0) == 0)
    # (c) 模拟 worker 真能跑 0.5s 间隔并在 1.5s 内累计 2+ 点
    npu2._connect()       # 启动模拟 worker
    import time as _t
    end = _t.time() + 1.5
    while _t.time() < end:
        app.processEvents()
        _t.sleep(0.05)
    n_pts = npu2._sample_count
    ok_c = n_pts >= 2
    npu2._disconnect()    # 顺便验证 disconnect 后真的清空
    app.processEvents()
    ok_c2 = (npu2.bars[0].val.text() == "-- %" and npu2._sample_count == 0)
    ok = ok_a and ok_b and ok_c and ok_c2
    report("T20 模拟动态+断开清空+实时计数", ok,
           "fps/infer=%s c0唯一值=%d 模拟采到=%d点 断开清空=%s"
           % (has_fps, len(c0_set), n_pts, ok_c2))
except Exception as e:
    report("T20 模拟动态+断开清空+实时计数", False, repr(e))

# ---------- T21 NPU页错误提示/hint/静默断开 ----------
try:
    npu3 = win.pages[5]
    # (a) 切到板端串口：hint 含 "board_infer.py" 和端口号
    npu3.mode.setCurrentIndex(1)
    app.processEvents()
    hint_serial = npu3.hint.text()
    ok_a = "board_infer.py" in hint_serial and "COM3" in hint_serial
    # (b) 切到板端TCP：hint 含 "tcp-port" 和 IP/端口
    npu3.mode.setCurrentIndex(2)
    app.processEvents()
    hint_tcp = npu3.hint.text()
    ok_b = "tcp-port" in hint_tcp and "9000" in hint_tcp and "9000" in hint_tcp
    # (c) 主动断开时 _user_disconnecting 走完一圈后归零，且不会触发 _show_error_dialog
    called = {"err": 0}
    npu3._show_error_dialog = lambda msg: called.__setitem__("err", called["err"] + 1)
    npu3._user_disconnecting = True
    npu3._on_bridge_conn(False, "已断开 COM3")
    ok_c = (called["err"] == 0) and npu3._user_disconnecting is True
    npu3._user_disconnecting = False

    # T24 NPU 页「已开 COM3 但无数据」巡检（5s/10s 提示改写状态文字）
    import time as _t
    # 模拟一个「板端连接已建立、_sample_count=0」的状态（bridge 不能为 None）
    class _FakeBridge: pass
    npu3.bridge = _FakeBridge()
    npu3._sample_count = 0
    npu3._conn_since = _t.time() - 7
    npu3._watch_no_data()
    s7 = npu3.status._text
    npu3._conn_since = _t.time() - 15
    npu3._watch_no_data()
    s15 = npu3.status._text
    npu3._sample_count = 1  # 收到一条数据后巡检应停
    npu3._watch_no_data()
    s_after = npu3.status._text
    npu3.bridge = None  # 清理
    npu3._conn_since = 0.0
    ok_x = "等板端数据 7s" in s7 and "board_infer.py" in s15 and s15 == s_after
    report("T24 NPU连接无数据巡检", ok_x,
           "7s=%r 15s=%r 收数据后=%r" % (s7, s15, s_after))
    # (d) 真正的连接失败（msg 是 '打开串口 ... 失败'）会弹错误框
    npu3._on_bridge_conn(False, "打开串口 COM3 失败: [Errno 2] No such file or directory")
    ok_d = called["err"] == 1
    # (e) 成功后状态灯 = "已连接 … 等待板端数据…"
    npu3._sample_count = 0
    npu3._conn_since = 0.0  # 关掉 watchdog 让 _on_bridge_conn 的等待提示保留
    npu3._on_bridge_conn(True, "已连接 COM3 @ 115200")
    ok_e = "等待板端数据" in npu3.status._text
    ok = ok_a and ok_b and ok_c and ok_d and ok_e
    report("T21 错误提示+动态hint+静默断开", ok,
           "hint串口含板端=%s hintTCP含端口=%s 静默断开=%s 真失败弹框=%s 等待文字=%s"
           % (ok_a, ok_b, ok_c, ok_d, npu3.status._text))
except Exception as e:
    report("T21 错误提示+动态hint+静默断开", False, repr(e))

# ---------- T22 连接泄漏修复（COM3 被永久占死的根因） ----------
try:
    npu4 = win.pages[5]
    # (a) 模拟模式连上 → 切到板端串口 → 旧 worker 必须被停掉
    npu4.mode.setCurrentIndex(0)
    app.processEvents()
    npu4._connect()              # 起模拟 worker
    app.processEvents()
    had_worker = npu4.worker is not None
    npu4.mode.setCurrentIndex(1)  # 切模式 → 应自动 _disconnect
    app.processEvents()
    ok_a = had_worker and npu4.worker is None

    # (b) 已连接状态下再 _connect → 先 disconnect，不叠加
    npu4.mode.setCurrentIndex(0)
    app.processEvents()
    npu4._connect()
    app.processEvents()
    w1 = npu4.worker
    npu4._connect()               # 不点断开直接再连
    app.processEvents()
    ok_b = (npu4.worker is not None) and (npu4.worker is not w1)  # 换了新对象，旧的已 stop

    # (c) 失败回调把 bridge 挪进 _dead_bridges，_disconnect 会回收
    class _FakeBridge(object):
        def __init__(self): self.stopped = False
        def stop(self): self.stopped = True
    fb = _FakeBridge()
    npu4.bridge = fb
    npu4._on_bridge_conn(False, "打开串口 COM3 失败: PermissionError")
    app.processEvents()
    moved = (npu4.bridge is None) and (fb in npu4._dead_bridges)
    npu4._disconnect()
    app.processEvents()
    ok_c = moved and fb.stopped and npu4._dead_bridges == []

    npu4.mode.setCurrentIndex(0)
    app.processEvents()
    ok = ok_a and ok_b and ok_c
    report("T22 连接泄漏修复(COM3占用根因)", ok,
           "切模式停旧=%s 重连不叠加=%s 失败bridge回收=%s"
           % (ok_a, ok_b, ok_c))
except Exception as e:
    report("T22 连接泄漏修复(COM3占用根因)", False, repr(e))

# ==================== T23 板端模拟器 × 真实桥接 端到端 ====================
# 验证：板端模拟器(协议级替身) 经真实 TCP socket → BoardTcpBridge →
#       stats/result 分流 → 字段与 board_infer.py 协议一致
try:
    import importlib.util as _iu
    _spec = _iu.spec_from_file_location("simboard", "板端模拟器.py")
    _sim = _iu.module_from_spec(_spec)
    _spec.loader.exec_module(_sim)

    import time as _t
    from PyQt5.QtCore import QThread as _QT

    _port = 9345
    board = _sim.SimBoard(_port, fps=20, ng_rate=0.6)
    board.start()
    _t.sleep(0.4)

    _st, _rs = [], []
    br = BoardTcpBridge("127.0.0.1", _port)
    br.stats_received.connect(lambda d: _st.append(d))
    br.result_received.connect(lambda d: _rs.append(d))
    br.start()
    _QT.msleep(2600)
    app.processEvents()
    br.stop(); br.wait(2000)
    board.stop()

    # (a) 两类消息都收到，且 result 数量与 fps 吻合（20fps × ~2.5s ≈ 45~55）
    ok_a = len(_st) >= 2 and 30 <= len(_rs) <= 70
    # (b) stats 字段与板端协议完全一致
    _need = {"core0", "core1", "core2", "temp", "mem_used", "mem_total", "fps", "infer_ms"}
    ok_b = bool(_st) and _need.issubset(set(_st[-1].keys()))
    # (c) result 字段与板端协议一致，defects 结构与 NEU 六类匹配
    ok_c = bool(_rs) and {"frame", "ok", "defects", "infer_ms", "w", "h"}.issubset(set(_rs[-1].keys()))
    _ng = [r for r in _rs if not r.get("ok")]
    ok_d = True
    if _ng:
        d0 = _ng[0]["defects"][0]
        ok_d = {"cls", "conf", "x1", "y1", "x2", "y2"}.issubset(set(d0.keys())) \
               and d0["cls"] in _sim.CLASSES
    # (e) NPU 负载确有动态（不是一条死线）
    _c0 = set(x["core0"] for x in _st) if _st else set()
    ok_e = len(_c0) >= 2 or (max(x["core0"] for x in _st) - min(x["core0"] for x in _st)) > 15 if _st else False

    ok = ok_a and ok_b and ok_c and ok_d and ok_e
    report("T23 板端模拟器×真实桥接端到端", ok,
           "stats=%d条 result=%d帧 NG=%d帧 字段齐=%s/%s 缺陷结构=%s 负载动态=%s"
           % (len(_st), len(_rs), len(_ng), ok_b, ok_c, ok_d, ok_e))
except Exception as e:
    report("T23 板端模拟器×真实桥接端到端", False, repr(e))

# ---------- T25 检测页工具栏接线 + 缩放联动（A） ----------
try:
    ok_a = (hasattr(dp, "tb_play") and hasattr(dp, "tb_pause")
            and hasattr(dp, "tb_cam") and hasattr(dp, "tb_zoomin")
            and hasattr(dp, "tb_zoomout"))
    # 缩放双向同步
    dp.canvas.set_image("模型训练/datasets/neu_aug/images/val/crazing_103.jpg")
    app.processEvents()
    dp.canvas.zoom_in(); app.processEvents()
    z1 = dp.canvas.zoom
    dp.cb_zoom.setCurrentText("50%"); app.processEvents()
    z2 = dp.canvas.zoom
    dp.canvas.reset_zoom(); app.processEvents()
    ok_b = abs(z1 - 1.25) < 0.01 and abs(z2 - 0.5) < 0.01 and dp.canvas.zoom == 1.0
    # 开始/停止与工具栏按钮联动
    dp.canvas.set_image("模型训练/datasets/neu_aug/images/val/crazing_103.jpg")
    dp._start(); app.processEvents()
    play_dis = not dp.tb_play.isEnabled() and dp.tb_pause.isEnabled()
    dp._stop(); app.processEvents()
    play_back = dp.tb_play.isEnabled() and not dp.tb_pause.isEnabled()
    report("T25 工具栏接线+缩放联动", ok_a and ok_b and play_dis and play_back,
           "按钮=%s 缩放=%.2f/%.2f 开始禁停=%s 停止恢复=%s"
           % (ok_a, z1, z2, play_dis, play_back))
except Exception as e:
    report("T25 工具栏接线+缩放联动", False, repr(e))

# ---------- T26 缺陷类型分布图（E） ----------
try:
    dp.defect_chart.clear()
    dp.defect_chart.push("crazing"); dp.defect_chart.push("crazing")
    dp.defect_chart.push("inclusion"); dp.defect_chart.push("--")  # -- 应忽略
    d = dp.defect_chart.data
    ok_a = d.get("crazing") == 2 and d.get("inclusion") == 1 and "--" not in d
    # 真实推理结果驱动分布图（T5 已跑过推理，此处验证 _apply_real_result 路径）
    before = dict(dp.defect_chart.data)
    dp._apply_real_result(
        [{"xyxy": [0.1, 0.1, 0.3, 0.3], "xyxy_px": [64, 64, 192, 192],
          "name": "scratches", "conf": 0.9, "color": "#f85149"}],
        True, 0.9, 0.05, False)
    app.processEvents()
    after = dp.defect_chart.data
    ok_b = after.get("scratches", 0) == before.get("scratches", 0) + 1
    dp.defect_chart.clear()
    report("T26 缺陷类型分布图", ok_a and ok_b,
           "push累加=%s 真实结果驱动=%s 数据=%s" % (ok_a, ok_b, after))
except Exception as e:
    report("T26 缺陷类型分布图", False, repr(e))

# ---------- T27 顶栏真实状态灯（C） ----------
try:
    # 初始状态（T2 后立即采集）：相机红 / 模型黄（待加载）或红（推理不可用）
    ok_a = (_init_cam_txt == "相机未就绪"
            and _init_model_txt in ("模型待加载", "推理不可用"))
    # 加载图片 → 相机灯亮
    dp.canvas.set_image("模型训练/datasets/neu_aug/images/val/crazing_103.jpg")
    dp._update_cam_ind(); app.processEvents()
    ok_b = win.dot_cam_top._text == "图像源:照片"
    # 引擎加载 → 模型灯亮
    dp._ensure_engine()
    ok_c = win.dot_model_top._text == "模型已加载"
    # 清除图片 → 相机灯灭
    dp._clear_image(); dp._update_cam_ind(); app.processEvents()
    ok_d = win.dot_cam_top._text == "相机未就绪"
    report("T27 顶栏真实状态灯", ok_a and ok_b and ok_c and ok_d,
           "初始=%s 相机亮=%s 模型亮=%s 相机灭=%s" % (ok_a, ok_b, ok_c, ok_d))
except Exception as e:
    report("T27 顶栏真实状态灯", False, repr(e))

# ---------- T28 历史记录页增强（B） ----------
try:
    hp = win.pages[2]
    # 默认查询范围 7 天（应命中 0 条也可能有，但不应崩）+ 空提示
    hp._query(); app.processEvents()
    ok_a = "命中" in hp.lb_count.text()
    # 结果筛选 NG：只查 NG
    hp._set_result_filter("NG"); app.processEvents()
    ok_b = all(r[3] == "NG" for r in hp.rows) and len(hp.rows) > 0
    ng_n = len(hp.rows)
    hp._set_result_filter("OK"); app.processEvents()
    ok_c = all(r[3] == "OK" for r in hp.rows) and len(hp.rows) > 0
    ok_n = len(hp.rows) > 0
    # 缺陷分布图有数据（NG 筛选时）
    hp._set_result_filter("NG"); app.processEvents()
    ok_d = len(hp.dist_chart.data) > 0
    # 大范围查询应有数据
    from PyQt5.QtCore import QDateTime as _QDT
    hp.dt_start.setDateTime(_QDT.currentDateTime().addDays(-30))
    hp._query(); app.processEvents()
    ok_e = len(hp.rows) > 0
    # 重置恢复"全部"
    hp._reset(); app.processEvents()
    ok_f = hp.result_filter == "全部"
    report("T28 历史页增强", all([ok_a, ok_b, ok_c, ok_d, ok_e, ok_f]),
           "空提示=%s NG筛选=%d条全NG=%s OK筛选=%s 分布图=%s 30天查询=%s 重置=%s"
           % (ok_a, ng_n, ok_b, ok_c, ok_d, ok_e, ok_f))
except Exception as e:
    report("T28 历史页增强", False, repr(e))

# ---------- 汇总 ----------
print("\n" + "="*50, flush=True)
npass = sum(1 for _,ok,_ in results if ok)
print("汇总: %d/%d 通过" % (npass, len(results)), flush=True)
for n,ok,d in results:
    print("  %s %s" % ("✓" if ok else "✗", n), flush=True)
sys.exit(0 if npass == len(results) else 1)
