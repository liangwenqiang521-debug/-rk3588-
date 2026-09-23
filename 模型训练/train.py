"""YOLO 缺陷检测训练脚本（自包含，运行于 模型训练/ 目录）。

流程：加载基础权重(yolo11n.pt) -> 在 data.yaml 数据集上训练 -> 产出 best.pt
      -> 额外导出 best.onnx（对应路线图 P2 的 PyTorch→ONNX 步骤，便于后续转 RKNN）

用法：
  python train.py                  # 默认 50 轮
  python train.py --epochs 80 --batch 8 --imgsz 512
  python train.py --no-export     # 跳过 ONNX 导出

输出：
  runs/train/<name>/weights/best.pt
  best.pt  (复制到脚本同级)
  best.onnx (若导出成功)
"""
import argparse
import shutil
from pathlib import Path

import torch
from ultralytics import YOLO

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent  # 缺陷检测项目


def find_base_weights():
    # 优先用脚本同级，其次项目根目录的 yolo11n.pt
    cand = [SCRIPT_DIR / "yolo11n.pt", PROJECT_ROOT / "yolo11n.pt"]
    for c in cand:
        if c.exists():
            return c
    return "yolo11n.pt"  # 让 ultralytics 自行下载


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default=str(SCRIPT_DIR / "data.yaml"))
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--name", type=str, default="defect_yolo11n")
    ap.add_argument("--device", type=str, default="cpu")
    ap.add_argument("--no-export", action="store_true", help="不导出 ONNX")
    ap.add_argument("--resume", type=str, default=None,
                    help="续训：传入已有 run 名(如 neu_yolo11n_aug)，从 last.pt 继续训练")
    args = ap.parse_args()

    if torch.cuda.is_available():
        args.device = "0"
        print("[train] 检测到 CUDA，自动切换到 GPU 训练")

    if args.resume:
        # 续训：从 runs/<resume>/weights/last.pt 继续，沿用原训练的 epochs/data 设定
        last = SCRIPT_DIR / "runs" / args.resume / "weights" / "last.pt"
        if not last.exists():
            raise SystemExit(f"[train] 找不到续训检查点: {last}")
        print(f"[train] 续训模式: {args.resume} (from {last})")
        model = YOLO(str(last))
        results = model.train(resume=True)
    else:
        base = find_base_weights()
        print(f"[train] 基础权重: {base}")
        print(f"[train] 数据集:   {args.data}")
        model = YOLO(str(base))
        results = model.train(
            data=args.data,
            epochs=args.epochs,
            batch=args.batch,
            imgsz=args.imgsz,
            device=args.device,
            name=args.name,
            project=str(SCRIPT_DIR / "runs"),
            workers=2,
            verbose=True,
            patience=15,  # 15 轮无提升则早停
        )

    # 找 best.pt（续训时用 args.resume 作为 run 名，否则用 args.name）
    run_name = args.resume or args.name
    # 找 best.pt（ultralytics project=SCRIPT_DIR/runs, name=run_name -> runs/<run_name>/weights/best.pt）
    best_src = SCRIPT_DIR / "runs" / run_name / "weights" / "best.pt"
    if not best_src.exists():
        found = list((SCRIPT_DIR / "runs").glob(f"**/{run_name}/weights/best.pt"))
        best_src = found[0] if found else None
    if not best_src or not Path(best_src).exists():
        # 兜底：扫描整个 runs 目录
        found = list((SCRIPT_DIR / "runs").glob("**/weights/best.pt"))
        best_src = found[0] if found else None

    if best_src and Path(best_src).exists():
        # 续训产物单独命名，避免覆盖根目录 best.pt（上位机默认模型=defect 4类）
        dst = SCRIPT_DIR / (f"best_{run_name}.pt" if args.resume else "best.pt")
        shutil.copy(str(best_src), str(dst))
        print(f"[train] 已复制 best.pt -> {dst}")
    else:
        print("[train] 未找到 best.pt，请检查 runs/ 目录")

    # 导出 ONNX（路线图 P2）
    if not args.no_export and best_src and Path(best_src).exists():
        try:
            m = YOLO(str(best_src))
            exported = m.export(format="onnx", imgsz=args.imgsz, dynamic=False)
            onnx_path = Path(exported) if isinstance(exported, str) else Path(str(exported))
            print(f"[train] ONNX 导出成功 -> {onnx_path}")
        except Exception as e:
            print(f"[train] ONNX 导出失败（不影响 .pt）: {e}")

    print("[train] 训练完成。")


if __name__ == "__main__":
    main()
