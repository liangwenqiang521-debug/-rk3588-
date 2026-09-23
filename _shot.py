# -*- coding: utf-8 -*-
import os, sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import infer
from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)
import main as M
app.setStyleSheet(M.QSS)
win = M.MainWindow()
win.resize(1440, 900)
win.show()
app.processEvents()
# 加载一张图让检测页更真实
try:
    win.pages[0].canvas.set_image("模型训练/datasets/neu_aug/images/val/crazing_103.jpg")
    app.processEvents()
except Exception as e:
    print("img load skip:", e)
out = sys.argv[1] if len(sys.argv) > 1 else "ui_before.png"
win.grab().save(out)
print("saved", out)
