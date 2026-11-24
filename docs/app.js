/* ============================================================
   三角洲行动 · 变卖物行情 —— 前端逻辑
   数据来自本机 server.py 的 /api/prices 和 /api/grade/<品质>
   ============================================================ */

(function () {
  "use strict";

  var REFRESH_SECONDS = 120; // 每 120 秒自动刷新一次首屏数据

  var GRADE_META = {
    blue: { cn: "蓝色", dot: "blue" },
    purple: { cn: "紫色", dot: "purple" },
    gold: { cn: "金色", dot: "gold" },
    red: { cn: "红色", dot: "red" }
  };

  var els = {
    status: document.getElementById("status"),
    statusText: document.getElementById("statusText"),
    updatedAt: document.getElementById("updatedAt"),
    refreshBtn: document.getElementById("refreshBtn"),
    banner: document.getElementById("banner"),
    bannerText: document.getElementById("bannerText"),
    bannerRetry: document.getElementById("bannerRetry"),

    kpiBlueCount: document.getElementById("kpiBlueCount"),
    kpiBlueMax: document.getElementById("kpiBlueMax"),
    kpiBlueMaxName: document.getElementById("kpiBlueMaxName"),
    kpiBlueMin: document.getElementById("kpiBlueMin"),
    kpiBlueMinName: document.getElementById("kpiBlueMinName"),
    kpiPurpleMin: document.getElementById("kpiPurpleMin"),
    kpiPurpleMinName: document.getElementById("kpiPurpleMinName"),
    todayBadge: document.getElementById("todayBadge"),

    listPanel: document.getElementById("listPanel"),
    qualityDot: document.getElementById("qualityDot"),
    listTitle: document.getElementById("listTitle"),
    listCount: document.getElementById("listCount"),
    blueList: document.getElementById("blueList"),
    blueFoot: document.getElementById("blueFoot"),
    tabs: document.getElementById("tabs"),
    searchInput: document.getElementById("searchInput"),

    cheapestThumb: document.getElementById("cheapestThumb"),
    cheapestName: document.getElementById("cheapestName"),
    cheapestPrice: document.getElementById("cheapestPrice"),
    cheapestLow: document.getElementById("cheapestLow"),
    cheapestHigh: document.getElementById("cheapestHigh"),
    cheapestVsLow: document.getElementById("cheapestVsLow"),
    cheapestRangeFill: document.getElementById("cheapestRangeFill"),
    cheapestRangeDot: document.getElementById("cheapestRangeDot"),
    purpleTop: document.getElementById("purpleTop"),
    purpleCount: document.getElementById("purpleCount"),

    nextRefresh: document.getElementById("nextRefresh"),
    refreshLine: document.getElementById("refreshLine"),
    refreshEvery: document.getElementById("refreshEvery")
  };

  var nf = new Intl.NumberFormat("zh-CN");
  var state = {
    overview: null,
    grades: {},          // 品质 -> { items, updatedAt }
    active: "blue",
    loading: false,
    loadingGrade: null,
    remain: REFRESH_SECONDS,
    query: "",
    staticMode: false    // true = 读取的是 GitHub Actions 生成的静态 JSON
  };

  // ---------------- 小工具 ----------------

  function fmt(num) {
    if (typeof num !== "number" || !isFinite(num)) return "--";
    return nf.format(Math.round(num));
  }

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function clock(date) {
    var d = date || new Date();
    return [d.getHours(), d.getMinutes(), d.getSeconds()]
      .map(function (n) { return n < 10 ? "0" + n : String(n); })
      .join(":");
  }

  function picture(url) {
    if (!url) return "";
    return '<img src="' + esc(url) + '" alt="" loading="lazy" referrerpolicy="no-referrer" ' +
      'onerror="this.classList.add(\'broken\')">';
  }

  function byPriceDesc(a, b) { return b.price - a.price; }

  function cheapestOf(items) {
    return items.reduce(function (min, item) {
      return !min || item.price < min.price ? item : min;
    }, null);
  }

  // ---------------- 取数：本地优先，静态文件兜底 ----------------
  // 本地运行时走 /api/...（Python 帮忙取数）；
  // 放在 GitHub Pages 上没有 /api/...，就自动改读 data/*.json（由 GitHub Actions 定时生成）。

  function requestJson(url) {
    return fetch(url, { cache: "no-store" }).then(function (res) {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();
    });
  }

  function fetchWithFallback(primaryUrl, staticUrl) {
    return requestJson(primaryUrl)
      .then(function (data) {
        if (!data || !data.ok) throw new Error((data && data.error) || "接口返回异常");
        return { data: data, staticMode: false };
      })
      .catch(function (primaryError) {
        return requestJson(staticUrl).then(function (data) {
          if (!data || !data.ok) throw new Error("静态数据不可用");
          return { data: data, staticMode: true };
        }).catch(function () {
          throw primaryError;
        });
      });
  }

  // ---------------- 状态与提示 ----------------

  function setStatus(kind, text) {
    els.status.dataset.state = kind;
    els.statusText.textContent = text;
  }

  function showBanner(kind, text) {
    els.banner.hidden = false;
    els.banner.dataset.kind = kind;
    els.bannerText.textContent = text;
  }

  function hideBanner() {
    els.banner.hidden = true;
  }

  // ---------------- 首屏数据：蓝 + 紫 ----------------

  function loadOverview(force) {
    if (state.loading) return;
    state.loading = true;
    els.refreshBtn.disabled = true;
    els.refreshBtn.classList.add("spinning");
    setStatus("loading", "正在拉取行情…");

    var stamp = "?t=" + Date.now();

    fetchWithFallback(
      "/api/prices" + (force ? "/refresh" : "") + stamp,
      "data/prices.json" + stamp
    )
      .then(function (result) {
        var data = result.data;
        state.staticMode = result.staticMode;
        if (!data.blue || !data.purple) {
          throw new Error("数据格式不对：缺少蓝色或紫色列表");
        }
        state.overview = data;
        state.grades.blue = { items: data.blue || [], updatedAt: data.updatedAt };
        state.grades.purple = { items: data.purple || [], updatedAt: data.updatedAt };
        renderAll();
        if (data.stale) {
          setStatus("stale", "缓存数据");
          showBanner("stale", (data.note || "实时接口暂时连不上，正在显示上一次的数据") +
            (data.error ? "（" + data.error + "）" : ""));
        } else {
          setStatus("ok", result.staticMode ? "线上数据" : "实时数据");
          hideBanner();
        }

        // 线上数据放太久没更新时，提醒一句
        if (result.staticMode) {
          var hours = dataAgeHours(data.updatedAt);
          if (hours >= 24) {
            showBanner("stale", "这份线上数据是 " + Math.round(hours) +
              " 小时前的了。在电脑上双击「更新数据.bat」就能刷新。");
          }
        }
      })
      .catch(function (err) {
        setStatus("error", "连接失败");
        showBanner("error", "拿不到数据：" + err.message + "。确认黑窗口还开着，然后点「重试」。");
        if (!state.overview) renderEmpty(err.message);
      })
      .then(function () {
        state.loading = false;
        state.remain = REFRESH_SECONDS;
        els.refreshBtn.disabled = false;
        els.refreshBtn.classList.remove("spinning");
        updateNextRefresh();
      });
  }

  // ---------------- 其他品质：点页签时再取 ----------------

  function ensureGrade(key) {
    if (state.grades[key] || state.loadingGrade === key) return;

    state.loadingGrade = key;
    renderSkeleton(key);

    fetchWithFallback(
      "/api/grade/" + key + "?t=" + Date.now(),
      "data/grade-" + key + ".json?t=" + Date.now()
    )
      .then(function (result) {
        var data = result.data;
        state.grades[key] = { items: (data.items || []).slice().sort(byPriceDesc), updatedAt: data.updatedAt };
        if (state.active === key) renderList();
      })
      .catch(function (err) {
        if (state.active === key) renderGradeError(key, err.message);
      })
      .then(function () {
        state.loadingGrade = null;
      });
  }

  // ---------------- 渲染 ----------------

  function renderAll() {
    var data = state.overview;
    if (!data) return;

    els.updatedAt.textContent = timePart(data.updatedAt);
    els.todayBadge.textContent = datePart(data.updatedAt);

    if (state.staticMode) {
      els.refreshLine.innerHTML = "线上数据 · GitHub Pages 托管";
    } else {
      els.refreshLine.innerHTML = "页面每 <b>" + REFRESH_SECONDS + "</b> 秒自动刷新";
    }

    var blue = (state.grades.blue ? state.grades.blue.items : []).slice().sort(byPriceDesc);
    var purple = (state.grades.purple ? state.grades.purple.items : []).slice().sort(byPriceDesc);
    var purpleMin = cheapestOf(purple);

    els.kpiBlueCount.textContent = blue.length;
    if (blue.length) {
      els.kpiBlueMax.textContent = fmt(blue[0].price);
      els.kpiBlueMaxName.textContent = blue[0].name;
      els.kpiBlueMin.textContent = fmt(blue[blue.length - 1].price);
      els.kpiBlueMinName.textContent = blue[blue.length - 1].name;
    }
    if (purpleMin) {
      els.kpiPurpleMin.textContent = fmt(purpleMin.price);
      els.kpiPurpleMinName.textContent = purpleMin.name;
    }

    els.purpleCount.textContent = purple.length;

    renderList();
    renderPurpleCard(purpleMin, purple);
  }

  function timePart(text) {
    if (!text) return "--:--";
    var m = String(text).match(/(\d{1,2}:\d{2}(?::\d{2})?)/);
    return m ? m[1] : String(text);
  }

  function datePart(text) {
    if (!text) return "今日";
    var m = String(text).match(/(\d{4})-(\d{2})-(\d{2})/);
    return m ? m[2] + "-" + m[3] : "今日";
  }

  function dataAgeHours(text) {
    var time = Date.parse(String(text || "").replace(" ", "T"));
    if (isNaN(time)) return 0;
    return (Date.now() - time) / 3600000;
  }

  function updateTabs() {
    Array.prototype.forEach.call(els.tabs.querySelectorAll(".tab"), function (tab) {
      var on = tab.dataset.grade === state.active;
      tab.classList.toggle("is-active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  function renderList() {
    var key = state.active;
    var meta = GRADE_META[key];

    els.listTitle.textContent = meta.cn + "品质 · 变卖物";
    els.qualityDot.className = "quality-dot " + meta.dot;
    els.listPanel.dataset.grade = key;
    updateTabs();

    var record = state.grades[key];
    if (!record) {
      renderSkeleton(key);
      ensureGrade(key);
      return;
    }

    var all = record.items.slice().sort(byPriceDesc);
    var q = state.query;
    var list = all.filter(function (item) {
      if (!q) return true;
      return (item.name || "").toLowerCase().indexOf(q) !== -1 ||
        String(item.id || "").indexOf(q) !== -1;
    });

    els.listCount.textContent = all.length + " 件";

    if (!list.length) {
      els.blueList.innerHTML =
        '<li class="empty-state"><b>' + (q ? "没有找到这个变卖物" : "暂无数据") + "</b>" +
        (q ? "换个关键词，或者清空搜索框试试" : "点右上角刷新一下") + "</li>";
    } else {
      var html = "";
      for (var i = 0; i < list.length; i++) {
        html += rowHtml(list[i], i);
      }
      els.blueList.innerHTML = html;
    }

    els.blueFoot.textContent = q
      ? "搜索结果 " + list.length + " / " + all.length + " 件"
      : "共 " + all.length + " 件，按价格从高到低 · 列表可上下滚动";
  }

  function renderSkeleton(key) {
    var meta = GRADE_META[key];
    els.listTitle.textContent = meta.cn + "品质 · 变卖物";
    els.qualityDot.className = "quality-dot " + meta.dot;
    els.listCount.textContent = "加载中…";
    els.blueList.innerHTML =
      '<li class="skeleton-row"></li><li class="skeleton-row"></li><li class="skeleton-row"></li>' +
      '<li class="skeleton-row"></li><li class="skeleton-row"></li><li class="skeleton-row"></li>';
    els.blueFoot.textContent = "正在向数据站请求" + meta.cn + "品质的报价…";
  }

  function renderGradeError(key, message) {
    var meta = GRADE_META[key];
    els.listCount.textContent = "-- 件";
    els.blueList.innerHTML =
      '<li class="empty-state"><b>' + meta.cn + "品质暂时没拿到数据</b>" +
      esc(message || "") + '<br><button class="retry-btn" type="button" data-retry="' + key + '">再试一次</button></li>';
    els.blueFoot.textContent = "网络抖了一下，点上面的按钮重试";
  }

  function rowHtml(item, index) {
    var p = Math.max(0, Math.min(100, item.position || 0));
    var delta = item.vsLow > 0 ? "+" + item.vsLow.toFixed(1) + "%" : "0%";
    var size = item.cells ? item.cells + " 格" : "收集品";
    return '' +
      '<li class="row" style="animation-delay:' + Math.min(index, 14) * 18 + 'ms">' +
        '<span class="rank">' + (index + 1) + "</span>" +
        '<span class="thumb">' + picture(item.pic) + "</span>" +
        '<span class="row-main">' +
          '<span class="row-name" title="' + esc(item.name) + '">' + esc(item.name) + "</span>" +
          '<span class="row-sub">' + size + " · 收集品</span>" +
        "</span>" +
        '<span class="row-price">' + fmt(item.price) +
          '<span class="delta">较7日低点 ' + delta + "</span>" +
        "</span>" +
        '<span class="row-range" title="近7日 ' + fmt(item.low7) + " ~ " + fmt(item.high7) + '">' +
          '<span class="range-track" style="--p:' + p + '%"><i></i><b></b></span>' +
          '<span class="range-cap"><span>' + fmt(item.low7) + "</span><span>" + fmt(item.high7) + "</span></span>" +
        "</span>" +
      "</li>";
  }

  function renderPurpleCard(best, purple) {
    if (!best) {
      els.cheapestName.textContent = "暂无数据";
      els.cheapestPrice.textContent = "--";
      els.purpleTop.innerHTML = '<li class="empty-state">没有拿到紫色品质的数据</li>';
      return;
    }

    els.cheapestName.textContent = best.name;
    els.cheapestPrice.textContent = fmt(best.price);
    els.cheapestLow.textContent = fmt(best.low7);
    els.cheapestHigh.textContent = fmt(best.high7);
    els.cheapestVsLow.textContent = (best.vsLow > 0 ? "+" : "") + best.vsLow.toFixed(1) + "%";

    var p = Math.max(0, Math.min(100, best.position || 0));
    els.cheapestThumb.innerHTML = picture(best.pic) + "<span>◆</span>";
    els.cheapestRangeFill.style.width = p + "%";
    els.cheapestRangeDot.style.left = p + "%";

    var html = "";
    purple.slice().sort(function (a, b) { return a.price - b.price; }).slice(0, 5).forEach(function (item, i) {
      html += "<li>" +
        '<span class="mini-rank">' + (i + 1) + "</span>" +
        '<span class="mini-thumb">' + picture(item.pic) + "</span>" +
        '<span class="mini-name" title="' + esc(item.name) + '">' + esc(item.name) + "</span>" +
        '<span class="mini-price">' + fmt(item.price) + "</span>" +
        "</li>";
    });
    els.purpleTop.innerHTML = html;
  }

  function renderEmpty(message) {
    els.listTitle.textContent = "变卖物排行";
    els.listCount.textContent = "-- 件";
    els.blueList.innerHTML = '<li class="empty-state"><b>加载失败</b>' + esc(message || "") + "</li>";
    els.purpleTop.innerHTML = "";
    els.cheapestName.textContent = "加载失败";
    els.cheapestPrice.textContent = "--";
  }

  // ---------------- 倒计时 ----------------

  function updateNextRefresh() {
    els.nextRefresh.textContent = "下次刷新 " + clock(new Date(Date.now() + state.remain * 1000));
  }

  function tick() {
    state.remain -= 1;
    if (state.remain <= 0) {
      loadOverview(false);
      return;
    }
    updateNextRefresh();
  }

  // ---------------- 事件 ----------------

  els.refreshBtn.addEventListener("click", function () { loadOverview(true); });
  els.bannerRetry.addEventListener("click", function () { loadOverview(true); });

  els.tabs.addEventListener("click", function (e) {
    var tab = e.target.closest(".tab");
    if (!tab) return;
    var key = tab.dataset.grade;
    if (!key || key === state.active) return;
    state.active = key;
    renderList();
  });

  els.blueList.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-retry]");
    if (!btn) return;
    var key = btn.dataset.retry;
    delete state.grades[key];
    renderList();
  });

  var searchTimer = null;
  els.searchInput.addEventListener("input", function (e) {
    var value = e.target.value.trim().toLowerCase();
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      state.query = value;
      if (state.grades[state.active]) renderList();
    }, 90);
  });

  // ---------------- 启动 ----------------

  // 支持用网址直接打开某个品质，例如 ...?grade=gold
  var fromUrl = (location.search.match(/grade=(blue|purple|gold|red)/) || [])[1];
  if (fromUrl) state.active = fromUrl;

  els.refreshEvery.textContent = REFRESH_SECONDS;
  loadOverview(false);  setInterval(tick, 1000);
})();
