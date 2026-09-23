# -*- coding: utf-8 -*-
"""板端冒烟测试：构造主窗口并连本机 board_server(:9000)，验证 PySide6 垫片端口无异常。

运行（板端，无显示用 minimal 平台）：
  QT_QPA_PLATFORM=minimal python3 smoke_test.py
"""
import sys
import time

from PyQt5.QtWidgets import QApplication  # 经 qt_shim 重定向到 PySide6

import main


def main_test():
    app = QApplication(sys.argv)
    app.setStyleSheet(main.QSS)
    win = main.MainWindow()
    win.show()
    app.processEvents()
    # 给事件循环一点时间，让“连接 RK3588”按钮逻辑等就绪
    time.sleep(1.5)
    # 尝试以板端默认配置连接本机 9000（board_server）
    try:
        page = win.pages[0]
        if getattr(page, "cb_edge_mode", None) is not None:
            page.cb_edge_mode.setCurrentIndex(1)  # 网络 TCP
            page.ed_edge_host.setText("127.0.0.1")
            page.ed_edge_port.setText("9000")
            page._toggle_edge()
            time.sleep(2.5)
            connected = bool(page.bridge and page.bridge.isRunning())
            print("EDGE_CONNECTED:", connected)
    except Exception as e:
        print("EDGE_TOGGLE_ERR:", repr(e))
    app.processEvents()
    print("SMOKE OK: MainWindow constructed, pages=%d" % len(win.pages))
    win.close()
    app.quit()


if __name__ == "__main__":
    main_test()
