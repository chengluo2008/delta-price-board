#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取四种品质的变卖物价格，写成静态 JSON。

谁会用到它？
  1) GitHub Actions：每 15 分钟自动跑一次，把最新数据打进要发布的网站里；
  2) 你自己在本机跑：`python scripts/fetch_data.py`，生成 docs/data/*.json，
     这样就算本地数据接口连不上，页面也能读这份"上次的数据"。

输出文件：
  docs/data/prices.json        蓝色 + 紫色（首屏用）
  docs/data/grade-gold.json    金色
  docs/data/grade-red.json     红色
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from server import GRADE_CN, fetch_grade_with_retry, normalize_item  # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "data")
ALL_GRADES = ("blue", "purple", "gold", "red")
REQUIRED = ("blue", "purple")


def build_grade(key, attempts=4):
    rows, update_time = fetch_grade_with_retry(GRADE_CN[key], attempts=attempts)
    items = []
    for row in rows:
        item = normalize_item(row, key)
        if item:
            items.append(item)
    items.sort(key=lambda x: -x["price"])
    return {"ok": True, "grade": key, "updatedAt": update_time, "items": items}


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def write_json(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    results, failures = {}, {}

    for key in ALL_GRADES:
        try:
            results[key] = build_grade(key)
            print("[ok] %s：%d 件，数据时间 %s"
                  % (GRADE_CN[key], len(results[key]["items"]), results[key]["updatedAt"]))
        except Exception as exc:  # noqa: BLE001
            failures[key] = str(exc)
            print("[warn] %s 抓取失败：%s" % (GRADE_CN[key], exc))
        time.sleep(0.6)  # 有礼貌一点，别连着猛敲数据站

    # 抓不到就沿用旧文件，别把好好的数据覆盖成空的
    for key, error in failures.items():
        old = read_json(os.path.join(OUT_DIR, "grade-%s.json" % key))
        if old and old.get("items"):
            results[key] = old
            print("[keep] %s 继续使用上一次的数据" % GRADE_CN[key])
        elif key in REQUIRED:
            raise SystemExit("关键品质「%s」没抓到，且本地没有旧数据，任务失败：%s" % (GRADE_CN[key], error))

    if "blue" not in results or "purple" not in results:
        raise SystemExit("蓝色/紫色数据缺失，任务失败")

    for key, payload in results.items():
        write_json(os.path.join(OUT_DIR, "grade-%s.json" % key), payload)

    overview = {
        "ok": True,
        "source": "DerGame 小Der数据报",
        "sourceUrl": "https://dergame.cn/?type=armory",
        "updatedAt": results["blue"].get("updatedAt") or results["purple"].get("updatedAt"),
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "blue": results["blue"]["items"],
        "purple": results["purple"]["items"],
        "counts": {
            "blue": len(results["blue"]["items"]),
            "purple": len(results["purple"]["items"]),
        },
    }
    write_json(os.path.join(OUT_DIR, "prices.json"), overview)
    print("[done] 已写入 %s" % OUT_DIR)


if __name__ == "__main__":
    main()
