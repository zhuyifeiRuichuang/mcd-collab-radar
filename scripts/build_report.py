#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦联名 / 周边情报中枢 — 单文件 HTML 情报卡生成器。

读取 collab_radar.py 产出的 radar JSON，渲染自包含单文件 HTML：
活动时间轴 + 跨界联名卡片墙 + 自有限定清单 + 到店锚点 + 合规声明。

用法：
    python build_report.py --input radar.json --out report.html
    python build_report.py --demo        # 用 examples/radar_live.json → examples/demo_report.html

约束（与官方参赛要求一致）：
- 单文件、无外部 CSS/JS 依赖；图片走麦当劳官方 CDN（加载失败自动降级为文字卡）。
- 不用 % 格式化模板（模板含 width:100% 等字面 %，会被误食），一律 replace。
- 明示「非官方产品 / 以官方实时为准 / 不引导二级炒作」。
"""

import argparse
import datetime as dt
import json
import os
import sys

STATUS_LABEL = {
    "进行中": ("#c0392b", "进行中"),      # 涨/活跃 → 红（A 股惯例，活跃=热）
    "即将开始": ("#b7791f", "即将开始"),   # 提醒关注 → 琥珀
    "已结束": ("#718096", "已结束"),      # 过往 → 灰
    "往期": ("#718096", "往期"),
    "未知": ("#718096", "未知"),
}
SCARCITY_LABEL = {
    "高稀缺": ("#c0392b", "高稀缺"),
    "中稀缺": ("#b7791f", "中稀缺"),
    "常规": ("#2f855a", "常规"),
    "已下架": ("#718096", "已下架"),
    "已结束": ("#718096", "已结束"),
    "—": ("#718096", "—"),
}
DEMO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


def esc(text):
    return (str(text or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def badge(text, mapping):
    color, label = mapping.get(text, ("#718096", str(text or "未知")))
    return ('<span class="badge" style="background:%s">%s</span>' % (color, esc(label)))


def days_text(item):
    status, remain = item.get("status"), item.get("remainDays")
    if status == "已结束":
        return "窗口已过"
    if remain is None:
        return ""
    if status == "即将开始":
        return "距开售 %d 天" % remain
    return "剩 %d 天" % remain


def access_text(item):
    mode = item.get("accessMode")
    pts, prc = item.get("points"), item.get("price")
    parts = []
    if mode == "积分兑换" or mode == "积分+现金":
        try:
            if float(pts or 0) > 0:
                parts.append("%g 积分" % float(pts))
        except (TypeError, ValueError):
            pass
    if mode == "现金购买" or mode == "积分+现金":
        try:
            if float(prc or 0) > 0:
                parts.append("¥%s" % prc)
        except (TypeError, ValueError):
            pass
    if not parts:
        return "以官方页面为准"
    return " + ".join(parts)


def render_event_timeline(events):
    blocks = []
    for e in events:
        dates = "、".join(e.get("dates") or [])
        ip_chip = ('<span class="ip-chip">%s</span>' % esc(e["ip"])) if e.get("ip") else ""
        price = ""
        try:
            if float(e.get("price") or 0) > 0:
                price = '<span class="price">¥%s%s</span>' % (esc(e.get("price")),
                                                              esc(e.get("priceSuffix") or ""))
        except (TypeError, ValueError):
            pass
        content = esc((e.get("content") or "").replace("\n", " "))[:220]
        blocks.append("""
      <div class="tl-item">
        <div class="tl-date">__DATES__</div>
        <div class="tl-body">
          <div class="tl-title">__TITLE____IP__ __PRICE__</div>
          <div class="tl-meta">__BADGES__</div>
          <div class="tl-content">__CONTENT__</div>
        </div>
      </div>""".replace("__DATES__", esc(dates))
            .replace("__TITLE__", esc(e.get("title")))
            .replace("__IP__", ip_chip)
            .replace("__PRICE__", price)
            .replace("__BADGES__", badge(e.get("status"), STATUS_LABEL) + badge(e.get("scarcity"), SCARCITY_LABEL))
            .replace("__CONTENT__", content))
    return "\n".join(blocks)


def render_product_cards(products):
    cards = []
    for p in products:
        img = p.get("image")
        img_html = ('<img class="card-img" src="%s" alt="%s" loading="lazy" '
                    'onerror="this.style.display=\'none\'">' % (esc(img), esc(p.get("name")))) if img else ""
        ip_chip = ('<span class="ip-chip">%s</span>' % esc(p["ip"])) if p.get("ip") else ""
        zombie_note = ('<div class="zombie-note">详情接口复核：该商品已下架'
                       '（列表仍展示，官方 status 字段不可信）</div>') if p.get("detailZombie") else ""
        sku_html = ""
        for sku in (p.get("skuList") or [])[:1]:
            bits = []
            try:
                if float(sku.get("points") or 0) > 0:
                    bits.append("%g 积分" % float(sku.get("points")))
            except (TypeError, ValueError):
                pass
            try:
                if float(sku.get("price") or 0) > 0:
                    bits.append("¥%s" % sku.get("price"))
            except (TypeError, ValueError):
                pass
            if bits:
                sku_html = '<div class="sku-note">SKU %s：%s</div>' % (esc(sku.get("skuId")),
                                                                       esc(" + ".join(bits)))
        selling = esc((p.get("selling") or "")[:120])
        window = "%s ~ %s" % ((p.get("window") or {}).get("upTime", "")[:10] or "?",
                              (p.get("window") or {}).get("downTime", "")[:10] or "?")
        cards.append("""
      <div class="card__CARD_CLASS__">
        __IMG__
        <div class="card-body">
          <div class="card-title">__NAME____IP__</div>
          <div class="card-meta">__STATUS____SCARCITY____ACCESS__</div>
          <div class="card-window">档期 __WINDOW__ ｜ __DAYS__</div>
          <div class="card-selling">__SELLING__</div>
          __SKU____ZOMBIE__
        </div>
      </div>""".replace("__CARD_CLASS__", " card-zombie" if p.get("detailZombie") else "")
            .replace("__IMG__", img_html)
            .replace("__NAME__", esc(p.get("name")))
            .replace("__IP__", ip_chip)
            .replace("__STATUS__", badge(p.get("status"), STATUS_LABEL))
            .replace("__SCARCITY__", badge(p.get("scarcity"), SCARCITY_LABEL))
            .replace("__ACCESS__", '<span class="access">%s</span>' % esc(access_text(p)))
            .replace("__WINDOW__", esc(window))
            .replace("__DAYS__", esc(days_text(p)))
            .replace("__SELLING__", selling)
            .replace("__SKU__", sku_html)
            .replace("__ZOMBIE__", zombie_note))
    return "\n".join(cards)


def render_own_list(products):
    rows = []
    for p in products:
        rows.append("""
        <tr>
          <td>__NAME__</td>
          <td>__IP__</td>
          <td>__STATUS____DAYS__</td>
          <td>__ACCESS__</td>
        </tr>""".replace("__NAME__", esc(p.get("name")))
            .replace("__IP__", esc(p.get("ip") or "—"))
            .replace("__STATUS__", badge(p.get("status"), STATUS_LABEL))
            .replace("__DAYS__", esc(days_text(p)))
            .replace("__ACCESS__", esc(access_text(p))))
    return "\n".join(rows)


def render_store_anchors(stores):
    rows = []
    for s in stores:
        rows.append("""
        <tr>
          <td>__NAME__</td>
          <td>__ADDR__</td>
          <td>__HOURS__</td>
          <td>__DIST__</td>
        </tr>""".replace("__NAME__", esc(s.get("storeName")))
            .replace("__ADDR__", esc(s.get("address")))
            .replace("__HOURS__", esc(s.get("businessHours")))
            .replace("__DIST__", esc("%sm" % s.get("distance") if s.get("distance") is not None else "—")))
    return "\n".join(rows)


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>麦麦联名 / 周边情报中枢</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f5f6f8; color: #1a202c; line-height: 1.6; padding: 24px; }
  .wrap { max-width: 1080px; margin: 0 auto; }
  header { background: linear-gradient(135deg, #ffc72c 0%, #ffb000 100%);
            border-radius: 14px; padding: 28px 32px; margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,.08); }
  header h1 { font-size: 26px; color: #292929; }
  header .sub { color: #5a4a00; font-size: 13px; margin-top: 6px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
           gap: 12px; margin-bottom: 22px; }
  .stat { background: #fff; border-radius: 12px; padding: 16px 18px;
          box-shadow: 0 1px 4px rgba(0,0,0,.06); }
  .stat .num { font-size: 26px; font-weight: 700; color: #c0392b; }
  .stat .lbl { font-size: 12px; color: #718096; margin-top: 2px; }
  section { background: #fff; border-radius: 14px; padding: 22px 26px;
            margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
  section h2 { font-size: 18px; margin-bottom: 14px; padding-left: 10px;
               border-left: 4px solid #ffc72c; }
  .tl-item { display: flex; gap: 14px; padding: 12px 0; border-bottom: 1px dashed #e2e8f0; }
  .tl-item:last-child { border-bottom: none; }
  .tl-date { flex: 0 0 118px; font-size: 12px; color: #4a5568; font-weight: 600;
             padding-top: 2px; }
  .tl-title { font-size: 15px; font-weight: 600; }
  .tl-meta { margin: 4px 0; }
  .tl-content { font-size: 12px; color: #718096; }
  .badge { display: inline-block; color: #fff; font-size: 11px; border-radius: 4px;
           padding: 1px 8px; margin-right: 6px; vertical-align: middle; }
  .ip-chip { display: inline-block; background: #ebf4ff; color: #2b6cb0; font-size: 11px;
             border-radius: 4px; padding: 1px 8px; margin-left: 6px; }
  .price { color: #c0392b; font-weight: 700; font-size: 13px; margin-left: 6px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
           gap: 14px; }
  .card { border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden;
          background: #fff; display: flex; flex-direction: column; }
  .card-zombie { opacity: .72; border-style: dashed; }
  .card-img { width: 100%; height: 140px; object-fit: cover; background: #f7fafc; }
  .card-body { padding: 12px 14px; }
  .card-title { font-size: 14px; font-weight: 600; min-height: 42px; }
  .card-meta { margin: 6px 0; }
  .card-window { font-size: 12px; color: #4a5568; }
  .card-selling { font-size: 12px; color: #718096; margin-top: 6px;
                  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
                  overflow: hidden; }
  .access { font-size: 12px; color: #2f855a; font-weight: 600; }
  .sku-note { font-size: 11px; color: #4a5568; margin-top: 6px;
              background: #f7fafc; border-radius: 4px; padding: 2px 8px;
              display: inline-block; }
  .zombie-note { font-size: 11px; color: #c0392b; margin-top: 6px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; background: #f7fafc; padding: 8px 10px; color: #4a5568;
       font-weight: 600; }
  td { padding: 8px 10px; border-bottom: 1px solid #edf2f7; vertical-align: top; }
  footer { font-size: 12px; color: #718096; background: #fff; border-radius: 12px;
           padding: 16px 20px; }
  footer p { margin-bottom: 4px; }
  @media (max-width: 640px) { .tl-date { flex-basis: 86px; } body { padding: 12px; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🍔 麦麦联名 / 周边情报中枢</h1>
    <div class="sub">mcd-collab-radar ｜ 数据时间：__SERVER_TIME__（时钟源：__CLOCK_SOURCE__）｜ 生成时间：__GEN_AT__</div>
  </header>

  <div class="stats">
    <div class="stat"><div class="num">__N_COLLAB_EVENTS__</div><div class="lbl">联名 / 限定活动（进行中 __N_ACTIVE_EVENTS__ ｜ 即将开始 __N_UPCOMING_EVENTS__）</div></div>
    <div class="stat"><div class="num">__N_COLLAB_PRODUCTS__</div><div class="lbl">跨界联名在售商品</div></div>
    <div class="stat"><div class="num">__N_HIGH_SCARCITY_EVENTS__</div><div class="lbl">高稀缺活动（限量 / 即将开售）</div></div>
    <div class="stat"><div class="num">__N_ZOMBIE__</div><div class="lbl">已下架商品（详情接口复核确认）</div></div>
    <div class="stat"><div class="num">__N_STORES__</div><div class="lbl">到店锚点门店（去重）</div></div>
  </div>

  <section>
    <h2>联名 / 限定活动时间轴</h2>
__TIMELINE__
  </section>

  <section>
    <h2>跨界联名商品（积分 / 现金）</h2>
    <div class="cards">
__COLLAB_CARDS__
    </div>
  </section>

  <section>
    <h2>麦当劳自有 IP / 季节限定主题</h2>
    <table>
      <thead><tr><th>名称</th><th>IP</th><th>档期</th><th>获取方式</th></tr></thead>
      <tbody>
__OWN_ROWS__
      </tbody>
    </table>
  </section>

  <section>
    <h2>到店锚点（联名商品 / 派对可预约门店参考）</h2>
    <table>
      <thead><tr><th>门店</th><th>地址</th><th>营业时间</th><th>距离</th></tr></thead>
      <tbody>
__STORE_ROWS__
      </tbody>
    </table>
    <p style="font-size:12px;color:#718096;margin-top:8px">注：官方门店接口单次最多返回 5 家、无分页，此处按「到店 / 得来速」双场景扇出去重； longitude/latitude 官方恒返回 0.0，不提供地图渲染。</p>
  </section>

  <footer>
    <p><b>合规声明</b></p>
    <p>1. 本项目为麦当劳程序员创意开发大赛参赛作品，由参赛者独立开发，<b>非麦当劳官方产品</b>；</p>
    <p>2. 数据全部来自麦当劳中国官方 MCP 接口实时返回（campaign-calendar / mall-points-products / mall-product-detail / query-nearby-stores），餐品、价格及供应状态<b>以麦当劳官方渠道实时结果为准</b>；</p>
    <p>3. 稀缺度 / 档期标签由公开规则推导，仅供参考，<b>不构成任何购买建议，不引导二级市场炒作</b>；</p>
    <p>4. 本项目不收集、不输出任何个人信息；未调用任何下单 / 支付类工具。</p>
  </footer>
</div>
</body>
</html>
"""


