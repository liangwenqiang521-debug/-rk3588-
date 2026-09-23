# -*- coding: utf-8 -*-
"""板端连接参数集中配置（公开仓库版）。

设计原则
--------
本模块是**所有板端连接参数的唯一来源**。仓库内任何脚本都不得硬编码 IP / 密码，
一律 `import board_env` 后取用。

参数优先级（从高到低）：
    1. 环境变量          —— 例如 `set BOARD_IP=10.0.0.5`（Windows）/ `export BOARD_IP=...`
    2. 本地私有文件      —— 仓库根目录 `board_env.local.py`（已在 .gitignore 中忽略）
    3. 本模块内置默认值  —— 仅保留 RFC 5737 文档用地址与空密码，**不含真实凭据**

首次使用
--------
    cp board_env.example.py board_env.local.py   # 按需填写真实 IP / 密码
或直接设置环境变量。

注意：`BOARD_PASS` 默认为空字符串——密码认证会自动跳过，请使用 SSH 密钥。
"""
import os

BASE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 默认值
# 下列均为占位地址：169.254.x.x 属 RFC 3927 链路本地段，192.0.2.x 属 RFC 5737 文档段。
# 真实部署请通过环境变量或 board_env.local.py 覆盖。
_DEFAULTS = {
    "BOARD_IP": "",
    "BOARD_USER": "root",
    "BOARD_PASS": "",
    "BOARD_PORT": "22",
    "BOARD_KEY": os.path.expanduser(r"~\.ssh\id_ed25519"),
    "BOARD_STREAM_PORT": "9000",
    "BOARD_SERIAL_PORT": "COM3",
    "BOARD_SERIAL_BAUD": "1500000",
}

# 候选地址（自动探测顺序）。刻意使用文档保留段，避免仓库暴露真实内网拓扑。
FALLBACK_IPS = [
    "169.254.100.100",   # 占位：网线直连（PC 侧 APIPA 段，无需管理员权限）
    "192.0.2.2",         # 占位：按需改为你的板子静态地址
    "192.0.2.20",        # 占位：备用地址
    "192.0.2.12",        # 占位：热点段示例
]


def _load_local():
    """加载 board_env.local.py（若存在），返回其大写变量字典。"""
    path = os.path.join(BASE, "board_env.local.py")
    data = {}
    if not os.path.exists(path):
        return data
    try:
        ns = {}
        with open(path, "r", encoding="utf-8") as f:
            exec(compile(f.read(), path, "exec"), ns)
        for k, v in ns.items():
            if k.isupper() and isinstance(v, (str, int, float)):
                data[k] = str(v)
    except Exception:
        pass
    return data


_LOCAL = _load_local()


def get(name, default=None):
    """按 环境变量 > board_env.local.py > 内置默认值 的顺序取值。"""
    if name in os.environ and os.environ[name].strip() != "":
        return os.environ[name].strip()
    if name in _LOCAL and _LOCAL[name].strip() != "":
        return _LOCAL[name].strip()
    if default is not None:
        return default
    return _DEFAULTS.get(name, "")


def get_int(name, default=0):
    try:
        return int(get(name, ""))
    except Exception:
        return default


def fallback_ips():
    """候选 IP 列表：本地覆盖优先，其后是内置占位列表。"""
    local = get("BOARD_FALLBACK_IPS", "")
    if local:
        return [x.strip() for x in local.split(",") if x.strip()]
    return list(FALLBACK_IPS)


def is_configured():
    """是否已提供真实连接参数（用于给用户友好提示）。"""
    return bool(get("BOARD_IP", "") or get("BOARD_PASS", "") or os.path.exists(
        os.path.join(BASE, "board_env.local.py")))


# ---------------------------------------------------------------- 便捷常量
# 方便 `from board_env import HOST, USER` 这类用法。
HOST = get("BOARD_IP", "")
USER = get("BOARD_USER", "root")
PASS = get("BOARD_PASS", "")
PORT = get_int("BOARD_PORT", 22)
KEY = get("BOARD_KEY", os.path.expanduser(r"~\.ssh\id_ed25519"))
STREAM_PORT = get_int("BOARD_STREAM_PORT", 9000)
SERIAL_PORT = get("BOARD_SERIAL_PORT", "COM3")
SERIAL_BAUD = get_int("BOARD_SERIAL_BAUD", 1500000)
