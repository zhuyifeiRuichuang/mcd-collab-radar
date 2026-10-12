# workbuddy.md

> 本文件为使用腾讯 WorkBuddy 开发本项目的对话上下文记录，用于核验 WorkBuddy 专项奖励条件。
> 由 WorkBuddy 会话上下文整理而成。

## 项目

- 名称：麦麦联名 / 周边情报中枢（mcd-collab-radar）
- 定位：基于麦当劳中国官方 MCP 的联名/周边统一情报 Skill（档期 × 稀缺度 × 获取方式 × 到店锚点）
- 开发环境：腾讯 WorkBuddy（Agent 模式）
- 联调日期：2026-10-12（**全部工具均用有效 Token 完成真实调用**）

---

## 一、需求起点

用户提出：分析已有项目 `mcd-collab-radar`（联名/周边情报中枢），要求——
1. 使用麦当劳 MCP 真实调测，确认功能真实可用且无故障；
2. 完整检查功能、模拟测试确认可用，排查并解决功能与安全隐患，把旧配置更新到最新适配版本；
3. 推送发布到 GitHub 新建仓库，带版本号发布正式 release，并严格按官方要求提交报名。

用户明确约束：**禁止猜测，必须是真实有效的配置，必须在麦当劳参考文档与 MCP 开发指导中真实查到**。

## 二、调研过程（WorkBuddy 完成）

1. 读取竞赛主仓库 README「开发 Skill」章节，确认参赛必需文件清单：README.md、
   CONTEST_DECLARATION.md（内容不可改）、MCP_INTEGRATION.md、源代码、workbuddy.md；
   报名 Issue 格式为「【参赛申请】+ 项目名称/项目地址/项目简介」，标题与正文间不加换行、
   地址不用 Markdown 链接。
2. 读取既有骨架（6 文件，仅文档无代码）与兄弟项目 `mcd-checkin-map` 的工程范式，对齐交付形态。
3. 用有效 Token 直连 `https://mcp.mcd.cn` 做真实探测：`initialize` → `tools/list`（35 个工具）
   → 核心工具逐个 `tools/call`，以**接口真实返回**作为唯一事实来源。

### 关键转折：真实联调推翻了骨架的多条核心假设

| # | 骨架假设 | 真实事实 |
|:---:|---|---|
| 1 | 商品 `status` 反映上下架 | `status` 恒为 `2`，不可信；Nike Book 2 / 罗技键鼠套装列表在列、详情 `610403 已下架` |
| 2 | 默认商品列表即全部在售 | 默认 50 条不含「酸黄瓜吧唧礼盒」；须用官方 `catRuleIds=2`（周边产品）专供补拉 |
| 3 | 活动标题在 `activityTitle` | `activityTitle` 常为空串，真实标题在 `articleDto.title` |
| 4 | 档期语义可直接使用 | 无文档载明；由 live 数据推导：`stage=2`+「提醒我」按钮 = 即将开始，`stage=3` = 已开售 |
| 5 | 同标题活动可合并 | 同标题不同 highlights = 不同「弹」（PEACEMINUSONE 棒球帽 vs 徽章），合并会丢档期 |
| 6 | 「麦麦」可作联名 IP 信号 | 过宽，把普通活动误判为联名；IP 词典须二分「跨界联名 / 自有 IP」 |
| 7 | 旧工具清单可用 | `query-partystore-date`（无连字符）已淘汰，实为 `query-party-store-date`；缺 `query-promotions`、`query-survey-coupon`、`now-time-info` |

## 三、实现与自查（WorkBuddy 生成代码后真实复测）

生成的文件：

1. `scripts/mcd_mcp_client.py`：MCP 客户端（优先 `structuredContent`，重试与 401/429 提示，
   `--token` > 环境变量 > `.env` 优先级）
2. `scripts/collab_radar.py`：聚合引擎（双 feed 合并 + 档期/稀缺度/IP 判定 + 门店扇出）
3. `scripts/build_report.py`：单文件 HTML 情报卡（无外部 CSS/JS、XSS 转义、图片降级）
4. `scripts/selftest.py`：48 项模拟测试与安全断言
5. `references/live-contract.md`（live 契约证据 base）、`references/mcp-tools.md`（程序化重建）
6. `examples/`：2026-10-12 真实抓取数据 + `radar_live.json` + `demo_report.html`
7. README / MCP_INTEGRATION / SKILL / CHANGELOG / LICENSE / workbuddy.md

### 自查中发现并修复的真实缺陷

- **多「弹」合并丢档期**：PEACEMINUSONE 棒球帽（10-12 已开售）与徽章（10-15 即将开售）
  标题相同被合并，且状态升级后稀缺度未重算 → 去重键改为「标题 + highlights」并重算。
- **显式空商品仍混入默认周边**：selftest T2.2 暴露 → 周边专供默认文件仅在商品列表
  也用默认路径时合并。
- **联名误判**：「麦麦」入典导致普通活动全被判联名 → 移除过宽词，IP 二分。
- **测试自身 bug**：scarcity_score 返回序 (score, tier, evidence) 在测试中被颠倒解包，
  导致 4 项假失败 → 修正后 48/48 通过。

### 验证结果

- live 全链路一次运行约 20 次请求（远低于 600/分钟限流，内置 0.15s 节流）。
- 联名活动 7 场（进行中 5 / 即将开始 2 高稀缺）；跨界联名商品 10 件、自有 IP 9 件；
  僵尸确认 2 件；到店锚点 10 个（beType 1/5 各 5 家去重）。
- HTML 情报卡：标签配平、占位符零残留、无外部 CSS/JS、XSS 转义断言通过。
- 离线演示链路（`--demo`）无需 Token 完整跑通并产出 HTML。

## 四、合规与发布

- 仓库内不含真实 Token：`.env` 已 `.gitignore`，示例仅 `${MCD_MCP_TOKEN}` 占位；
  selftest T8.1/T8.2 以「真实 Token 精确比对 + 凭证形态扫描」双重断言，提交前全仓复核。
- 未调用任何下单/支付/抽奖/领券工具（selftest T8.6 断言）。
- 发布 v1.0.0 Release，并按官方格式提交报名 Issue。
