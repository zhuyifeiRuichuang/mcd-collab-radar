#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦联名 / 周边情报中枢（mcd-collab-radar）聚合引擎。

把 campaign-calendar（联名活动）+ mall-points-products（在售周边/派对商品）
+ mall-product-detail（详情二次校验）+ query-nearby-stores（到店锚点）
聚合为一个统一情报视图：档期、稀缺度、获取方式、到店情况。

用法：
    python collab_radar.py --live                      # 真实 Token 拉取并聚合
    python collab_radar.py --live --city 上海 --keyword 人民广场
    python collab_radar.py --demo                      # 离线演示（用 examples/ 真实抓取数据）
    python collab_radar.py --input a.json b.json ...   # 离线指定输入
    python collab_radar.py --live --details 8          # 对前 N 个联名候选拉详情校验

全部判定规则均来自 2026-10-12 live 实测（见 references/live-contract.md），
禁止凭记忆改字段名与语义。
"""

import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcd_mcp_client import (  # noqa: E402
    McpError, call_tool, initialize, load_token, tools_list, unwrap,
)

DEFAULT_URL = "https://mcp.mcd.cn"
THROTTLE = 0.15  # 官方限流 600 次/分钟，扇出保持温和间隔

# ---------------------------------------------------------------- 联名 IP 词典
# 命中即判「联名/跨界」候选，命中词作为证据回显（零编造，可复核）。
# type: collab=第三方跨界联名 / own=麦当劳自有 IP 或季节限定主题。
# 注意：「麦麦」「GD」这类过宽词不入词典——麦当劳一切皆麦麦，
# 会把普通活动误判成联名（2026-10-12 live 实测教训）。
IP_DICT = {
    # 第三方跨界联名
    "PEACEMINUSONE": ("PEACEMINUSONE（G-DRAGON 主理品牌）", "collab"),
    "G-DRAGON": ("G-DRAGON", "collab"),
    "小雏菊": ("PEACEMINUSONE 小雏菊元素", "collab"),
    "龙焰": ("G-DRAGON 联动韩式风味系列", "collab"),
    "疯狂动物城": ("迪士尼·疯狂动物城", "collab"),
    "唐老鸭": ("迪士尼·唐老鸭", "collab"),
    "米妮": ("迪士尼·米妮", "collab"),
    "迪士尼": ("迪士尼", "collab"),
    "海底小纵队": ("海底小纵队", "collab"),
    "Nike": ("Nike", "collab"),
    "罗技": ("罗技", "collab"),
    # 麦当劳自有 IP / 季节限定主题（非跨界联名，单独归类）
    "万马奔腾": ("万马奔腾（生肖主题）", "own"),
    "四小福": ("四小福（麦当劳经典 IP）", "own"),
    "捣蛋": ("麦麦奇妙夜（万圣限定）", "own"),
    "过家家": ("过家家派对（职业体验）", "own"),
    "酸黄瓜": ("酸黄瓜吧唧（麦门 meme）", "own"),
}

# 联名活动关键词（campaign-calendar 侧；「麦麦」不入列，见 IP_DICT 注释）
COLLAB_EVENT_KW = ("联名", "联动", "X ", "×", "周边", "限定", "PEACEMINUSONE",
                   "小雏菊", "徽章", "丝巾", "珍藏", "同款")

# 稀缺度信号词（名称/卖点/规则文本中出现即加权）
SCARCITY_KW = ("限量", "限定", "独家", "珍藏", "即将开售", "开售", "抢先", "专属", "第二弹", "第一弹", "同款")

# 行政区划误判排除（避免「西湖区」误判为西湖景区式误命中，联名侧同样保守）
ADMIN_SUFFIX = ("区", "县", "市", "镇", "街道", "乡", "村", "新区", "开发区")

DEMO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


# ---------------------------------------------------------------- 工具函数

def parse_time(text):
    """把 '2026-10-12 11:26:21' / '2026-10-12' 解析为 datetime；失败返回 None。"""
    if not text:
        return None
    text = str(text).strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text[: len(fmt) + 4], fmt)
        except ValueError:
            continue
    return None


def detect_ip(*texts):
    """IP 词典命中：返回 (标准化 IP 名, 命中证据词, 类型)；无命中返回 ("", "", "")。"""
    joined = " ".join(t for t in texts if t)
    for kw, (label, ip_type) in IP_DICT.items():
        if kw in joined:
            return label, kw, ip_type
    return "", "", ""


def match_scarcity(*texts):
    joined = " ".join(t for t in texts if t)
    hits = [kw for kw in SCARCITY_KW if kw in joined]
    return hits


def classify_window(up_text, down_text, now):
    """按 upTime/downTime 相对服务器时间判定档期。返回 (状态, 剩余天数, 证据)。"""
    up, down = parse_time(up_text), parse_time(down_text)
    if up is None and down is None:
        return "未知", None, "无时间窗字段"
    if up and now < up:
        delta = (up - now).days
        return "即将开始", max(delta, 0), "上架 %s" % up_text
    if down and now > down:
        return "已结束", 0, "下架 %s" % down_text
    if up and down:
        remain = max((down - now).days, 0)
        span = max((down - up).days, 1)
        return "进行中", remain, "窗口 %s ~ %s（共 %d 天）" % (up_text[:10], down_text[:10], span)
    return "进行中", None, "窗口 %s ~ %s" % (up_text, down_text)


def scarcity_score(status, remain_days, span_days, points, price, kw_hits, zombie):
    """稀缺度评分（0-100）与分档。规则透明、可复核：
    - 僵尸商品（详情 610403）→ 直接「已下架」
    - 时间窗 ≤ 3 天 → 闪购级稀缺
    - 剩余 ≤ 7 天 → 高稀缺
    - 积分门槛 ≥ 5000 → 高门槛
    - 稀缺信号词命中 → 加权
    """
    if zombie:
        return 0, "已下架", "详情接口返回 610403 商品已下架"
    score = 0
    reasons = []
    if status == "已结束":
        return 0, "已结束", "销售窗口已过"
    if status == "即将开始":
        score += 25
        reasons.append("尚未开售（预约/提醒窗口）")
    if remain_days is not None:
        if remain_days <= 3:
            score += 45
            reasons.append("剩余 %d 天（闪购级）" % remain_days)
        elif remain_days <= 7:
            score += 30
            reasons.append("剩余 %d 天" % remain_days)
        elif remain_days <= 30:
            score += 10
            reasons.append("剩余 %d 天" % remain_days)
    if span_days is not None and span_days <= 7:
        score += 20
        reasons.append("总窗口仅 %d 天" % span_days)
    try:
        pts = float(points or 0)
    except (TypeError, ValueError):
        pts = 0.0
    if pts >= 5000:
        score += 20
        reasons.append("积分门槛 %g（高门槛）" % pts)
    elif pts >= 1000:
        score += 8
        reasons.append("积分门槛 %g" % pts)
    if kw_hits:
        score += min(5 * len(kw_hits), 15)
        reasons.append("信号词：%s" % "、".join(kw_hits[:3]))
    score = max(0, min(100, score))
    if score >= 60:
        tier = "高稀缺"
    elif score >= 35:
        tier = "中稀缺"
    elif score > 0:
        tier = "常规"
    else:
        tier = "常规"
    return score, tier, "；".join(reasons) if reasons else "无限量/高门槛信号"


def access_mode(points, price):
    """获取方式：积分 / 现金 / 免费未知。字段为字符串，容错转换。"""
    try:
        pts = float(points or 0)
    except (TypeError, ValueError):
        pts = 0.0
    try:
        prc = float(price or 0)
    except (TypeError, ValueError):
        prc = 0.0
    if pts > 0 and prc > 0:
        return "积分+现金"
    if pts > 0:
        return "积分兑换"
    if prc > 0:
        return "现金购买"
    return "待详情确认"


# ---------------------------------------------------------------- 数据装载

def load_calendar(path=None, data=None):
    if data is not None:
        return data
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload.get("calendar") if "calendar" in payload else payload


def load_products(path=None, data=None):
    if data is not None:
        return data
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload.get("products") if "products" in payload else payload


# ---------------------------------------------------------------- 聚合逻辑

def aggregate_products(products, now, detail_map=None, merch_ids=None):
    """在售周边/派对商品 → 情报条目列表。merch_ids = 周边专供 feed 的 spuId 集合。"""
    detail_map = detail_map or {}
    merch_ids = merch_ids or set()
    items = []
    for p in products:
        spu_id = p.get("spuId")
        ip, ip_ev, ip_type = detect_ip(p.get("spuName"), p.get("selling"), p.get("catName"))
        status, remain, win_ev = classify_window(p.get("upTime"), p.get("downTime"), now)
        kw_hits = match_scarcity(p.get("spuName"), p.get("selling"))
        mode = access_mode(p.get("point"), p.get("price"))
        detail = detail_map.get(str(spu_id)) or {}
        zombie = bool(detail.get("zombie"))
        span_days = None
        up, down = parse_time(p.get("upTime")), parse_time(p.get("downTime"))
        if up and down:
            span_days = max((down - up).days, 0)
        score, tier, scarcity_ev = scarcity_score(status, remain, span_days,
                                                  p.get("point"), p.get("price"),
                                                  kw_hits, zombie)
        feed = "周边专供(catRuleIds=2)" if spu_id in merch_ids else "默认列表"
        items.append({
            "spuId": spu_id,
            "name": p.get("spuName"),
            "image": p.get("spuImage"),
            "category": p.get("catName"),
            "shopId": p.get("shopId"),
            "selling": p.get("selling"),
            "feed": feed,
            "accessMode": mode,
            "points": p.get("point"),
            "price": p.get("price"),
            "status": status,
            "remainDays": remain,
            "window": {"upTime": p.get("upTime"), "downTime": p.get("downTime"),
                       "spanDays": span_days},
            "ip": ip,
            "ipType": ip_type,
            "ipEvidence": ip_ev,
            "scarcity": tier,
            "scarcityScore": score,
            "scarcityEvidence": scarcity_ev,
            "detailChecked": bool(detail),
            "detailZombie": zombie,
            "skuList": detail.get("skuList") or [],
        })
    # 排序：跨界联名优先，其次自有 IP/常规；档期优先，稀缺分降序
    order = {"进行中": 0, "即将开始": 1, "已结束": 2, "未知": 3}
    items.sort(key=lambda x: (0 if x["ipType"] == "collab" else 1,
                              order.get(x["status"], 3), -x["scarcityScore"]))
    return items


def event_scarcity(entry):
    """活动级稀缺度：档期 × 规则信号词。周边类活动（徽章/丝巾/棒球帽）才参与。"""
    if not entry["isCollab"]:
        return "—", 0, ""
    score = 0
    reasons = []
    if entry["status"] == "即将开始":
        score += 35
        reasons.append("尚未开售（可订阅提醒）")
    elif entry["status"] == "往期":
        return "已结束", 0, "活动日期已过"
    haystack = " ".join([entry["title"], entry["highlights"], entry["content"]])
    kw_hits = match_scarcity(entry["title"], entry["highlights"], entry["content"])
    if kw_hits:
        score += min(6 * len(kw_hits), 24)
        reasons.append("信号词：%s" % "、".join(kw_hits[:3]))
    if "抢先" in haystack or "10:40" in haystack:
        score += 10
        reasons.append("积分抢先购（更早开抢）")
    if "一套" in haystack or "三枚" in haystack:
        score += 8
        reasons.append("套装组合")
    score = max(0, min(100, score))
    tier = "高稀缺" if score >= 60 else ("中稀缺" if score >= 35 else "常规")
    return tier, score, "；".join(reasons) if reasons else "无限量/早鸟信号"


def aggregate_events(calendar, now):
    """campaign-calendar → 联名活动情报条目（含全部活动，联名候选单独标记）。"""
    entries = []
    seen = {}
    for day in calendar.get("dailyList") or []:
        date = day.get("date")
        for ev in day.get("events") or []:
            article = ev.get("articleDto") or {}
            # 实测：activityTitle 常为空串，真实标题必须取 articleDto.title
            title = (article.get("title") or ev.get("activityTitle") or "").strip()
            if not title:
                continue
            stage = ev.get("activityStage")
            button = ev.get("button") or {}
            # 档期语义（2026-10-12 live 推导）：stage=2 + button.status=2 → 即将开始；
            # stage=3 + button.status=1 → 已开售；日期早于今天 → 往期。
            day_time = parse_time(date)
            is_past = bool(day_time and day_time.date() < now.date())
            if is_past:
                status = "往期"
            elif stage == 2 or button.get("status") == 2:
                status = "即将开始"
            else:
                status = "进行中"
            ip, ip_ev, ip_type = detect_ip(title, article.get("highlights"),
                                           article.get("content"))
            kw_hits = [kw for kw in COLLAB_EVENT_KW if kw in
                       " ".join([title, article.get("highlights") or "",
                                 article.get("content") or ""])]
            is_collab = bool(ip or kw_hits)
            # 同系列多日条目合并；但同标题不同 highlights = 不同「弹」
            # （如 PEACEMINUSONE 棒球帽第一弹 vs 徽章第二弹，2026-10-12 live 实测）
            key = title + "||" + (article.get("highlights") or "")
            if key in seen:
                seen[key]["dates"].append(date)
                if status == "即将开始":
                    seen[key]["status"] = "即将开始"
                    # 状态升级后重算稀缺度，避免沿用创建时的「进行中」评分
                    tier, score, ev = event_scarcity(seen[key])
                    seen[key]["scarcity"], seen[key]["scarcityScore"] = tier, score
                    seen[key]["scarcityEvidence"] = ev
                continue
            entry = {
                "title": title,
                "highlights": article.get("highlights") or "",
                "content": article.get("content") or "",
                "image": (article.get("imgList") or [None])[0],
                "price": ev.get("price"),
                "priceSuffix": ev.get("priceSuffix"),
                "status": status,
                "activityStage": stage,
                "buttonStatus": button.get("status"),
                "buttonText": button.get("text"),
                "isCollab": is_collab,
                "ip": ip,
                "ipType": ip_type,
                "ipEvidence": ip_ev,
                "eventKeywords": kw_hits,
                "dates": [date],
            }
            entry["scarcity"], entry["scarcityScore"], entry["scarcityEvidence"] = \
                event_scarcity(entry)
            seen[key] = entry
            entries.append(entry)
    order = {"进行中": 0, "即将开始": 1, "往期": 2}
    entries.sort(key=lambda x: (0 if x["isCollab"] else 1, order.get(x["status"], 3),
                                -x["scarcityScore"]))
    return entries


def aggregate_stores(stores_list):
    """多锚点门店 → 去重到店锚点（单次查询恒 5 家，靠多锚点覆盖）。"""
    merged = {}
    for bundle in stores_list:
        for s in bundle.get("stores") or []:
            code = s.get("storeCode")
            if code and code not in merged:
                merged[code] = {
                    "storeCode": code,
                    "storeName": s.get("storeName"),
                    "address": s.get("address"),
                    "distance": s.get("distance"),
                    "businessHours": "%s-%s" % (s.get("businessStartTime"), s.get("businessEndTime")),
                    "anchor": bundle.get("params", {}).get("keyword"),
                }
    anchors = sorted(merged.values(), key=lambda x: _to_float(x.get("distance")))
    return anchors


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 9e9


# ---------------------------------------------------------------- live 拉取

def live_fetch(token, url, city, keyword, detail_count, log):
    """真实调用 MCP：calendar + products + 详情校验 + stores 扇出。"""
    result = {}
    initialize(token, url)
    log("initialize OK")

    cal = unwrap(call_tool("campaign-calendar", {}, token, url))
    result["calendar"] = cal
    log("campaign-calendar OK：%d 天 / currentTime=%s" % (
        len(cal.get("dailyList") or []), cal.get("currentTime")))

    products = unwrap(call_tool("mall-points-products", {}, token, url))
    result["products"] = products if isinstance(products, list) else []
    log("mall-points-products OK：%d 件（默认列表）" % len(result["products"]))
    time.sleep(THROTTLE)

    # 周边 / 实物商品专供 feed：官方类目规则 catRuleIds=2（实物商品，含 2>8 周边产品）。
    # 2026-10-12 live 实测：默认 50 件列表不含「酸黄瓜吧唧礼盒」等周边，
    # 必须用 catRuleIds 补拉，否则周边情报存在盲区。
    merch = unwrap(call_tool("mall-points-products", {"catRuleIds": "2"}, token, url))
    result["merchProducts"] = merch if isinstance(merch, list) else []
    known = {p.get("spuId") for p in result["products"]}
    added = [p for p in result["merchProducts"] if p.get("spuId") not in known]
    result["products"].extend(added)
    log("mall-points-products catRuleIds=2 OK：%d 件（新增 %d 件不在默认列表）"
        % (len(result["merchProducts"]), len(added)))
    time.sleep(THROTTLE)

    # 详情二次校验候选：优先「已结束/短窗口」联名项（僵尸商品检测是情报中枢
    # 的差异化价值——列表 status 恒为 2 不可信，2026-10-12 live 实测 Nike Book 2
    # 即列表在列、详情返回 610403 已下架），再补进行中联名项 enriching skuList。
    cal_now = parse_time(cal.get("currentTime")) or dt.datetime.now()
    detail_map = {}
    candidates = [p for p in result["products"]
                  if detect_ip(p.get("spuName"), p.get("selling"), p.get("catName"))[0]]

    def _priority(p):
        status, _, _ = classify_window(p.get("upTime"), p.get("downTime"), cal_now)
        return {"已结束": 0, "即将开始": 1, "进行中": 2, "未知": 3}.get(status, 3)

    candidates.sort(key=_priority)
    for p in candidates[:detail_count]:
        try:
            det = unwrap(call_tool("mall-product-detail", {"spuId": p.get("spuId")}, token, url))
            if isinstance(det, dict):
                detail_map[str(p.get("spuId"))] = {
                    "skuList": det.get("skuList") or [],
                    "zombie": False,
                    "noteText": _html_to_text(det.get("note")),
                    "selling": det.get("selling"),
                }
                log("mall-product-detail OK：%s %s" % (p.get("spuId"), p.get("spuName")))
        except McpError as exc:
            code = getattr(exc, "code", None)
            detail_map[str(p.get("spuId"))] = {"zombie": code == 610403,
                                               "error": str(exc), "code": code}
            log("mall-product-detail %s → code=%s（%s）" % (p.get("spuId"), code, exc))
        time.sleep(THROTTLE)
    result["details"] = detail_map

    if city and keyword:
        stores = []
        for be_type in (1, 5):
            try:
                data = unwrap(call_tool("query-nearby-stores", {
                    "beType": be_type, "searchType": 2, "city": city, "keyword": keyword,
                }, token, url))
                stores.append({"params": {"beType": be_type, "city": city, "keyword": keyword},
                               "stores": data if isinstance(data, list) else []})
                log("query-nearby-stores OK：beType=%d %d 家" % (be_type, len(stores[-1]["stores"])))
            except McpError as exc:
                log("query-nearby-stores beType=%d 失败（降级继续）：%s" % (be_type, exc))
            time.sleep(THROTTLE)
        result["stores"] = stores
    return result


def _html_to_text(html):
    if not html:
        return ""
    import re
    text = re.sub(r"<[^>]+>", " ", str(html))
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------- 主流程

def run(args):
    log = lambda msg: print("[collab-radar] %s" % msg, file=sys.stderr)

    if args.live:
        token = load_token(args.token)
        if not token:
            print("缺少 MCP Token：使用 --token、设置环境变量 MCD_MCP_TOKEN，或写入 .env。",
                  file=sys.stderr)
            return 2
        raw = live_fetch(token, args.url, args.city, args.keyword, args.details, log)
    else:
        # 离线 / 演示模式：读取 examples/ 下真实抓取数据
        cal_path = args.calendar or os.path.join(DEMO_DIR, "real_calendar.json")
        prod_path = args.products or os.path.join(DEMO_DIR, "real_products.json")
        # 周边专供默认文件仅在商品列表也用默认时合并，避免显式指定空/自定义商品时混入
        merch_path = args.merch or (os.path.join(DEMO_DIR, "real_products_merch.json")
                                    if not args.products else "")
        store_paths = args.stores or [
            os.path.join(DEMO_DIR, "real_stores_shanghai.json"),
        ]
        raw = {"calendar": load_calendar(cal_path),
               "products": load_products(prod_path)}
        merch = load_products(merch_path) if os.path.isfile(merch_path) else []
        raw["merchProducts"] = merch if isinstance(merch, list) else []
        known = {p.get("spuId") for p in raw["products"]}
        raw["products"].extend([p for p in raw["merchProducts"] if p.get("spuId") not in known])
        detail_path = args.details_file or os.path.join(DEMO_DIR, "real_details.json")
        if os.path.isfile(detail_path):
            with open(detail_path, encoding="utf-8") as fh:
                raw["details"] = json.load(fh)
        stores = []
        for path in store_paths:
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as fh:
                    stores.append(json.load(fh))
        raw["stores"] = stores
        log("离线模式：calendar=%s products=%d（含周边专供 %d）stores=%d" % (
            os.path.basename(cal_path), len(raw["products"]), len(raw["merchProducts"]), len(stores)))

    calendar = raw.get("calendar") or {}
    # 时钟源优先级：campaign-calendar.currentTime（官方服务器时间）> now-time-info > 本地
    server_time = calendar.get("currentTime") or args.now
    now = parse_time(server_time) or dt.datetime.now()
    clock_source = "campaign-calendar.currentTime" if calendar.get("currentTime") else "本地时钟"

    products = aggregate_products(raw.get("products") or [], now, raw.get("details") or {},
                                  merch_ids={p.get("spuId") for p in raw.get("merchProducts") or []})
    events = aggregate_events(calendar, now)
    stores = aggregate_stores(raw.get("stores") or [])

    collab_products = [p for p in products if p["ipType"] == "collab"]
    own_products = [p for p in products if p["ipType"] == "own"]
    stats = {
        "clockSource": clock_source,
        "serverTime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "totalProducts": len(products),
        "collabProducts": len(collab_products),
        "ownIpProducts": len(own_products),
        "activeProducts": sum(1 for p in products if p["status"] == "进行中"),
        "upcomingProducts": sum(1 for p in products if p["status"] == "即将开始"),
        "endedProducts": sum(1 for p in products if p["status"] == "已结束"),
        "zombieProducts": sum(1 for p in products if p["detailZombie"]),
        "highScarcity": sum(1 for p in products if p["scarcity"] == "高稀缺"),
        "totalEvents": len(events),
        "collabEvents": sum(1 for e in events if e["isCollab"]),
        "activeEvents": sum(1 for e in events if e["isCollab"] and e["status"] == "进行中"),
        "upcomingEvents": sum(1 for e in events if e["isCollab"] and e["status"] == "即将开始"),
        "highScarcityEvents": sum(1 for e in events if e["isCollab"] and e["scarcity"] == "高稀缺"),
        "storeAnchors": len(stores),
    }

    radar = {
        "generatedAt": dt.datetime.now().isoformat(timespec="seconds"),
        "clock": {"source": clock_source, "serverTime": stats["serverTime"]},
        "stats": stats,
        "collabEvents": [e for e in events if e["isCollab"]],
        "allEvents": events,
        "products": products,
        "storeAnchors": stores,
        "disclaimer": "非麦当劳官方产品；数据来自麦当劳中国 MCP 实时接口；"
                      "稀缺度与估值仅供参考，不构成任何购买建议；"
                      "餐品、价格及供应状态以麦当劳官方渠道实时结果为准。",
    }

    text = json.dumps(radar, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        log("已写入 %s" % os.path.abspath(args.out))
    else:
        print(text)

    # 控制台摘要
    print("=" * 72)
    print("麦麦联名 / 周边情报中枢（数据时间：%s，来源：%s）" % (stats["serverTime"], clock_source))
    print("联名活动 %d 场（进行中 %d / 即将开始 %d / 高稀缺 %d）｜跨界联名商品 %d 件 / 自有限定 %d 件"
          "（进行中 %d / 已结束 %d / 已下架 %d）｜到店锚点 %d 个"
          % (stats["collabEvents"], stats["activeEvents"], stats["upcomingEvents"],
             stats["highScarcityEvents"], stats["collabProducts"], stats["ownIpProducts"],
             stats["activeProducts"], stats["endedProducts"],
             stats["zombieProducts"], stats["storeAnchors"]))
    print("-" * 72)
    print("【联名 / 限定活动】")
    for e in radar["collabEvents"]:
        dates = "、".join(e["dates"][:3])
        print("  [%s|%s] %s（%s）%s" % (e["status"], e["scarcity"], e["title"], dates,
                                        "｜IP：%s" % e["ip"] if e["ip"] else ""))
    print("【跨界联名商品】")
    for p in collab_products[:10]:
        remain = ("距开售 %d 天" % p["remainDays"]) if p["status"] == "即将开始" and p["remainDays"] is not None \
            else ("剩 %d 天" % p["remainDays"]) if p["remainDays"] is not None else ""
        print("  [%s|%s] %s ｜%s｜%s %s" % (p["status"], p["scarcity"], p["name"],
                                            p["accessMode"], p["ip"], remain))
    if not collab_products:
        print("  （本期无跨界联名在售商品）")
    print("=" * 72)
    return 0


def main():
    parser = argparse.ArgumentParser(description="麦麦联名 / 周边情报中枢聚合引擎")
    parser.add_argument("--live", action="store_true", help="真实 Token 拉取（默认离线演示）")
    parser.add_argument("--demo", action="store_true", help="离线演示模式（默认即离线）")
    parser.add_argument("--token", default="")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--city", default="", help="到店锚点城市（配合 --keyword）")
    parser.add_argument("--keyword", default="", help="到店锚点关键词（配合 --city）")
    parser.add_argument("--details", type=int, default=8, help="live 模式对前 N 个联名候选拉详情校验")
    parser.add_argument("--now", default="", help="离线模式指定时钟 yyyy-MM-dd HH:MM:SS")
    parser.add_argument("--calendar", default="", help="离线日历 JSON 路径")
    parser.add_argument("--products", default="", help="离线商品 JSON 路径")
    parser.add_argument("--merch", default="", help="离线周边专供（catRuleIds=2）JSON 路径")
    parser.add_argument("--stores", nargs="*", default=None, help="离线门店 JSON 路径列表")
    parser.add_argument("--details-file", default="", help="离线详情校验 JSON 路径")
    parser.add_argument("--out", default="", help="输出 radar JSON 路径（缺省打印）")
    args = parser.parse_args()
    try:
        return run(args)
    except McpError as exc:
        print("MCP 调用失败：%s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
