# 麦麦联名 / 周边情报中枢 / `mcd-collab-radar`

> 麦当劳程序员创意开发大赛参赛作品 · 版本 v1.0.0 · 数据源：麦当劳中国官方 MCP（live 实测）

## 一、项目介绍

「麦麦联名 / 周边情报中枢」把分散的联名活动与在售周边聚合成**一个持续可查的统一视图**：
一次拉全所有联名/限定活动（麦当劳 X PEACEMINUSONE、联动 G-DRAGON……）与在售周边
（迪士尼疯狂动物城派对、海底小纵队、Nike 联名、罗技键鼠……），按**档期状态、稀缺度、
获取方式、到店锚点**四个维度归档，输出可分享的单文件 HTML 情报卡。

与「自己翻接口」的本质差异（全部为 2026-10-12 live 实测发现）：

| # | 能力 | live 事实依据 |
|---|---|---|
| 1 | 双 feed 防盲区 | 默认商品列表不含全部周边，须以官方 `catRuleIds=2` 周边专供补拉合并 |
| 2 | 详情下架复核 | 商品 `status` 恒为 2 不可信；Nike Book 2 / 罗技键鼠套装列表在列、详情返回 `610403 已下架` |
| 3 | 官方时钟判定档期 | 时钟源取 `campaign-calendar.currentTime`，非本地时间 |
| 4 | 弹次识别 | 同系列不同「弹」（PEACEMINUSONE 棒球帽 vs 徽章）按 highlights 拆分，不混为一谈 |
| 5 | 联名 IP 结构化 | 迪士尼·唐老鸭/米妮/疯狂动物城、海底小纵队、PEACEMINUSONE、G-DRAGON 等，命中词回显可复核 |

## 二、目标用户

麦当劳周边收藏党、联名玩家（GD/PEACEMINUSONE/迪士尼）、想「别漏掉上新」的情报追踪者。

## 三、安装与配置

1. 申请麦当劳中国 MCP Token：https://open.mcd.cn/mcp （登录 → 控制台 → 激活）
2. 在 MCP Client 中配置 `mcd-mcp`（参考 `mcp-config.example.json`）：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer ${MCD_MCP_TOKEN}" }
    }
  }
}
```

3. 本地运行（零第三方依赖，Python 3.8+）：

```bash
# 实时模式（Token 经 .env 或环境变量注入，.env 已被 gitignore）
python scripts/collab_radar.py --live --city 上海 --keyword 人民广场 --details 14 --out radar.json
python scripts/build_report.py --input radar.json --out report.html

# 离线演示（examples/ 为 2026-10-12 真实抓取数据，无需 Token）
python scripts/collab_radar.py --demo
python scripts/build_report.py --demo

# 模拟测试（48 项断言）
python scripts/selftest.py
```

## 四、使用示例

**用户**：把所有在售的麦当劳周边和联名活动整理给我，GD 联名到第几弹了？

**助手**：以 2026-10-12 11:34（官方服务器时钟）为基准——

- **进行中**：麦当劳 X PEACEMINUSONE 第一弹·GD 同款复古棒球帽（10-08 10:45 已开售，任意餐品 +39.9 元）；
- **即将开始·高稀缺**：PEACEMINUSONE 第二弹·联名徽章（10-15 10:45 开售，一套三枚限量珍藏，APP 积分 10:40 抢先购）；
- **即将开始·高稀缺**：第三周周边·限定主题丝巾（10-22 开售）；
- **在售跨界联名商品**：迪士尼疯狂动物城主题派对（¥58/¥98）、海底小纵队欢乐派对（¥58/¥88）等 10 件；
- **已下架提醒**：Nike Book 2 联名款、罗技键鼠套装兑换窗口已过且详情确认下架。

完整视图见 `examples/demo_report.html`。

## 五、使用的麦当劳 MCP 工具

| 工具 | 用途 |
|---|---|
| `campaign-calendar` | 联名/限定活动（标题取 `articleDto.title`；`activityStage=2`+「提醒我」= 即将开始） |
| `mall-points-products` | 在售商品默认列表 + `catRuleIds=2` 周边专供（双 feed 合并） |
| `mall-product-detail` | 联名候选详情复核（`610403` 僵尸检测、skuList、规则文本） |
| `query-nearby-stores` | 到店锚点（`beType=1/5` 双场景扇出，单次 5 家无分页，多锚点去重） |
| `now-time-info` | 备用时钟源（第一时钟源为 `campaign-calendar.currentTime`） |

字段级契约与踩坑记录见 [`references/live-contract.md`](references/live-contract.md)，
35 个工具 live 清单见 [`references/mcp-tools.md`](references/mcp-tools.md)。

## 六、合规要点

- 二级市场估值为参考非引导炒作；稀缺度评分规则公开透明、可复核。
- 不输出个人信息；不调用任何下单/支付/抽奖/领券工具。
- 价格、供应状态一律以麦当劳官方渠道实时结果为准。
- 单 Token 每分钟 ≤600 次请求（脚本内置 0.15s 节流）。

## 七、项目结构

```
mcd-collab-radar/
├── SKILL.md                  工作流定义
├── README.md                 本文件
├── MCP_INTEGRATION.md        MCP 接入说明
├── CONTEST_DECLARATION.md    参赛声明（官方文件，内容不可改）
├── mcp-config.example.json   配置示例（仅环境变量占位符）
├── LICENSE                   MIT
├── CHANGELOG.md              版本记录
├── workbuddy.md              WorkBuddy 开发上下文
├── scripts/
│   ├── mcd_mcp_client.py     MCP 客户端（initialize/tools-list/tools-call）
│   ├── collab_radar.py       聚合引擎（双feed+档期+稀缺度+IP）
│   ├── build_report.py       单文件 HTML 情报卡生成器
│   └── selftest.py           48 项模拟测试与安全断言
├── references/
│   ├── live-contract.md      live 实测契约（禁止猜测的证据 base）
│   └── mcp-tools.md          35 工具 live 清单（程序化生成）
└── examples/                 2026-10-12 真实抓取数据 + radar_live.json + demo_report.html
```

## 声明

参赛项目为麦当劳程序员节创意开发大赛参赛作品，由参赛者独立开发，非麦当劳官方产品。
输出仅供参考，餐品信息、价格及供应状态以麦当劳官方渠道实时结果为准。
