# MCP 接入说明 / `mcd-collab-radar`

## MCP Server

- 名称：`mcd-mcp`
- 接入地址：`https://mcp.mcd.cn`
- 协议：Streamable HTTP（JSON-RPC 2.0 over HTTP POST）
- 鉴权：`Authorization: Bearer ${MCD_MCP_TOKEN}`（Token 通过环境变量 / `.env` 注入，禁止硬编码）
- 协议版本：`2025-06-18`（initialize 协商结果）；服务端无状态，不下发 `mcp-session-id`

> WorkBuddy 配置方式：左侧边栏【专家·技能·连接器】→【连接器】→【自定义连接器】→【配置MCP】，
> 填入官方指南 JSON（见 `mcp-config.example.json`），保存后在【自定义连接器】启用 `mcd-mcp`。

## 使用的工具（5 个，均经 2026-10-12 live 实测）

| 工具 | 入参（live 实测） | 返回要点 | 在本项目的角色 |
|---|---|---|---|
| `campaign-calendar` | 无必填（可带 `specifiedDate` 锚点） | `{currentTime, dailyList[], subscribedEvents}`；标题在 `articleDto.title`（`activityTitle` 常为空串） | 联名活动源 + **官方时钟源** |
| `mall-points-products` | 可选 `catRuleIds`（如 `2`=实物商品/周边产品） | `data` 直接为数组；字段 `spuId/spuName/point/price/shopId/selling/catName/status/upTime/downTime` | 在售商品源（默认列表） |
| `mall-points-products` | `catRuleIds="2"` | 周边/实物专供 3 件（罗技/Nike/酸黄瓜） | **周边专供 feed**（防默认列表盲区） |
| `mall-product-detail` | `spuId`（必填） | `{skuList[], selling, note}`；下架返回 `code:610403` | 联名候选详情复核（僵尸检测） |
| `query-nearby-stores` | `beType`(1/5)、`searchType=2`、`city`、`keyword`（后两者必填，缺 → `600058`） | 单次恒 5 家、无分页；`longitude/latitude` 恒 0.0；`600014` = 地址无结果 | 到店锚点（双场景扇出 + 去重） |
| `now-time-info` | 无 | `{timestamp, formatted, timezone:"GMT+08:00", …}` | 备用时钟源（独立校验用） |

## 调用流程

```
initialize →（可选 tools/list 自检）
  ├─ campaign-calendar ──────────→ currentTime（官方时钟） + 联名/限定活动
  ├─ mall-points-products ───────→ 默认列表 50 件
  ├─ mall-points-products(2) ────→ 周边专供（按 spuId 合并去重）
  ├─ mall-product-detail × N ────→ 联名候选复核（610403 = 已下架；取 skuList/规则）
  └─ query-nearby-stores × 2 ────→ beType=1/5 双场景到店锚点（降级不中断）
        ↓
   collab_radar.py 聚合：档期（窗口 vs 官方时钟）× 稀缺度（透明评分）× IP（跨界/自有）
        ↓
   radar.json → build_report.py → 单文件 HTML 情报卡
```

## 业务价值

把「联名活动日历 + 商城商品 + 商品详情 + 附近门店」四个官方接口的真实数据，收敛成一个
面向周边收藏者/联名玩家的统一情报入口：**档期不错过（即将开售提醒）、僵尸不踩坑
（详情下架复核）、周边不遗漏（专供 feed 补拉）、到店有锚点（门店扇出）**。
用户不需要自己拼接口、辨字段、判真假。

## 速率与合规

- 单 Token 每分钟上限 600 次请求；脚本 `THROTTLE=0.15s`，live 全链路一次运行约 20 次请求。
- 不输出真实 Token / 个人信息；配置文件仅用环境变量占位符；`.env` 已 `.gitignore`。
- 餐品、价格、供应状态一律以官方实时结果为准。
- **不调用任何写操作工具**：`create-order` / `mall-create-order` / `party-order-create` /
  `draw-lottery` / `auto-bind-coupons` 一律不碰（`scripts/selftest.py` T8.6 有断言）。
- 服务端无状态、单头鉴权（`Authorization: Bearer`）即通；`authToken` 头非必需。
