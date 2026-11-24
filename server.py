#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三角洲行动 · 变卖物行情看板 —— 本地小服务器

作用（大白话）：
  1. 帮你把网页文件发出去（浏览器才能打开）；
  2. 替浏览器去 DerGame 拉最新的交易行价格（浏览器直接拉会被跨域拦截，所以让 Python 帮忙）；
  3. 把拉到的数据存一份到 data/snapshot.json，网络抽风时还能显示上一次的数据。

只用 Python 自带库，不需要 pip install 任何东西。
"""

import json
import os
import socket
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlrequest

# ---------------- 基本配置 ----------------

ROOT = os.path.dirname(os.path.abspath(__file__))
# 网页文件放在 docs/：这样同一个文件夹既能本地跑，也能直接交给 GitHub Pages 发布
WEB_DIR = os.path.join(ROOT, "docs")
DATA_DIR = os.path.join(ROOT, "data")
SNAPSHOT_FILE = os.path.join(DATA_DIR, "snapshot.json")

API_URL = "https://dergame.cn/api/Items/search"
API_PAGE = "https://dergame.cn/?type=armory"

# 想改成 8848 以外的端口，改这里，或者启动前设置环境变量 DF_PORT
DEFAULT_PORT = int(os.environ.get("DF_PORT", "8848"))

# 同一份数据在服务器里缓存多少秒（避免频繁打扰数据站）
CACHE_TTL = 180

# 品质：接口里 3=蓝色 4=紫色 5=金色 6=红色
GRADE_CN = {"blue": "蓝色", "purple": "紫色", "gold": "金色", "red": "红色"}

# 首屏一定要有：蓝色榜 + 紫色最低价；金/红等你点页签时再取，别一上来就发 4 个请求
CORE_GRADES = ("blue", "purple")

# 拉数据时的伪装（正常的浏览器标识，做个有礼貌的访客）
HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Accept": "application/json",
    "Origin": "https://dergame.cn",
    "Referer": "https://dergame.cn/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0 Safari/537.36 DeltaPriceBoard/1.0"
    ),
}


# ---------------- 工具函数 ----------------

def to_int(value, fallback=0):
    """把接口里可能出现的字符串数字、None 统一变成整数。"""
    try:
        if value is None or value == "":
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def normalize_item(raw, grade_key):
    """把接口返回的一条物品，整理成前端好用的样子。"""
    value = raw.get("value") or {}
    price = to_int(value.get("new"))
    if price <= 0:
        return None  # 没有报价的物品直接跳过

    low7 = to_int(value.get("7down"), price)
    high7 = to_int(value.get("7top"), price)
    if low7 <= 0:
        low7 = price
    if high7 < price:
        high7 = price
    if high7 <= low7:
        high7 = low7  # 7 天没波动的情况

    length = to_int(raw.get("length"), 0)
    width = to_int(raw.get("width"), 0)
    cells = length * width if length > 0 and width > 0 else 0

    # 当前价格在 7 日区间中的位置（0% = 最低点，100% = 最高点）
    if high7 > low7:
        position = round((price - low7) / (high7 - low7) * 100)
    else:
        position = 50
    position = max(0, min(100, position))

    return {
        "id": str(raw.get("id") or ""),
        "name": (raw.get("name") or "").strip(),
        "grade": grade_key,
        "gradeCode": to_int(raw.get("grade")),
        "price": price,
        "low7": low7,
        "high7": high7,
        "cells": cells,
        "pic": raw.get("pic") or "",
        "position": position,
        "vsLow": round((price - low7) / low7 * 100, 1) if low7 > 0 else 0.0,
    }


def fetch_grade(grade_cn):
    """向 DerGame 请求某一品质的全部收集品（变卖物）。"""
    payload = json.dumps(
        {"type": ["收集品"], "grade": [grade_cn]}, ensure_ascii=False
    ).encode("utf-8")
    req = urlrequest.Request(API_URL, data=payload, headers=HEADERS, method="POST")
    with urlrequest.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if data.get("code") != 0:
        raise RuntimeError(data.get("msg") or "接口返回异常")
    return data.get("data") or [], data.get("updateTime") or ""


def fetch_grade_with_retry(grade_cn, attempts=3):
    """网络偶尔会抖，失败了就等一会儿再试。"""
    last_error = None
    for i in range(attempts):
        try:
            return fetch_grade(grade_cn)
        except Exception as exc:  # noqa: BLE001 —— 什么错都接住，换个时间再试
            last_error = exc
            time.sleep(0.8 * (i + 1))
    raise RuntimeError(str(last_error) if last_error else "未知错误")


# ---------------- 个别物品的价格纠正 ----------------
# 数据站的「榜单」接口偶尔会张冠李戴：价格和它自己的「小时曲线」对不上。
# 这里列出确认有问题的物品 id，改用小时曲线的最后一个点来算价格。
# 目前只有「植物样本」有问题（榜单长期报 ~9.2 万，实际 ~1.8 万）。

CHART_URL = "https://dergame.cn/api/Items/chartData"
CHART_FIX_IDS = {
    "15080050119": "植物样本",
}


def fetch_chart_prices(item_id, attempts=4):
    """取某个物品近 7 天的小时均价序列（每行一个整点）。"""
    payload = json.dumps({"itemId": item_id, "chartType": 7}).encode("utf-8")
    last_error = None
    for i in range(attempts):
        try:
            req = urlrequest.Request(CHART_URL, data=payload, headers=HEADERS, method="POST")
            with urlrequest.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            prices = []
            for point in data.get("values") or []:
                try:
                    prices.append(float(point["avg_price"]))
                except (KeyError, TypeError, ValueError):
                    continue
            return prices
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1.2 * (i + 1))
    raise RuntimeError(str(last_error) if last_error else "未知错误")


def apply_price_corrections(items):
    """对被数据站标错的物品，用小时曲线覆盖价格和 7 日区间。"""
    kept = []
    for item in items:
        if item["id"] not in CHART_FIX_IDS:
            kept.append(item)
            continue
        try:
            prices = fetch_chart_prices(item["id"])
            if len(prices) < 5:
                raise RuntimeError("曲线数据太少")
            price = int(prices[-1])
            low7, high7 = int(min(prices)), int(max(prices))
            if price <= 0 or low7 <= 0:
                raise RuntimeError("曲线价格异常")
            item["price"] = price
            item["low7"] = low7
            item["high7"] = max(high7, price)
            item["position"] = (
                max(0, min(100, round((price - low7) / (high7 - low7) * 100)))
                if high7 > low7 else 50
            )
            item["vsLow"] = round((price - low7) / low7 * 100, 1)
            item["corrected"] = True
            kept.append(item)
            print("[fix] %s 价格已按小时曲线纠正为 %d" % (item["name"], price))
        except Exception as exc:  # noqa: BLE001
            # 纠正不了就别显示错误价格，宁可不显示
            print("[warn] 纠正 %s 失败，本次先不显示这件：%s" % (item["name"], exc))
    items[:] = kept


# ---------------- 每个品质单独缓存 ----------------

_cache = {}          # key -> {"items": [...], "updateTime": "...", "ts": 时间戳}
_cache_lock = threading.Lock()
_snapshot_lock = threading.Lock()


def read_snapshot():
    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("grades") or {}
    except (OSError, ValueError):
        return {}


def write_snapshot():
    """把内存里所有品质的数据存一份到硬盘，断网重启也有东西看。"""
    with _snapshot_lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        with _cache_lock:
            grades = {
                key: {"items": entry["items"], "updateTime": entry["updateTime"]}
                for key, entry in _cache.items()
            }
        payload = {
            "savedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "grades": grades,
        }
        tmp = SNAPSHOT_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
            os.replace(tmp, SNAPSHOT_FILE)
        except OSError as exc:
            print("[warn] 快照保存失败：%s" % exc)


def get_grade(key, force=False):
    """
    取某个品质的全部物品。
    返回 (items, updateTime, stale)：stale=True 表示是缓存/快照里的旧数据。
    """
    if key not in GRADE_CN:
        raise KeyError(key)

    now = time.time()
    with _cache_lock:
        entry = _cache.get(key)

    if entry and not force and now - entry["ts"] < CACHE_TTL:
        return entry["items"], entry["updateTime"], False

    try:
        rows, update_time = fetch_grade_with_retry(GRADE_CN[key])
        items = []
        for row in rows:
            item = normalize_item(row, key)
            if item:
                items.append(item)
        apply_price_corrections(items)
        items.sort(key=lambda x: -x["price"])  # 统一从大到小
        entry = {"items": items, "updateTime": update_time, "ts": time.time()}
        with _cache_lock:
            _cache[key] = entry
        write_snapshot()
        return items, update_time, False
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        print("[warn] %s 品质数据获取失败：%s" % (GRADE_CN[key], message))
        if entry:  # 内存里有旧数据，先用着
            return entry["items"], entry["updateTime"], True
        snap = read_snapshot().get(key)
        if snap and snap.get("items"):
            return snap["items"], snap.get("updateTime") or "", True
        raise RuntimeError(message)


# ---------------- 接口数据组装 ----------------

def build_overview(force=False):
    """首屏用：蓝色榜 + 紫色最低价，两个品质一起拉。"""
    results, errors = {}, []
    lock = threading.Lock()

    def worker(key):
        try:
            items, update_time, stale = get_grade(key, force=force)
            with lock:
                results[key] = {"items": items, "updateTime": update_time, "stale": stale}
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append("%s：%s" % (GRADE_CN[key], exc))

    threads = [threading.Thread(target=worker, args=(k,), daemon=True) for k in CORE_GRADES]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=50)

    if errors or len(results) != len(CORE_GRADES):
        raise RuntimeError("；".join(errors) or "数据没有拉全")

    blue = results["blue"]
    purple = results["purple"]
    updated_at = blue["updateTime"] or purple["updateTime"]

    return {
        "ok": True,
        "source": "DerGame 小Der数据报",
        "sourceUrl": API_PAGE,
        "updatedAt": updated_at,
        "fetchedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stale": bool(blue["stale"] or purple["stale"]),
        "blue": blue["items"],
        "purple": purple["items"],
        "counts": {"blue": len(blue["items"]), "purple": len(purple["items"])},
    }


def build_grade(key, force=False):
    items, update_time, stale = get_grade(key, force=force)
    return {
        "ok": True,
        "grade": key,
        "updatedAt": update_time,
        "stale": stale,
        "items": items,
    }


# ---------------- 网页服务器 ----------------

class Handler(SimpleHTTPRequestHandler):
    server_version = "DeltaPriceBoard/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        query = self.path.split("?")[1] if "?" in self.path else ""
        force = "force=1" in query

        if path == "/api/prices" or path == "/api/prices/refresh":
            self.handle_overview(force or path.endswith("refresh"))
            return
        if path.startswith("/api/grade/"):
            self.handle_grade(path.rsplit("/", 1)[-1], force)
            return
        if path == "/api/health":
            self.send_json({"ok": True, "time": datetime.now().isoformat()})
            return
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def handle_overview(self, force):
        try:
            self.send_json(build_overview(force=force))
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc),
                            "note": "实时接口暂时连不上，请检查网络后点刷新重试"})

    def handle_grade(self, key, force):
        if key not in GRADE_CN:
            self.send_json({"ok": False, "error": "未知品质：%s" % key})
            return
        try:
            self.send_json(build_grade(key, force=force))
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "grade": key, "error": str(exc)})

    def send_json(self, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # 只关心接口请求，静态文件不刷屏
        if "/api/" in (self.path or ""):
            sys.stderr.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), fmt % args))


def pick_port(start):
    """端口被别的程序占了就顺延找下一个。"""
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("8848 附近 20 个端口都被占用了")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    port = pick_port(DEFAULT_PORT)
    url = "http://127.0.0.1:%d" % port
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True

    print("=" * 52)
    print("  三角洲行动 · 变卖物行情看板")
    print("  网址：%s" % url)
    print("  关掉这个黑窗口 = 停止服务")
    print("=" * 52)

    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
