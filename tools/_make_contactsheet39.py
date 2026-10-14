# -*- coding: utf-8 -*-
"""把 tools/_stage39/ 的 42 张样本拼成一张联络图，便于一眼看清板端现在有哪些样本。

注意：项目路径含中文 → cv2.imread/imwrite 会静默失败，必须 np.fromfile + imdecode，
      写盘用 cv2.imencode(...)[1].tofile(...)。
用法：  .venv/Scripts/python.exe tools/_make_contactsheet39.py
"""
import os
import glob
import numpy as np
import cv2

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE = os.path.join(_ROOT, 'tools', '_stage39')
OUT = os.path.join(_ROOT, 'tools', '_samples39_contact_sheet.png')

THUMB = 168
PAD = 6
HEAD = 22
COLS = 7


def imread_u(p):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)


def imwrite_u(p, img):
    ext = os.path.splitext(p)[1] or '.png'
    cv2.imencode(ext, img)[1].tofile(p)


def main():
    files = sorted(glob.glob(os.path.join(STAGE, '*.jpg')))
    rows = (len(files) + COLS - 1) // COLS
    cw, ch = THUMB, THUMB + HEAD
    canvas = np.full((rows * ch + PAD, COLS * cw + PAD, 3), 245, np.uint8)

    for i, f in enumerate(files):
        img = imread_u(f)
        if img is None:
            continue
        r, c = divmod(i, COLS)
        t = cv2.resize(img, (THUMB, THUMB), interpolation=cv2.INTER_AREA)
        y0 = r * ch + PAD
        x0 = c * cw + PAD
        canvas[y0 + HEAD:y0 + HEAD + THUMB, x0:x0 + THUMB] = t
        cv2.rectangle(canvas, (x0, y0), (x0 + THUMB, y0 + THUMB + HEAD), (190, 190, 190), 1)
        label = os.path.splitext(os.path.basename(f))[0]
        label = label if len(label) <= 22 else label[:22]
        cv2.putText(canvas, label, (x0 + 3, y0 + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (20, 20, 20), 1, cv2.LINE_AA)

    imwrite_u(OUT, canvas)
    print('已生成 %s  (%dx%d, %d 张)' % (OUT, canvas.shape[1], canvas.shape[0], len(files)))


if __name__ == '__main__':
    main()
