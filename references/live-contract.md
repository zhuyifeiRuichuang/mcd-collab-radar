# Live 实测契约（2026-10-12，禁止凭记忆修改）

> 本文档记录 `mcd-collab-radar` 对麦当劳 MCP（`https://mcp.mcd.cn`，Streamable HTTP）
> 的**真实调用结论**。所有字段名、语义、边界均以 live 返回为唯一事实来源；
> 与官方文档或历史记忆冲突时，以本文档为准并在此留痕。

## 1. 协议层

| 项 | live 事实 |
|---|---|
| initialize | 返回 `protocolVersion: 2025-06-18`，`serverInfo.name = mcd-mcp` |
| 会话 | 服务端**无状态**：initialize 响应**不下发** `mcp-session-id`，后续调用无需带会话头 |
| 鉴权 | 仅 `Authorization: Bearer <TOKEN>` 单头即可通过账户/商城/日历/门店全部工具（`authToken` 头非必需，服务端接受但忽略） |
| 响应形态 | 同时带 `content[].text` 与 `structuredContent`；**优先取 `structuredContent`**，文本正则解析仅作兜底 |
| 业务体 | `{success, code, message, datetime, traceId, data}`；`success=false` 时 `code` 携带业务错误码 |
| 限流 | 单 Token 600 次/分钟；批量扇出保持 ≥0.15s 间隔（`THROTTLE`） |

## 2. campaign-calendar（联名活动源）

| 项 | live 事实 |
|---|---|
| 返回结构 | `{currentTime, dailyList[], subscribedEvents}`；`dailyList[].{date, dateText, events[], today}` |
| 时钟源 | `currentTime` = 官方服务器时间（如 `2026-10-12 11:26:21`），本项目档期判定的第一时钟源 |
| 标题陷阱 | `activityTitle` **常为空串**，真实标题必须取 `articleDto.title` |
| 要点 | `articleDto.highlights`；正文 `articleDto.content`（含开售时间、规则）；图片 `articleDto.imgList[0]` |
| 档期语义 | `activityStage=2` 且 `button.status=2`（"提醒我"）→ **即将开始**；`activityStage=3` 且 `button.status=1` → **已开售/进行中**；日期早于 `currentTime` 当日 → 往期 |
| 实测样本 | 26 条事件 / 15 个唯一活动；含真实联名：**麦当劳 X PEACEMINUSONE**（GD 同款复古棒球帽 10-08 10:45 已开售；联名徽章第二弹 10-15 10:45 即将开售，一套三枚限量珍藏）、**麦当劳联动G-DRAGON**（韩式风味系列，龙焰鸡腿堡三件套 26.9 元起） |
| 多日合并 | 同标题同日历多日出现需合并；但同标题不同 `highlights` = 不同「弹」（棒球帽 vs 徽章），不得合并 |

## 3. mall-points-products（在售商品源）

| 项 | live 事实 |
|---|---|
| 返回结构 | `data` **直接是数组**（非 `{list,total}` 包装），默认 50 条 |
| 商品字段 | `spuId / spuName / spuImage / point / price / shopId / selling / catName / status / upTime / downTime` |
| 单位 | `point`、`price` 均为**字符串**；价格单位**元**（`45` = ¥45.00） |
| shopId | `2` = 积分兑换域；`5` = 派对/主题活动域（现金购买） |
| status 陷阱 | **恒为 `2`，不可信**——档期必须用 `upTime/downTime` 窗口相对 `currentTime` 判定 |
| catRuleIds | 官方类目规则：商品券(1>4)、实物商品(2)、**周边产品(2>8)**、实物礼品卡(2>9)、生日类派对(1>6>20)、主题类派对(1>6>21)、麦麦体验营(1>6>22)、品鉴会(1>6>25)、读书会(1>6>34)、积分兑换活动(1>6>40) |
| 列表盲区 | **默认 50 条不含全部周边**：live 实测默认列表无「酸黄瓜吧唧礼盒」(spuId 17643)，须以 `catRuleIds=2` 专项补拉（与 `2>8` 返回同一 3 件集合）后按 spuId 合并 |

## 4. mall-product-detail（详情二次校验）

| 项 | live 事实 |
|---|---|
| 返回结构 | `{spuId, spuName, images[], shopId, skuList[], selling, note}` |
| skuList | `[{skuId, extTradePrice, points, price}]`；下单仅支持 `shopId=2`，实物需 addressId |
| 僵尸检测 | 列表在列但详情返回 `code:610403 商品已下架` → 判定僵尸。live 实证：**Nike Book 2 麦当劳特别联名款**（spuId 16800，8888 积分）、**罗技键鼠套装**（spuId 17694，6666 积分）均 610403 |
| note | HTML 富文本，含活动时间、预约规则（提前 3 天 / 每场 5 儿童起订 / 上限 12）、门店限制（港澳台不适用、交通枢纽/服务区/旅游景区不适用） |

## 5. query-nearby-stores（到店锚点）

| 项 | live 事实 |
|---|---|
| 入参 | `beType`（1 到店自提→无 `beCode` / 5 得来速→有 `beCode`）、`searchType`（2 按位置）、`city`、`keyword`（searchType=2 时 city+keyword 必填，缺 → `600058`） |
| 硬上限 | **单次恒返回 5 家门店，无分页参数** → 覆盖度只能靠多锚点扇出 + `storeCode` 去重 |
| 坐标陷阱 | `longitude` / `latitude` **恒为 `0.0`**（京/沪/蓉/杭 × 到店/得来速全测）→ 不可用于地图渲染，只能用 `distance` 做距离排序 |
| 错误码 | `600014` 没有查询到该地址 → 按「告警降级不中断」处理 |
| 其他字段 | `businessStartTime/businessEndTime`（`00:00`+`23:59` 可派生全天营业）、`distance`、`reservation`、`reservationTimeOptions` |

## 6. now-time-info（备用时钟）

| 项 | live 事实 |
|---|---|
| 返回 | `data{timestamp, formatted, timezone:"GMT+08:00", ...}`；本项目以 `campaign-calendar.currentTime` 为第一时钟源，本工具为独立校验备用 |

## 7. 本项目判定规则（全部可由上述证据复核）

1. **档期**：`upTime/downTime` 窗口 vs 官方时钟 → 进行中 / 即将开始 / 已结束；`status` 字段不参与判定。
2. **稀缺度**（0-100 透明评分）：剩余 ≤3 天 +45、≤7 天 +30、≤30 天 +10；总窗口 ≤7 天 +20；积分门槛 ≥5000 +20 / ≥1000 +8；信号词（限量/限定/独家/珍藏/开售/抢先/专属/同款/第N弹）每个 +5（封顶 15）；≥60 高稀缺 / ≥35 中稀缺。僵尸商品直接「已下架」。
3. **联名识别**：IP 词典（迪士尼·唐老鸭/米妮/疯狂动物城、海底小纵队、PEACEMINUSONE/G-DRAGON、Nike、罗技 = 跨界；万马奔腾、四小福、捣蛋、过家家、酸黄瓜 = 自有 IP），命中词回显为证据；「麦麦」等过宽词**不入词典**（live 教训：会把一切误判为联名）。
4. **获取方式**：`point>0` → 积分兑换；`price>0` → 现金购买；均 0 → 待详情确认。
