#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把本地改动发布到 GitHub（不用 git push）。

为什么不用 git push？
  这台电脑连不上 github.com:443，但 api.github.com 是通的，
  所以改用 GitHub 的 API 直接提交。效果和 git push 一样。

它会自动比较：只上传有变化的文件，没变化就什么都不做。
"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

REPO = "chengluo2008/delta-price-board"
BRANCH = "main"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", ".github", "__pycache__", "data", ".preview"}
SKIP_FILES = {"Thumbs.db", ".DS_Store"}

GH_CANDIDATES = (
    r"C:\Program Files\GitHub CLI\gh.exe",
    r"C:\Program Files (x86)\GitHub CLI\gh.exe",
    "gh",
)


def find_gh():
    for path in GH_CANDIDATES:
        if os.path.sep in path:
            if os.path.exists(path):
                return path
        else:
            return path  # 交给系统 PATH
    raise SystemExit("没找到 gh（GitHub CLI），请先安装或打开 DeepSeek Harness")


GH = find_gh()


def token():
    try:
        return subprocess.check_output([GH, "auth", "token"], text=True).strip()
    except Exception:
        raise SystemExit("gh 没有登录，运行 `gh auth login` 之后再试")


TOKEN = token()


def api(method, path, payload=None, attempts=5):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last = None
    for i in range(attempts):
        req = urllib.request.Request(
            "https://api.github.com" + path,
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer " + TOKEN,
                "Accept": "application/vnd.github+json",
                "User-Agent": "delta-price-board-publisher",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
        except Exception as exc:  # noqa: BLE001
            last = exc
            print("  网络抖动（%s），%d 秒后重试 %d/%d"
                  % (type(exc).__name__, 2 * (i + 1), i + 1, attempts))
            time.sleep(2 * (i + 1))
    raise last


def git_blob_sha(data):
    """Git 计算文件指纹的固定算法，用来判断"改没改"。"""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def collect_files():
    files = []
    for base, dirs, names in os.walk(ROOT):
        if base == ROOT:
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        else:
            dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in names:
            if name in SKIP_FILES:
                continue
            full = os.path.join(base, name)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            files.append((rel, full))
    return sorted(files)


def main():
    head = api("GET", "/repos/%s/git/ref/heads/%s" % (REPO, BRANCH))
    parent = head["object"]["sha"]
    commit = api("GET", "/repos/%s/git/commits/%s" % (REPO, parent))
    tree_sha = commit["tree"]["sha"]

    remote = {}
    tree = api("GET", "/repos/%s/git/trees/%s?recursive=1" % (REPO, parent))
    for entry in tree.get("tree") or []:
        if entry.get("type") == "blob":
            remote[entry["path"]] = entry["sha"]

    changed = []
    for rel, full in collect_files():
        with open(full, "rb") as fh:
            data = fh.read()
        if remote.get(rel) != git_blob_sha(data):
            changed.append((rel, data))

    if not changed:
        print("没有需要发布的改动。")
        return 0

    print("发现 %d 个改动：" % len(changed))
    entries = []
    for rel, data in changed:
        blob = api("POST", "/repos/%s/git/blobs" % REPO, {
            "content": base64.b64encode(data).decode("ascii"),
            "encoding": "base64",
        })
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print("  + %s" % rel)

    new_tree = api("POST", "/repos/%s/git/trees" % REPO, {"base_tree": tree_sha, "tree": entries})
    new_commit = api("POST", "/repos/%s/git/commits" % REPO, {
        "message": "chore: 更新变卖物数据（%s）" % time.strftime("%Y-%m-%d %H:%M"),
        "tree": new_tree["sha"],
        "parents": [parent],
    })
    api("PATCH", "/repos/%s/git/refs/heads/%s" % (REPO, BRANCH), {
        "sha": new_commit["sha"], "force": True,
    })

    print("已发布：https://github.com/%s/commit/%s" % (REPO, new_commit["sha"][:7]))
    print("1 分钟左右 GitHub Pages 会重新构建，网址不变。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
