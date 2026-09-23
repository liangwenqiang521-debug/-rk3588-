"""缺陷检测推理脚本（用训练得到的 best.pt 对新图片/文件夹做检测）。

用法：
  python predict.py --source ../datasets/defect_synthetic/images/val   # 验证集
  python predict.py --source D:/path/to/one.jpg --conf 0.3
  python predict.py --source folder --weights best.pt --out predict_output

输出：在 --out 目录生成带检测框的图，并打印每图缺陷数量。
"""
import argparse
from pathlib import Path

import cv2
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=str, required=True, help="图片路径或文件夹")
    ap.add_argument("--weights", type=str, default=str(SCRIPT_DIR / "best.pt"))
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--out", type=str, default=str(SCRIPT_DIR / "predict_output"))
    args = ap.parse_args()

    model = YOLO(args.weights)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    names = model.names

    results = model.predict(source=args.source, conf=args.conf, save=False, stream=True)
    for r in results:
        im = r.orig_img.copy()
        for b in r.boxes:
            x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
            cls = int(b.cls[0])
            conf = float(b.conf[0])
            label = f"{names[cls]} {conf:.2f}"
            cv2.rectangle(im, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(im, label, (x1, max(0, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        save_path = out_dir / Path(r.path).name
        ok, buf = cv2.imencode(".png", im)
        if ok:
            with open(str(save_path), "wb") as f:
                f.write(buf.tobytes())
        print(f"{Path(r.path).name}: {len(r.boxes)} 个缺陷")


if __name__ == "__main__":
    main()
