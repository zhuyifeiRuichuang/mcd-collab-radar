---
name: mcd-collab-radar
description: 麦当劳「麦麦联名 / 周边情报中枢」Skill。基于麦当劳中国官方 MCP 真实数据，把分散的联名活动（campaign-calendar）与在售周边（mall-points-products 默认列表 + catRuleIds=2 周边专供）聚合为统一情报视图：档期状态、稀缺度评分、获取方式、到店锚点，并用 mall-product-detail 做下架复核（列表 status 恒为 2 不可信）。适用于「所有在售周边整理」「联名活动汇总」「GD/PEACEMINUSONE 联名到了第几弹」「别漏掉周边上新」等需求。
---

# 麦麦联名 / 周边情报中枢 / mcd-collab-radar

一次拉全所有联名活动与在售周边，按档期与稀缺度归档，输出可分享的单文件 HTML 情报卡。数据 100% 来自麦当劳中国官方 MCP 实时接口，零编造、零第三方数据源。

## 何时使用

- 用户说：所有在售周边整理、联名活动汇总、周边情报、别漏掉上新、帮我盯着联名
- 用户问：GD / PEACEMINUSONE 联名到第几弹了、徽章什么时候开售、哪些联名快下了
- 用户想要一个长期、统一的周边/联名追踪入口

## 前置条件

- 麦当劳中国 MCP Token：https://open.mcd.cn/mcp （控制台 → 激活）
- 配置 `mcd-mcp`（见 `mcp-config.example.json`，Token 用环境变量 `MCD_MCP_TOKEN` 占位，禁止硬编码）

## 核心原则

1. **官方为准**：数据只来自官方 MCP；档期以官方服务器时钟（`campaign-calendar.currentTime`）判定，不信商品 `status` 字段（live 实测恒为 2）。
2. **双feed防盲区**：默认商品列表 + `catRuleIds=2` 周边专供合并（live 实测默认列表会漏周边，如「酸黄瓜吧唧礼盒」）。
3. **详情复核**：联名商品过 `mall-product-detail` 二次校验，`610403 商品已下架` 即判僵尸（live 实证 Nike Book 2 / 罗技键鼠套装）。
4. **归档可查**：按档期状态（进行中 / 即将开始 / 已结束）与 IP 类型（跨界联名 / 自有 IP）分类。
5. **理性克制**：稀缺度评分透明可复核，仅供参考，不引导二级炒作。

## 标准工作流

### 第 1 步：聚合（scripts/collab_radar.py）

```
campaign-calendar            → 联名活动（标题取 articleDto.title，activityTitle 常为空）
mall-points-products         → 在售商品默认列表（50 条）
mall-points-products(2)      → 周边/实物专供 feed，按 spuId 合并去重
mall-product-detail(spuId)   → 联名候选详情复核（僵尸检测 + skuList + 规则文本）
query-nearby-stores          → 可选：到店锚点（city + keyword，到店/得来速双扇出）
```

实时模式（需 Token）：

```bash
python scripts/collab_radar.py --live --city 上海 --keyword 人民广场 --details 14 --out radar.json
```

离线演示（examples/ 内为 2026-10-12 真实抓取数据，无需 Token）：

```bash
python scripts/collab_radar.py --demo --out radar.json
```

### 第 2 步：分类与评分

- 档期：`upTime/downTime` 窗口 vs 官方时钟 → 进行中 / 即将开始 / 已结束（含剩余天数）
- IP：跨界联名（迪士尼/疯狂动物城、海底小纵队、PEACEMINUSONE、G-DRAGON、Nike、罗技）vs 自有 IP（万马奔腾、四小福、捣蛋、过家家、酸黄瓜）
- 稀缺度：0-100 透明评分（窗口长度 × 积分门槛 × 信号词），规则见 `references/live-contract.md`
- 获取方式：积分兑换 / 现金购买 / 积分+现金

### 第 3 步：生成情报卡（scripts/build_report.py）

```bash
python scripts/build_report.py --input radar.json --out report.html
```

单文件自包含 HTML：统计概览 + 联名活动时间轴 + 跨界联名卡片墙（官方图片）+
自有 IP 清单 + 到店锚点 + 合规声明。无外部 CSS/JS，图片走官方 CDN 且加载失败自动降级。

### 第 4 步：模拟测试（scripts/selftest.py）

```bash
python scripts/selftest.py   # 48 项断言：聚合/边界/判定模型/HTML/错误处理/安全
```

## 输出要求

- 必须区分「进行中 / 即将开始 / 已结束」，必须标注时钟来源。
- 稀缺度与估值明确标注「仅供参考」。
- 每次输出含：非官方产品、以官方实时为准、不引导二级炒作、不输出个人信息。

## 硬约束

- 不引导二级炒作；不输出个人信息；数据以官方为准。
- 不调用任何下单/支付/抽奖/领券工具（`create-order` / `mall-create-order` / `party-order-create` / `draw-lottery` / `auto-bind-coupons` 一律不碰）。
- 单 Token 每分钟不超过 600 次请求；脚本内置 0.15s 节流。
- Token 只进 `.env`（已 gitignore）或环境变量，禁止写入任何输出文件。

## 文件说明

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本工作流定义 |
| `scripts/mcd_mcp_client.py` | MCP Streamable HTTP 客户端（零依赖，ping/tools-list/call/fetch-*） |
| `scripts/collab_radar.py` | 聚合引擎：双feed + 档期/稀缺度/IP 分类 |
| `scripts/build_report.py` | 单文件 HTML 情报卡生成器 |
| `scripts/selftest.py` | 48 项离线模拟测试与安全断言 |
| `references/live-contract.md` | live 实测契约（字段/语义/陷阱，禁止猜测的证据 base） |
| `references/mcp-tools.md` | 35 个工具 live 清单（程序化生成） |
| `examples/` | 2026-10-12 真实抓取数据 + radar_live.json + demo_report.html |
| `MCP_INTEGRATION.md` | MCP 接入说明 |
| `CONTEST_DECLARATION.md` | 参赛声明（官方文件，内容不可改） |
| `mcp-config.example.json` | 配置示例（仅环境变量占位符） |
| `workbuddy.md` | WorkBuddy 开发上下文记录 |
