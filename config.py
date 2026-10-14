# -*- coding: utf-8 -*-
"""配置持久化：config.json 读写"""
import json
import os
import copy

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")

DEFAULTS = {
    "camera": {
        "name": "相机 01", "resolution": "1920×1080", "exposure": "10.0",
        "gain": "2.0", "light": "128", "trigger": "连续触发",
        "trigger_delay": "0", "fps": "30 FPS", "flip": "无",
        "auto_exposure": True,
    },
    "model": {
        "name": "合成缺陷_v1 (4类·mAP50=0.94)",
        "path": "模型训练/runs/defect_yolo11n/weights/best.pt",
        "input_size": "640×640", "device": "CPU", "conf": "0.85",
        "min_area": "50", "iou": "0.45", "nms": "启用",
    },
    "preprocess": {
        "resize": "不缩放（保持原始）", "gray": "启用",
        "denoise": "中值滤波（3×3）", "clahe": "关闭",
        "morphology": "关闭", "sharpen": "关闭",
    },
    "storage": {
        "save_path": "D:/Inspect/Images", "save_ng": True,
        "save_raw": True, "clean": "磁盘空间 < 10% 时删除",
        "filename_rule": "{日期}_{序号}_{结果}", "disk_warn": "10",
    },
    "plc": {
        "enable": True, "proto": "Modbus TCP", "ip": "192.168.1.200",
        "port": "2000", "slave": "1", "heartbeat": "500",
        "timeout": "3000", "retry": "3", "byte_order": "大端 (ABCD)",
    },
    "serial": {
        "enable": False, "port": "COM3", "baud": "1500000",
        "databits": "8", "stopbits": "1", "parity": "无 (N)",
        "flow": "无", "timeout": "1000",
    },
    "edge": {
        "mode": "serial", "host": "", "port": "9000",
        "auto_connect": True,
        # 10-09：把存图/入库等重 IO 丢到后台线程池，避免边缘高帧率时主线程被磁盘拖慢。
        # 需回退到"主线程同步落盘"时改 False。
        "async_io": True,
    },
    "trigger": {
        "mode": "PLC 触发", "delay": "0", "ng_output": True,
        "io_port": "DO1", "recheck": "1", "auto_reset": True,
    },
    "cloud": {
        "enable": False, "proto": "MQTT", "url": "mqtt://broker:1883",
        "topic": "factory/inspect", "interval": "5",
    },
    "alarm": {
        "sound": True, "flash": True, "ng_signal": False, "io_port": "DO1",
        "delay": "0",
    },
}


class Config(object):
    def __init__(self):
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                for section, kv in saved.items():
                    if section in self.data and isinstance(kv, dict):
                        self.data[section].update(kv)
            except Exception:
                pass
        return self.data

    def save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def reset(self):
        self.data = copy.deepcopy(DEFAULTS)
        self.save()

    def get(self, section, key, default=""):
        return self.data.get(section, {}).get(key, default)

    def set(self, section, key, value):
        self.data.setdefault(section, {})[key] = value
