# -*- coding: utf-8 -*-
"""诊断：上位机检测页的类别来源（演示集 / 下拉框 / 本地引擎）。输出落 tools/_diag_out.txt。

用法（项目根）：.venv/Scripts/python.exe -X utf8 tools/_diag_ui39.py
"""
import os as _os
import sys as _sys

_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"

_OUT = open(os.path.join(_ROOT, "tools", "_diag_out.txt"), "w", encoding="utf-8")


def P(*a):
    _OUT.write(" ".join(str(x) for x in a) + "\n")
    _OUT.flush()


try:
    # 复刻 main.py 的导入顺序：先 infer/torch，再 PyQt5（否则会人为触发 c10.dll 冲突）
    try:
        import infer  # noqa: F401
        import torch
        torch.zeros(1)
    except Exception:
        pass

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    import main as M
    import page_detect as PD

    win = M.MainWindow()
    p = win.pages[0]

    P("[1] page_detect._HAS_INFER =", PD._HAS_INFER)
    P("[2] 演示类别数 _DEMO_DEFECTS =", len(PD._DEMO_DEFECTS))
    P("    前 8 个:", PD._DEMO_DEFECTS[:8])
    P("[3] 模型下拉框条目数 =", p.cb_model.count())
    P("    当前选中 =", p.cb_model.currentText())
    P("    选中 data =", p.cb_model.currentData())
    P("    config.model.path =", p.cfg.get("model", "path") if p.cfg else None)
    P("[4] infer.NAME_ZH 条数 =", len(PD._NAME_ZH))

    P("[4b] p.__class__ =", p.__class__.__module__ + "." + p.__class__.__name__)
    P("[4c] p.engine 现状 =", (type(p.engine).__name__ if p.engine is not None else None))
    if p.engine is not None:
        P("     p.engine.ready =", p.engine.ready, "| err =", p.engine.load_error,
          "| weights =", p.engine.weights)

    eng = p._ensure_engine()
    P("[5] _ensure_engine 返回 =", (type(eng).__name__ if eng is not None else None))
    pe = p.engine
    P("[5b] 调用后 p.engine =", (type(pe).__name__ if pe is not None else None))
    if pe is not None:
        P("     ready =", pe.ready, "| classes =", len(pe.names),
          "| weights =", pe.weights, "| err =", pe.load_error)

    try:
        import glob
        from infer import load_image
        cand = sorted(glob.glob(os.path.join(_ROOT, "图片", "*", "*.jpg")))
        if cand and eng and eng.ready:
            img = load_image(cand[0])
            defs = eng.predict_cv2(img)
            P("[6] 实拍推理:", os.path.basename(cand[0]), "->",
              [(d["name"], round(d["conf"], 2)) for d in sorted(defs, key=lambda x: -x["conf"])[:5]])
        else:
            P("[6] 无图或无引擎:", len(cand))
    except Exception as e:
        P("[6] 跳过:", repr(e))

    win.close()
except Exception as e:
    import traceback
    P("EXCEPTION:", repr(e))
    P(traceback.format_exc())
finally:
    _OUT.write("DONE\n")
    _OUT.close()
