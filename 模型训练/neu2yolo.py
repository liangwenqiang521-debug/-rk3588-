"""NEU-DET 真实数据集 -> YOLO 格式转换脚本（路线圖 P1）。

NEU surface defect database (NEU-DET)：
  - 1800 张热轧钢带表面灰度图，200x200，6 类缺陷，每类 300 张
  - 类别（顺序即 YOLO class id）：
      0 crazing        龟裂/裂纹
      1 inclusion      夹杂物
      2 patches        斑块/补丁
      3 pitted_surface 麻面/点蚀
      4 rolled-in_scale 轧入氧化皮
      5 scratches      划痕
  - 原始标注为 Pascal VOC XML（单图单类，框覆盖整张缺陷区域）

用法：
  python neu2yolo.py                  # 默认解压 neu_raw/neu.zip 并转换
  python neu2yolo.py --zip neu_raw/neu.zip --out datasets/neu_det --split 0.8

输出：
  datasets/neu_det/images/{train,val}/*.jpg
  datasets/neu_det/labels/{train,val}/*.txt   (YOLO 归一化)
  data_neu.yaml
"""
import argparse
import os
import random
import shutil
import zipfile
from pathlib import Path

import xml.etree.ElementTree as ET

# NEU-DET 6 类（顺序固定，与标注文件名前缀一致）
CLASSES = ["crazing", "inclusion", "patches", "pitted_surface",
           "rolled-in_scale", "scratches"]


def find_images_and_xmls(root: Path):
    """在解压目录里找 images 与对应 XML。返回 [(img_path, xml_path|None), ...]"""
    pairs = []
    # 常见顶层：IMAGES / JPEGImages / images；ANNOTATIONS / Annotations
    img_dirs, xml_dirs = [], []
    for d in root.rglob("*"):
        if d.is_dir():
            low = d.name.lower()
            if low in ("images", "jpegimages"):
                img_dirs.append(d)
            elif low in ("annotations",):
                xml_dirs.append(d)
    if not img_dirs:
        img_dirs = [root]
    if not xml_dirs:
        xml_dirs = [root]

    # 收集所有图片
    imgs = {}
    for d in img_dirs:
        for p in d.iterdir():
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
                imgs[p.stem] = p
    # 收集所有 xml
    xmls = {}
    for d in xml_dirs:
        for p in d.iterdir():
            if p.suffix.lower() == ".xml":
                xmls[p.stem] = p

    # 也处理一种情况：每个缺陷类一个子目录，内含 img + 同名 xml
    if not imgs:
        for p in root.rglob("*"):
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
                imgs[p.stem] = p
        for p in root.rglob("*.xml"):
            xmls[p.stem] = p

    for stem, imgp in imgs.items():
        pairs.append((imgp, xmls.get(stem)))

    # 若数据已自带 train/val 划分（Kaggle 镜像结构），直接按 split 目录返回映射
    split_dirs = sorted({p.parents[1] for p, _ in pairs
                         if p.parents[1].name in ("train", "val")}) if pairs else []
    if len(split_dirs) >= 1:
        # 返回 (img_path, xml_path, split) 三元组
        triples = []
        for imgp, xmlp in pairs:
            sp = imgp.parents[1].name if imgp.parents[1].name in ("train", "val") else "train"
            triples.append((imgp, xmlp, sp))
        return triples
    return pairs


def convert_xml_to_yolo(xml_path: Path, img_w: int, img_h: int):
    """解析 VOC XML，返回 [(cls_id, x_center, y_center, w, h) 归一化]"""
    boxes = []
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    for obj in root.iter("object"):
        name = obj.findtext("name")
        if name is None:
            continue
        name = name.strip().lower()
        if name not in CLASSES:
            # 容忍大小写/空格差异
            name = name.replace(" ", "_")
        if name not in CLASSES:
            print(f"  [warn] 未知类别跳过: {name} in {xml_path.name}")
            continue
        cls_id = CLASSES.index(name)
        bnd = obj.find("bndbox")
        if bnd is None:
            continue
        try:
            xmin = float(bnd.findtext("xmin"))
            ymin = float(bnd.findtext("ymin"))
            xmax = float(bnd.findtext("xmax"))
            ymax = float(bnd.findtext("ymax"))
        except (TypeError, ValueError):
            continue
        # 裁切到图像边界并防 0 尺寸
        xmin = max(0.0, min(xmin, img_w))
        ymin = max(0.0, min(ymin, img_h))
        xmax = max(0.0, min(xmax, img_w))
        ymax = max(0.0, min(ymax, img_h))
        w = xmax - xmin
        h = ymax - ymin
        if w <= 1 or h <= 1:
            continue
        xc = (xmin + xmax) / 2.0 / img_w
        yc = (ymin + ymax) / 2.0 / img_h
        nw = w / img_w
        nh = h / img_h
        boxes.append((cls_id, xc, yc, nw, nh))
    return boxes


