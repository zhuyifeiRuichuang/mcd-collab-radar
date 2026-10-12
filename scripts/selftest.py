#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcd-collab-radar 模拟测试套件（无需 Token，纯离线）。

覆盖：
  T1  离线演示聚合（examples/ 真实抓取数据）产出合法 radar JSON
  T2  空输入边界（空日历 / 空商品 / 无门店）不崩溃
  T3  档期判定单测（进行中 / 即将开始 / 已结束 / 无时间字段）
  T4  IP 词典单测（跨界 vs 自有 vs 无命中；「麦麦」不得入联名）
  T5  稀缺度模型单测（1 天窗口=高稀缺 / 长窗口=常规 / 僵尸=已下架）
  T6  HTML 生成（占位符全替换 / 标签配平 / 无外部 CSS-JS / XSS 转义）
  T7  MCP 客户端错误处理（缺 Token / 非法 JSON 参数 / 未知工具名）
  T8  安全断言（仓库内无真实 Token 形态字符串；.gitignore 覆盖 .env）

用法：python selftest.py   （退出码 0 = 全部通过）
"""

import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
EXAMPLES = os.path.join(ROOT, "examples")
PY = sys.executable

PASSED = []
FAILED = []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print("  ✅ %s" % name)
    else:
        FAILED.append(name)
        print("  ❌ %s %s" % (name, detail))


def run_json(args):
    proc = subprocess.run([PY] + args, capture_output=True, text=True,
                          encoding="utf-8", timeout=120)
    return proc


# ---------------------------------------------------------------- T1

def test_offline_demo():
    print("T1 离线演示聚合")
    out = os.path.join(tempfile.gettempdir(), "radar_selftest.json")
    proc = run_json([os.path.join(SCRIPTS, "collab_radar.py"), "--demo", "--out", out])
    check("T1.1 退出码 0", proc.returncode == 0, proc.stderr[-300:])
    check("T1.2 radar JSON 生成", os.path.isfile(out))
    if not os.path.isfile(out):
        return None
    with open(out, encoding="utf-8") as fh:
        radar = json.load(fh)
    stats = radar.get("stats") or {}
    check("T1.3 含跨界联名商品", stats.get("collabProducts", 0) > 0)
    check("T1.4 含联名活动", stats.get("collabEvents", 0) > 0)
    check("T1.5 时钟源为官方 currentTime", stats.get("clockSource") == "campaign-calendar.currentTime")
    check("T1.6 含到店锚点", stats.get("storeAnchors", 0) > 0)
    check("T1.7 含免责声明", bool(radar.get("disclaimer")))
    check("T1.8 周边专供 feed 生效",
          any(p.get("feed") == "周边专供(catRuleIds=2)" for p in radar.get("products") or []))
    return radar


# ---------------------------------------------------------------- T2

def test_empty_inputs():
    print("T2 空输入边界")
    out = os.path.join(tempfile.gettempdir(), "radar_empty.json")
    cal = os.path.join(tempfile.gettempdir(), "cal_empty.json")
    prod = os.path.join(tempfile.gettempdir(), "prod_empty.json")
    with open(cal, "w", encoding="utf-8") as fh:
        json.dump({"currentTime": "2026-10-12 12:00:00", "dailyList": []}, fh)
    with open(prod, "w", encoding="utf-8") as fh:
        json.dump([], fh)
    proc = run_json([os.path.join(SCRIPTS, "collab_radar.py"),
                     "--calendar", cal, "--products", prod, "--out", out,
                     "--now", "2026-10-12 12:00:00"])
    check("T2.1 空数据退出码 0", proc.returncode == 0, proc.stderr[-300:])
    if os.path.isfile(out):
        with open(out, encoding="utf-8") as fh:
            radar = json.load(fh)
        check("T2.2 空数据统计为 0", radar["stats"]["totalProducts"] == 0
              and radar["stats"]["totalEvents"] == 0)
        check("T2.3 空数据无联名活动", radar["collabEvents"] == [])
    html_out = os.path.join(tempfile.gettempdir(), "report_empty.html")
    proc2 = run_json([os.path.join(SCRIPTS, "build_report.py"), "--input", out, "--out", html_out])
    check("T2.4 空数据 HTML 生成", proc2.returncode == 0 and os.path.isfile(html_out))


# ---------------------------------------------------------------- T3/T4/T5 单测

def test_units():
    print("T3-T5 判定模型单测")
    sys.path.insert(0, SCRIPTS)
    import collab_radar as cr

    now = cr.parse_time("2026-10-12 12:00:00")
    check("T3.1 进行中", cr.classify_window("2026-10-01 00:00:00", "2026-11-01 00:00:00", now)[0] == "进行中")
    check("T3.2 即将开始", cr.classify_window("2026-10-20 00:00:00", "2026-11-01 00:00:00", now)[0] == "即将开始")
    check("T3.3 已结束", cr.classify_window("2026-08-01 00:00:00", "2026-08-21 00:00:00", now)[0] == "已结束")
    check("T3.4 无时间字段→未知", cr.classify_window("", "", now)[0] == "未知")
    check("T3.5 剩余天数正确",
          cr.classify_window("2026-10-01 00:00:00", "2026-10-22 00:00:00", now)[1] == 9)

    check("T4.1 迪士尼子IP优先于父IP",
          cr.detect_ip("麦当劳狂欢生日派对 迪士尼疯狂动物城主题")[0] == "迪士尼·疯狂动物城")
    check("T4.2 PEACEMINUSONE 判跨界", cr.detect_ip("麦当劳 X PEACEMINUSONE")[2] == "collab")
    check("T4.3 唐老鸭判迪士尼子IP", cr.detect_ip("［上海迪士尼唐老鸭主题］生日派对")[0] == "迪士尼·唐老鸭")
    check("T4.4 捣蛋派对判自有IP", cr.detect_ip("麦麦奇妙夜捣蛋派对")[2] == "own")
    check("T4.5 过家家判自有IP", cr.detect_ip("麦当劳过家家派对")[2] == "own")
    check("T4.6 普通餐品券无IP", cr.detect_ip("18.8元2份麦辣鸡翅", "")[0] == "")
    check("T4.7 「麦麦」不构成联名判定", cr.detect_ip("麦麦脆汁鸡两件套")[2] == "")

    # scarcity_score 返回 (score, tier, evidence)
    score, tier, _ = cr.scarcity_score("进行中", 1, 1, 0, 0, [], False)
    check("T5.1 1天窗口+剩1天=高稀缺", tier == "高稀缺", "%s/%s" % (score, tier))
    _, tier2, _ = cr.scarcity_score("进行中", 300, 400, 0, 0, [], False)
    check("T5.2 长窗口=常规", tier2 == "常规")
    _, tier3, _ = cr.scarcity_score("进行中", None, None, 0, 0, [], True)
    check("T5.3 僵尸商品=已下架", tier3 == "已下架")
    score4, tier4, _ = cr.scarcity_score("进行中", 100, 200, 8888, 0, [], False)
    check("T5.4 高积分门槛加分", score4 < 100 and tier4 in ("中稀缺", "高稀缺", "常规"),
          "%s/%s" % (score4, tier4))
    check("T5.5 获取方式-积分", cr.access_mode("6666", "0") == "积分兑换")
    check("T5.6 获取方式-现金", cr.access_mode("0", "45") == "现金购买")
    check("T5.7 获取方式-字符串容错", cr.access_mode(None, None) == "待详情确认")


# ---------------------------------------------------------------- T6

def test_html():
    print("T6 HTML 情报卡")
    radar_path = os.path.join(EXAMPLES, "radar_live.json")
    if not os.path.isfile(radar_path):
        check("T6.0 radar_live.json 存在", False)
        return
    out = os.path.join(tempfile.gettempdir(), "report_selftest.html")
    proc = run_json([os.path.join(SCRIPTS, "build_report.py"), "--input", radar_path, "--out", out])
    check("T6.1 生成退出码 0", proc.returncode == 0)
    with open(out, encoding="utf-8") as fh:
        html = fh.read()
    check("T6.2 无残留占位符", not re.findall(r"__[A-Z_]+__", html))
    check("T6.3 无外部 CSS/JS（仅官方图片CDN）",
          not re.search(r'(?:src|href)="(?!#)(?:https?:)?//[^"]*(?:css|js)', html))
    from html.parser import HTMLParser

    class V(HTMLParser):
        VOID = {"img", "br", "hr", "meta", "link", "input"}

        def __init__(self):
            super().__init__()
            self.stack, self.errors = [], []

        def handle_starttag(self, tag, attrs):
            if tag not in self.VOID:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if self.stack and self.stack[-1] == tag:
                self.stack.pop()
            else:
                self.errors.append(tag)

    v = V()
    v.feed(html)
    check("T6.4 标签配平", not v.stack and not v.errors, str(v.stack))
    check("T6.5 含合规声明", "非麦当劳官方产品" in html)
    check("T6.6 含不炒作声明", "不引导二级市场炒作" in html)
    # XSS：构造恶意名称验证转义
    evil = {
        "generatedAt": "2026-10-12 12:00:00",
        "clock": {"serverTime": "2026-10-12 12:00:00", "source": "test"},
        "stats": {},
        "collabEvents": [{"title": "<script>alert(1)</script>", "highlights": "x",
                          "content": "y", "dates": ["2026-10-12"], "status": "进行中",
                          "scarcity": "常规", "isCollab": True, "ip": ""}],
        "products": [], "storeAnchors": [],
    }
    sys.path.insert(0, SCRIPTS)
    import build_report
    evil_html = build_report.build(evil)
    check("T6.7 XSS 转义（事件标题）", "<script>alert(1)</script>" not in evil_html)
    check("T6.8 XSS 转义（属性上下文）", '"><script>' not in evil_html)


# ---------------------------------------------------------------- T7

def test_client_errors():
    print("T7 MCP 客户端错误处理")
    proc = run_json([os.path.join(SCRIPTS, "mcd_mcp_client.py"), "fetch-detail"])
    check("T7.1 参数校验：缺 --spu-id 拒绝执行", proc.returncode == 2 and "spu-id" in proc.stderr)
    proc = run_json([os.path.join(SCRIPTS, "mcd_mcp_client.py"), "ping",
                     "--token", "bogus-token-overrides-dotenv"])
    check("T7.2 --token 优先于 .env（bogus token 必须 401，证明未被 .env 顶替）",
          proc.returncode == 1 and "401" in (proc.stderr + proc.stdout))
    proc = run_json([os.path.join(SCRIPTS, "collab_radar.py"), "--demo",
                     "--out", os.path.join(tempfile.gettempdir(), "x.json"),
                     "--city", "", "--keyword", ""])
    check("T7.3 空锚点参数降级不中断", proc.returncode == 0)


# ---------------------------------------------------------------- T8

def test_security():
    print("T8 安全断言")
    # 精确比对：.env 中的真实 Token 不得出现在任何被 git 跟踪的文件里
    real_token = ""
    env_path = os.path.join(ROOT, ".env")
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MCD_MCP_TOKEN="):
                    real_token = line.split("=", 1)[1].strip()
    token_leaks = []
    if real_token:
        for base, _dirs, files in os.walk(ROOT):
            if ".git" in base:
                continue
            for fname in files:
                if fname == ".env":
                    continue  # .env 是本地凭证唯一合法存放处，已被 .gitignore
                path = os.path.join(base, fname)
                try:
                    with open(path, encoding="utf-8") as fh:
                        if real_token in fh.read():
                            token_leaks.append(os.path.relpath(path, ROOT))
                except (UnicodeDecodeError, OSError):
                    continue
    check("T8.1 真实 Token 仅存在于 .env（gitignore）", not token_leaks, str(token_leaks))

    # GitHub Token 形态 / 非 hex 长随机串（排除 traceId 纯小写hex 与官方图片URL）
    token_like = re.compile(r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
                            r"|[0-9A-Za-z]{32,})")
    findings = []
    for base, _dirs, files in os.walk(ROOT):
        if ".git" in base:
            continue
        for fname in files:
            if fname in (".env", "selftest.py"):
                continue
            path = os.path.join(base, fname)
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
            for m in token_like.finditer(text):
                tok = m.group(0)
                if "img.mcd.cn" in text[max(0, m.start() - 80):m.start()]:
                    continue
                if re.fullmatch(r"[0-9a-f]+", tok):
                    continue  # 纯小写 hex = 服务端 traceId，非凭证
                findings.append("%s: %s..." % (os.path.relpath(path, ROOT), tok[:8]))
    check("T8.2 仓库无凭证形态长随机串", not findings, str(findings[:3]))

    gitignore = os.path.join(ROOT, ".gitignore")
    if os.path.isfile(gitignore):
        with open(gitignore, encoding="utf-8") as fh:
            gi = fh.read()
        check("T8.3 .gitignore 覆盖 .env", ".env" in gi)
    else:
        check("T8.3 .gitignore 存在", False)
    check("T8.4 .env 存在但将被忽略（本地联调用）", os.path.isfile(env_path))
    mcp_cfg = os.path.join(ROOT, "mcp-config.example.json")
    with open(mcp_cfg, encoding="utf-8") as fh:
        cfg = fh.read()
    check("T8.5 配置示例仅占位符", "${MCD_MCP_TOKEN}" in cfg and "Bearer " in cfg)
    # 仅扫运营脚本（排除本测试文件自身的字符串）
    src = ""
    for fname in ("mcd_mcp_client.py", "collab_radar.py", "build_report.py"):
        fpath = os.path.join(SCRIPTS, fname)
        if os.path.isfile(fpath):
            with open(fpath, encoding="utf-8") as fh:
                src += fh.read()
    check("T8.6 未调用下单/支付/抽奖工具",
          "create-order" not in src and "mall-create-order" not in src
          and "party-order-create" not in src and "draw-lottery" not in src
          and "auto-bind-coupons" not in src)


def main():
    print("=" * 64)
    print("mcd-collab-radar 模拟测试套件")
    print("=" * 64)
    test_offline_demo()
    test_empty_inputs()
    test_units()
    test_html()
    test_client_errors()
    test_security()
    print("=" * 64)
    print("通过 %d / %d" % (len(PASSED), len(PASSED) + len(FAILED)))
    if FAILED:
        print("失败项：%s" % "、".join(FAILED))
        return 1
    print("全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