def build(radar):
    stats = radar.get("stats") or {}
    clock = radar.get("clock") or {}
    events = [e for e in (radar.get("collabEvents") or [])]
    products = radar.get("products") or []
    collab = [p for p in products if p.get("ipType") == "collab"]
    own = [p for p in products if p.get("ipType") == "own"]
    stores = radar.get("storeAnchors") or []

    html = TEMPLATE
    replacements = {
        "__SERVER_TIME__": esc(clock.get("serverTime") or stats.get("serverTime")),
        "__CLOCK_SOURCE__": esc(clock.get("source") or stats.get("clockSource")),
        "__GEN_AT__": esc(radar.get("generatedAt")),
        "__N_COLLAB_EVENTS__": esc(stats.get("collabEvents", len(events))),
        "__N_ACTIVE_EVENTS__": esc(stats.get("activeEvents")),
        "__N_UPCOMING_EVENTS__": esc(stats.get("upcomingEvents")),
        "__N_COLLAB_PRODUCTS__": esc(stats.get("collabProducts", len(collab))),
        "__N_HIGH_SCARCITY_EVENTS__": esc(stats.get("highScarcityEvents")),
        "__N_ZOMBIE__": esc(stats.get("zombieProducts")),
        "__N_STORES__": esc(stats.get("storeAnchors", len(stores))),
        "__TIMELINE__": render_event_timeline(events),
        "__COLLAB_CARDS__": render_product_cards(collab),
        "__OWN_ROWS__": render_own_list(own),
        "__STORE_ROWS__": render_store_anchors(stores),
    }
    for key, value in replacements.items():
        html = html.replace(key, value)
    return html


def main():
    parser = argparse.ArgumentParser(description="单文件 HTML 情报卡生成器")
    parser.add_argument("--input", default="", help="radar JSON（collab_radar.py 产出）")
    parser.add_argument("--out", default="", help="输出 HTML 路径")
    parser.add_argument("--demo", action="store_true", help="用 examples/radar_live.json 演示")
    args = parser.parse_args()

    src = args.input or (os.path.join(DEMO_DIR, "radar_live.json") if args.demo else "")
    if not src or not os.path.isfile(src):
        print("未找到输入 radar JSON：%s" % src, file=sys.stderr)
        return 2
    with open(src, encoding="utf-8") as fh:
        radar = json.load(fh)
    html = build(radar)
    out = args.out or (os.path.join(DEMO_DIR, "demo_report.html") if args.demo else "")
    if not out:
        print(html)
        return 0
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("已写入：%s（%d 字符，单文件自包含）" % (os.path.abspath(out), len(html)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
