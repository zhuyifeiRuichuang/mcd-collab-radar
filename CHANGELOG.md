# 更新日志 / Changelog

## v1.0.0 — 2026-10-12

首个正式版本。基于有效 Token 完成麦当劳 MCP 真实联调（initialize → tools/list → 全量核心工具
tools/call），并依据真实返回重写全部字段口径与判定规则。

### 新增

- `scripts/mcd_mcp_client.py`：MCP Streamable HTTP 客户端（仅标准库，零依赖）。
  支持 `ping` / `tools-list` / `call` / `fetch-stores` / `fetch-calendar` /
  `fetch-products` / `fetch-detail` / `now-time`；优先读取 `structuredContent`，
  网络与 5xx 自动重试，401/429 明确提示；Token 优先级 `--token` > 环境变量 > `.env`。
- `scripts/collab_radar.py`：聚合引擎。campaign-calendar + mall-points-products
  **双 feed**（默认列表 + `catRuleIds=2` 周边专供）+ mall-product-detail 复核
  （`610403` 僵尸检测）+ query-nearby-stores 双场景扇出；输出 radar JSON。
  判定模型：档期（窗口 vs 官方时钟）、稀缺度（0-100 透明评分）、IP（跨界/自有二分）。
- `scripts/build_report.py`：单文件 HTML 情报卡生成器（内联样式、无外部 CSS/JS、
  官方 CDN 图片加载失败自动降级、全量 HTML 转义防 XSS）。
- `scripts/selftest.py`：48 项离线模拟测试（聚合/空输入边界/判定模型单测/HTML 校验/
  客户端错误处理/安全断言）。
- `references/live-contract.md`：live 实测契约（字段、语义、陷阱，本项目禁止猜测的证据 base）。
- `examples/`：2026-10-12 真实抓取数据（日历/商品/周边专供/详情复核/门店）+
  `radar_live.json` + `demo_report.html`。

### 依据真实接口修正（清除旧骨架的落后配置）

| # | 旧配置（错误/缺失） | 真实接口事实 | 修正 |
|:---:|---|---|---|
| 1 | `references/mcp-tools.md` 手抄 33 工具、含错误工具名 | live 为 **35** 工具；真实名 `query-party-store-date/session`（含连字符） | 由 live `tools/list` **程序化重建**，补齐 `query-promotions`、`query-survey-coupon`、`now-time-info` |
| 2 | 未载明商城类目过滤 | 官方描述载明 `catRuleIds`：周边产品 = `2>8`（实物商品 = `2`） | 新增周边专供 feed |
| 3 | 默认商品列表即全部在售 | 默认 50 条**不含**「酸黄瓜吧唧礼盒」等周边 | 双 feed 按 spuId 合并去重 |
| 4 | 可信商品 `status` 字段 | `status` 恒为 `2`，不可信 | 档期一律以 `upTime/downTime` 窗口 vs `campaign-calendar.currentTime` 判定 |
| 5 | 无下架复核 | Nike Book 2 / 罗技键鼠套装列表在列，详情返回 `610403 商品已下架` | 联名候选详情二次校验，僵尸商品标注「已下架」 |
| 6 | 活动标题取 `activityTitle` | `activityTitle` 常为空串，真实标题在 `articleDto.title` | 标题/要点/正文/图片全部改取 `articleDto` |
| 7 | 档期语义未定义 | live 推导：`activityStage=2` + `button.status=2`（提醒我）= 即将开始；`stage=3` = 已开售 | 按证据实现，并在 radar 中回显 `activityStage`/`buttonStatus` |
| 8 | 同标题活动直接合并 | 同标题不同 highlights = 不同「弹」（PEACEMINUSONE 棒球帽 vs 徽章） | 去重键 = 标题 + highlights，状态升级后重算稀缺度 |
| 9 | 「麦麦」入联名 IP 词典 | 过宽词把一切误判为联名（live 教训） | 移除过宽词；IP 词典二分：跨界联名 vs 自有 IP，命中词回显 |
| 10 | 无本地时钟策略 | `now-time-info` 存在且可用 | 第一时钟源 `campaign-calendar.currentTime`，`now-time-info` 备用 |

### 验证记录（2026-10-12，有效 Token）

- `initialize` 通过（`protocolVersion 2025-06-18`，服务端无状态无 session-id）；`tools/list` 35 个。
- `campaign-calendar`：13 天 / 26 事件 / 15 唯一活动，`currentTime=2026-10-12 11:34:33`；
  实测联名：PEACEMINUSONE 两弹、G-DRAGON 联动、第三周丝巾（10-22 即将开售）。
- `mall-points-products`：默认 50 件 + 周边专供 3 件（新增 1 件不在默认列表）。
- `mall-product-detail`：14 次调用，2 次 `610403`（Nike Book 2 / 罗技）确认为僵尸，12 次正常取 skuList。
- `query-nearby-stores`：beType=1/5 各 5 家 → 去重 10 锚点；`longitude/latitude` 恒 0.0 已确认。
- `selftest.py`：48/48 通过（含 XSS 转义、空数据边界、Token 不落盘断言）。
