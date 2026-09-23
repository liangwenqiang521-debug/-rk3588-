# -*- coding: utf-8 -*-
"""检测记录数据库（SQLite）"""
import os
import sqlite3
import csv
import time

BASE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE, "data")
DB_PATH = os.path.join(DB_DIR, "records.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT NOT NULL,
    product TEXT,
    result TEXT,
    defect_type TEXT,
    area REAL,
    confidence REAL,
    image_path TEXT
);
"""


class RecordDB(object):
    # 自动裁剪：记录数超过 MAX_ROWS 时，删除最老的记录。
    # 目的：边缘模式 10fps 连续检测，若不限制会几小时刷出数万条，
    #       导致历史页加载变慢、数据库膨胀。
    MAX_ROWS = 5000
    _CHECK_EVERY = 50          # 每插入 N 条检查一次，避免每条都 count(*)
    _TRIM_KEEP = 4000          # 触发裁剪后保留的条数（留余量，避免频繁触发）

    def __init__(self):
        os.makedirs(DB_DIR, exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()
        self._insert_count = 0

    def insert(self, product, result, defect_type, area, confidence, image_path):
        t = time.strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "INSERT INTO records(time, product, result, defect_type, area, confidence, image_path)"
            " VALUES(?,?,?,?,?,?,?)",
            (t, product, result, defect_type, area, confidence, image_path))
        self.conn.commit()
        self._insert_count += 1
        if self._insert_count >= self._CHECK_EVERY:
            self._insert_count = 0
            # 只有超过 MAX_ROWS 才裁剪，否则记录会一直被压在 _TRIM_KEEP
            if self.count() > self.MAX_ROWS:
                self.trim(self._TRIM_KEEP)
        return t

    def trim(self, keep=4000):
        """保留最近 keep 条，删除更老的记录。返回删除条数。"""
        try:
            cur = self.conn.cursor()
            total = cur.execute("SELECT count(*) FROM records").fetchone()[0]
            if total <= keep:
                return 0
            cur.execute(
                "DELETE FROM records WHERE id NOT IN "
                "(SELECT id FROM records ORDER BY id DESC LIMIT ?)", (keep,))
            n = cur.rowcount
            self.conn.commit()
            return n
        except Exception:
            return 0

    def count(self):
        try:
            return self.conn.execute("SELECT count(*) FROM records").fetchone()[0]
        except Exception:
            return 0

    def query(self, start=None, end=None, product=None, defect=None,
              keyword=None, result=None, limit=500):
        sql = "SELECT id, time, product, result, defect_type, area, confidence, image_path FROM records WHERE 1=1"
        args = []
        if start:
            sql += " AND time >= ?"; args.append(start)
        if end:
            sql += " AND time <= ?"; args.append(end)
        if product and product != "全部":
            sql += " AND product = ?"; args.append(product)
        if defect and defect != "全部":
            sql += " AND defect_type = ?"; args.append(defect)
        if result and result != "全部":
            sql += " AND result = ?"; args.append(result)
        if keyword:
            sql += " AND (image_path LIKE ? OR defect_type LIKE ?)"
            args += ["%%%s%%" % keyword] * 2
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return self.conn.execute(sql, args).fetchall()

    def stats(self, rows=None):
        if rows is None:
            rows = self.query(limit=100000)
        total = len(rows)
        ng = sum(1 for r in rows if r[3] == "NG")
        ok = total - ng
        rate = (ok * 100.0 / total) if total else 0.0
        return {"total": total, "ok": ok, "ng": ng, "rate": rate}

    def products(self):
        rows = self.conn.execute(
            "SELECT DISTINCT product FROM records WHERE product IS NOT NULL").fetchall()
        return [r[0] for r in rows]

    def defect_types(self):
        rows = self.conn.execute(
            "SELECT DISTINCT defect_type FROM records WHERE defect_type NOT IN ('--','') AND defect_type IS NOT NULL").fetchall()
        return [r[0] for r in rows]

    def export_csv(self, path, rows=None):
        if rows is None:
            rows = self.query(limit=100000)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["序号", "时间", "产品", "结果", "缺陷类型",
                        "面积(px)", "置信度", "图像路径"])
            for r in rows:
                w.writerow(r)
        return len(rows)
