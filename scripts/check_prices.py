#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
价格核对工具：把「榜单价格」和「小时价格曲线」逐条对比，找出数据站里明显错误的条目。

用法：
    python scripts/check_prices.py

结果会打印在屏幕上，同时写入 data/price_check.json。

背景：数据站的榜单接口偶尔会张冠李戴（同一个物品，榜单价和它自己的曲线差好几倍）。
已知问题：植物样本（榜单长期报 ~9.2 万，实际 ~1.8 万），已在 server.py 里自动纠正。
"""

import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "price_check.json")

SEARCH = "https://dergame.cn/api/Items/search"
CHART = "https://dergame.cn/api/Items/chartData"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0 Safari/537.36",
    "Origin": "https://dergame.cn",
    "Referer": "https://dergame.cn/",
}
THRESHOLD = 25.0  # 偏差超过 25% 就算异常


def post(url, payload, tries=4):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5)
    raise last


def chart_last_price(item_id):
    data = post(CHART, {"itemId": item_id, "chartType": 7})
    values = data.get("values") or []
    if not values:
        return None
    try:
        return float(values[-1].get("avg_price") or 0)
    except (TypeError, ValueError):
        return None


def main():
    all_items = []
    for grade in ("蓝色", "紫色", "金色", "红色"):
        data = post(SEARCH, {"type": ["收集品"], "grade": [grade]})
        all_items.extend(data.get("data") or [])
        time.sleep(1)

    print("总物品数：%d" % len(all_items))
    bad = []
    for index, item in enumerate(all_items, 1):
        price = float((item.get("value") or {}).get("new") or 0)
        try:
            chart_price = chart_last_price(item["id"])
        except Exception as exc:  # noqa: BLE001
            print("[%3d/%3d] %s 曲线获取失败：%s" % (index, len(all_items), item["name"], exc))
            continue
        if not chart_price:
            continue
        dev = (price - chart_price) / chart_price * 100
        if abs(dev) >= THRESHOLD:
            bad.append({
                "id": item["id"], "name": item["name"], "grade": item.get("grade"),
                "list": price, "chart": chart_price, "dev": round(dev, 1),
            })
            print("[%3d/%3d] 异常 %-16s 榜单=%9.0f 曲线=%9.0f (%+.0f%%)"
                  % (index, len(all_items), item["name"], price, chart_price, dev))
        time.sleep(0.55)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(bad, fh, ensure_ascii=False, indent=1)
    print("完成：%d 条异常，已写入 %s" % (len(bad), OUT))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    main()
