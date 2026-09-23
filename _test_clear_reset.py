# -*- coding: utf-8 -*-
"""清除照片/打开照片 清场 回归测试（offscreen）"""
import os, sys, faulthandler
faulthandler.enable()
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)

# 屏蔽自动连接（真板子推流会覆盖注入结果）
import page_detect as PD
PD.DetectPage._auto_connect = lambda self: None
PD.DetectPage._auto_retry = lambda self: None

import main as M
win = M.MainWindow()
dp = win.pages[0]

fails = []
def check(name, ok, detail=""):
    print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    if not ok:
        fails.append(name)

dp._edge_detect_enabled = True

# ---- 1) 注入 NG 结果（框 + 角标 + 右侧面板）----
obj = {"frame": 1, "ok": False, "w": 640, "h": 480,
       "defects": [{"cls": "inclusion", "conf": 0.85,
                    "x1": 100, "y1": 80, "x2": 300, "y2": 420}],
       "infer_ms": 8.0}
dp._on_edge_result(obj)
app.processEvents()
check("注入NG-画布有框有角标",
      dp.canvas.result == "NG" and len(dp.canvas._real_defects) == 1)

# ---- 2) 清除照片 → 框/角标/面板应全部复原 ----
dp._clear_image()
app.processEvents()
check("清除后-画布角标清空", dp.canvas.result is None,
      "result=%r" % (dp.canvas.result,))
check("清除后-检测框清空", len(dp.canvas._real_defects) == 0)
check("清除后-右侧面板回待机",
      dp.big_result.text() == "--" and dp.big_conf.text() == "置信度: --")
check("清除后-图片已清", not dp.canvas.has_image())

# ---- 3) 打开新照片 → 旧结果同样应清空 ----
# 用假对话框替换模块属性（不动 PyQt5 类本身，避免段错误）
img = os.path.abspath("图片/scratches/scratches_108.jpg")
if not os.path.exists(img):
    img = os.path.abspath("模型训练/datasets/neu_aug/images/val/crazing_103.jpg")
assert os.path.exists(img), "测试图片不存在: %s" % img

class _FakeFD:
    @staticmethod
    def getOpenFileName(*a, **k):
        return (img, "")
PD.QFileDialog = _FakeFD

try:
    dp._open_image()
    app.processEvents()
    check("打开新照片-图片已加载", dp.canvas.has_image())
    # 再注入一次 NG，然后重新打开同一张照片，验证残留被清
    dp._on_edge_result(obj)
    app.processEvents()
    check("打开后注入NG-有结果", dp.canvas.result == "NG" and len(dp.canvas._real_defects) == 1)
    dp._open_image()
    app.processEvents()
    check("重新打开-旧结果被清",
          dp.canvas.result is None and len(dp.canvas._real_defects) == 0
          and dp.big_result.text() == "--")
except Exception:
    import traceback
    print(traceback.format_exc())
    check("打开照片流程", False, "异常")

# ---- 4) 渲染不崩 ----
pix = dp.canvas.grab()
check("渲染", not pix.isNull())

print("")
if fails:
    print("失败 %d 项: %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("全部通过（清除/打开照片清场）")
sys.exit(0)