_MISSING_XML = 0


def _convert_one(out: Path, imgp: Path, xmlp, sp: str, cls_counter: "Counter"):
    """复制一张图片并写 YOLO 标注；返回是否成功。"""
    global _MISSING_XML
    dst_img = out / "images" / sp / (imgp.stem + ".jpg")
    try:
        shutil.copyfile(str(imgp), str(dst_img))
    except Exception as e:
        print(f"  [warn] 复制图片失败 {imgp}: {e}")
        return False
    label_path = out / "labels" / sp / (imgp.stem + ".txt")
    if xmlp is None:
        _MISSING_XML += 1
        label_path.write_text("")
        return True
    try:
        import cv2
        im = cv2.imread(str(imgp))
        ih, iw = im.shape[:2]
    except Exception:
        iw, ih = 200, 200
    boxes = convert_xml_to_yolo(xmlp, iw, ih)
    for cls_id, xc, yc, nw, nh in boxes:
        cls_counter[cls_id] += 1
    with open(str(label_path), "w", encoding="utf-8") as f:
        for cls_id, xc, yc, nw, nh in boxes:
            f.write(f"{cls_id} {xc:.6f} {yc:.6f} {nw:.6f} {nh:.6f}\n")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=str, default=str(Path(__file__).resolve().parent / "neu_raw" / "neu.zip"))
    ap.add_argument("--src", type=str, default=None,
                    help="若已解压，直接指定根目录（含 IMAGES/ANNOTATIONS 或 img+xml）")
    ap.add_argument("--out", type=str, default=str(Path(__file__).resolve().parent / "datasets" / "neu_det"))
    ap.add_argument("--split", type=float, default=0.8, help="train 比例")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "images" / "train").mkdir(parents=True)
    (out / "images" / "val").mkdir(parents=True)
    (out / "labels" / "train").mkdir(parents=True)
    (out / "labels" / "val").mkdir(parents=True)

    # 1) 准备解压目录
    extract_root = None
    if args.src:
        extract_root = Path(args.src)
    else:
        zip_path = Path(args.zip)
        if not zip_path.exists():
            raise SystemExit(f"未找到 zip: {zip_path}\n请先运行下载（或手动放到 neu_raw/neu.zip）")
        extract_root = zip_path.parent / "unzip"
        if extract_root.exists():
            shutil.rmtree(extract_root)
        print(f"[neu2yolo] 解压 {zip_path} -> {extract_root}")
        with zipfile.ZipFile(str(zip_path), "r") as z:
            z.extractall(str(extract_root))

    print(f"[neu2yolo] 扫描图片与标注: {extract_root}")
    pairs = find_images_and_xmls(extract_root)
    print(f"  找到图片 {len(pairs)} 张")

    # 2) 转换并复制
    from collections import Counter
    cls_counter = Counter()
    global _MISSING_XML
    _MISSING_XML = 0

    has_split = bool(pairs) and len(pairs[0]) == 3
    if has_split:
        for imgp, xmlp, sp in pairs:
            _convert_one(out, imgp, xmlp, sp, cls_counter)
    else:
        rng = random.Random(args.seed)
        stems = [p[0].stem for p in pairs]
        rng.shuffle(stems)
        n_train = int(round(len(stems) * args.split))
        pmap = {p[0].stem: (p[0], p[1]) for p in pairs}
        for i, stem in enumerate(stems):
            imgp, xmlp = pmap[stem]
            sp = "train" if i < n_train else "val"
            _convert_one(out, imgp, xmlp, sp, cls_counter)

    missing_xml = _MISSING_XML

    # 3) 写 data_neu.yaml
    yaml_path = Path(__file__).resolve().parent / "data_neu.yaml"
    abs_out = out.resolve()
    with open(str(yaml_path), "w", encoding="utf-8") as f:
        f.write(f"# NEU-DET 真实钢材表面缺陷数据集（自动生成 by neu2yolo.py）\n")
        f.write(f"path: {abs_out}\n")
        f.write(f"train: images/train\n")
        f.write(f"val: images/val\n")
        f.write(f"nc: {len(CLASSES)}\n")
        f.write(f"names: {CLASSES}\n")

    print(f"\n[neu2yolo] 完成")
    print(f"  train={n_train} val={len(stems)-n_train} 总计={len(stems)}")
    print(f"  无对应 XML 的图片: {missing_xml}")
    print(f"  类别样本数(框): " + ", ".join(f"{CLASSES[k]}={v}" for k, v in sorted(cls_counter.items())))
    print(f"  data_neu.yaml -> {yaml_path}")


if __name__ == "__main__":
    main()
