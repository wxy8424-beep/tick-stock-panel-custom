# Longbridge Historical Semantics Closure v1

审计与续办：2026-10-14～2026-10-15，Asia/Shanghai。
源码基线：`main / 3c6d4eff54e3012e9e5a39cf2eaff15392dd2056`。
实际 SDK：Longbridge 5.2.0。

**结论：HK/US 六只样本的历史日线读取已实证；Momentum production input contract 仍 BLOCKED，不能冻结为已满足。**

| 验证项 | HK | US |
| --- | --- | --- |
| Daily API/SDK 存在及真实样本可读 | READY（本次三只/固定窗口） | READY（本次三只/固定窗口） |
| volume_contract | BLOCKED | BLOCKED |
| price_basis：split_adjusted_price_only | BLOCKED | BLOCKED |
| bar_finality | PARTIAL | PARTIAL |
| strict historical PIT / vintage | BLOCKED | BLOCKED |
| Momentum production input overall | BLOCKED | BLOCKED |

READY 仅限表中具体能力，不表示全市场、全历史、无限额度或生产集成已可用。

## 1. 范围与现状

本轮只读审计源码、SDK、官方公开文档，并通过现有凭证机制进行有限历史查询；只新增本报告和更新项目外记忆。不修改 provider、Historical factory、archive、数据库或生产 policy，不新增依赖，不实现 Engine/Universe/Score，不运行测试，不 commit/push。

保留此前三个未跟踪报告：[Input Validation](hk-us-momentum-input-contract-validation-v1.md)、[Sample Provenance](hk-us-historical-sample-provenance-v1.md)、[Provider Contract](hk-us-historical-provider-contract-v1.md)。它们是各自日期的观察，不覆盖其原结论；本报告新增 US Longbridge 历史成功证据，不把它写成此前 yfinance 已恢复。

项目 [Longbridge manifest](../../backend/app/plugins/longbridge/plugin.yaml) 仍只声明 realtime；[provider.py](../../backend/app/plugins/longbridge/provider.py) 未提供生产 Daily dataset。[Historical factory](../../backend/app/data_providers/historical.py) 的 CN/US research adapter 不会因此自动改用 Longbridge，HK adapter 仍未注册。本轮不接通这些路径。

## 2. API / SDK 能力

逻辑 endpoint 为 Security History Candlestick，官方 Quote 协议业务指令 **27**；文档入口为 [历史 K 线](https://open.longbridge.com/zh-HK/docs/quote/pull/history-candlestick)。这不是将文档路径当成 REST GET endpoint；没有抓取认证请求或输出实际连接配置。

已安装 `longbridge/openapi.pyi` 提供：

- `QuoteContext.history_candlesticks_by_date(symbol, period, adjust_type, start, end, trade_sessions)`，返回 List[Candlestick]。
- `history_candlesticks_by_offset(symbol, period, adjust_type, forward, count, time=None, trade_sessions=Intraday)`。

本次仅调用 by_date。SDK 5.2.0 [请求实现](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/rust/src/quote/context.rs) 将输入编码为 symbol、period、adjust_type、QueryByDate、start_date/end_date 和 trade_session，经既有 QuoteContext 发出请求，返回 candle 列表。没有在客户端构建拆股/分红调整公式；调整选项传给服务端。

| 参数 | 本次值 / 已验证合同 |
| --- | --- |
| symbol | 700.HK、9988.HK、3690.HK、AAPL.US、NVDA.US、MSFT.US |
| period / frequency | Period.Day（协议 1000） |
| adjust_type | NoAdjust（0）、ForwardAdjust（1），分别读取 |
| start / end | 2026-07-01 / 2026-10-13，显式有界 |
| query_type | 按日期区间（2） |
| trade_sessions | TradeSessions.Intraday；不开 overnight，不订阅推送 |
| 日期格式 | SDK date；协议 YYYYMMDD |

公开文档说明单次日期查询有 1000 根上限，不能把截断结果当完整覆盖。本次每请求 73 根，不涉及截断或全历史下载。公开 HK/US 覆盖说明和账号额度不能代替逐证券实际覆盖、退市历史或当时可用性证明。

返回字段：open/high/low/close/turnover 为 SDK Decimal，volume 为 int，timestamp 为 datetime，trade_session 为枚举。协议响应含 symbol 与 candlesticks；SDK 返回列表中的 candle 不再逐行携带 symbol，本次身份关联为明确请求 symbol，不凭价格猜身份。

## 3. Volume semantics

已核验官方历史端点字段表、SDK 5.2.0 [Python 类型](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/python/src/quote/types.rs)、[Rust 类型及转换](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/rust/src/quote/types.rs) 和当前项目 [quantity.py](../../backend/app/plugins/longbridge/quantity.py)。

| 问题 | 已证明 | 尚未证明 |
| --- | --- | --- |
| volume 是什么字段 | 当前周期成交量；SDK int / Rust i64 | 对 HK/US 是否分别为 shares、board lots 或其他单位 |
| HK board lot | 本次整数 volume 可读取 | 是否受 lot_size 影响、是否含碎股、跨 board-lot 变更是否同尺度 |
| US shares | 当前三只各73个正整数 | 端点/市场级明确 shares 定义及拆股前后数量口径 |
| 金额字段 | turnover 单独存在，官方描述为成交额 | 端点币种、交易范围、公司行动前后聚合规则 |
| amount / value | 本次 Candlestick 公共字段中没有这两个属性 | 不从其他端点同名字段推定 alias |
| volume 调整 | 本次每只两种价格调整模式的 volume 相同 | 不证明跨拆股日期数量完全不调整或永远一致 |

volume 原样从协议映射，不存在可供本轮核验的单位转换证明。其他 API 的 shares 注释不能跨推为历史 candle 合同。正整数、常见美股习惯、HK lot_size，以及 turnover/price 比较，都不是端点单位证据。

**volume_contract = BLOCKED（HK / US）**。VR20 还需证明窗口内单位、交易范围、缺失/零量和拆股尺度一致；不能只说比例会约掉单位。本轮未计算 VR20，也未修改现有 quantity gate。

## 4. Price basis / corporate action

官方 [AdjustType 字典](https://open.longbridge.com/zh-HK/docs/quote/objects) 和 SDK 已证明两种可选模式存在。NoAdjust 的 SDK 注释为 Actual，ForwardAdjust 为 Adjust forward；中文字典对 0 的标签为“除權”，不应自行扩写成经过证明的 as-traded / split-only 公式。

| 模式 | 可保留的标记 | raw as-traded | split-adjusted only | dividend-adjusted |
| --- | --- | --- | --- | --- |
| NoAdjust | vendor NoAdjust | 完整公司行动语义未证明 | 未证明 | 未证明是否/如何处理 |
| ForwardAdjust | vendor forward-adjusted | 不作为原始成交价格使用 | 未证明 | 未证明是否/如何处理 |

请求存在 adjustment mode，并不证明 split、reverse split、cash dividend、stock dividend、rights/spin-off 的具体处理、锚点、舍入和历史重算版本。历史 candle 不返回事件账本或调整因子版本；本轮没有调用其他公司行动接口或据差值反推因子。

本次 HK 三只窗口内两种模式的日期/OHLC/volume 相同；不能据此认定没有公司行动。US 三只的 OHLC 存在差异、volume 相同；这证明选项对返回序列产生差异，不能将差异直接归因为现金分红或拆股。

2026-07-01 close 的实际对照：

| symbol | NoAdjust close | ForwardAdjust close |
| --- | --- | --- |
| AAPL.US | 294.38 | 294.115 |
| NVDA.US | 197.58 | 197.363 |
| MSFT.US | 384.28 | 383.55 |

三只在 2026-10-13 的两模式 close 分别相同（341.27、228.52、543.45），仍不证明调整锚点或事件公式。

**price_basis = BLOCKED**：不能将任何模式直接声明为目标 split_adjusted_price_only，也不在本阶段转换价格。

## 5. Timestamp、交易日与 Completed bar finality

### 5.1 新确认：SDK 返回宿主本地 naive datetime

5.2.0 [时间包装实现](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/python/src/time.rs) 将 Rust epoch 经 Python from_timestamp、timezone=None 转为 datetime；[Python 文档](https://docs.python.org/3/library/datetime.html#datetime.datetime.fromtimestamp) 说明不提供 tz 时返回本地 naive 时间。

本次宿主为中国本地时间。全部 876 根响应 candle（六只 × 两模式 × 73）的 tzinfo 均为空。本轮在同一进程用 `.timestamp()` 恢复 epoch，检查本地 roundtrip，再显式转换 UTC 和 market timezone 取交易日；这是对已核验绑定行为的诊断，不是将任意 naive datetime 猜为 UTC/交易所时间。没有修改生产归一化逻辑，也没有验证换宿主/跨 DST 后的生产适配。

| 市场 | SDK naive 示例（本机） | 恢复后的 UTC | market trading_date |
| --- | --- | --- | --- |
| HK | 2026-10-13 00:00:00 | 2026-10-12T16:00:00Z | 2026-10-13（香港午夜） |
| US | 2026-10-13 12:00:00 | 2026-10-13T04:00:00Z | 2026-10-13（纽约午夜） |

不能直接把 US SDK datetime.date() 当交易日通用规则，不能对 naive 值直接附加 UTC；序列化而不保存时区来源会丢失可重放语义。市场午夜是本次日线标签观察，不是 session close 或 publication time。

### 5.2 Finality 边界

本次日期上界固定为 10月13日，早于读取日期；各市场日期与项目当前冻结日历一致，返回 trade_session 均为 Intraday。没有读取当日未完成 bar。

这些证据支持“过去常规交易日的历史日线结构”，但未证明源端何时最终发布、是否含收市竞价、迟到交易/更正会否修订，以及具体修订版本。HK 收市/竞价窗口、US regular 与盘前盘后边界不能由 midnight 标签推导。

已安装 SDK 的 `PushCandlestick.is_confirmed` 是推送事件字段；历史 Candlestick 没有这个字段。也不能用 Rust 内部 open_updated 标志当 finality；它不是源端历史发布证明。本轮没有新增订阅或借推送能力填补历史证据。

**bar_finality = PARTIAL**；若生产要求明确的 completed-session final close，缺少定版/修订合同仍然阻止上线。

## 6. PIT / vintage 与当前项目保存能力

| 信息 | Longbridge history 返回 | 当前项目实际情况 |
| --- | --- | --- |
| trading_date | 无独立字段；由 timestamp/session 解释 | 本次显式恢复 epoch 后取市场日期，仅诊断 |
| requested_at | 无 | 本次只读诊断记录调用前 UTC 时间；不是生产 Daily ledger |
| returned_at / fetched_at | 无源端字段 | 本次记录方法成功返回后的 UTC；不是供应商发布时间 |
| available_at | 无 | historical available_at=null，不回填成午夜或收盘时刻 |
| source revision / vintage | 无 | null，无历史版本查询参数/版本标识证据 |
| Historical schema 的 fetched_at | 非 SDK 返回 | research schema 成功行保存本次取得时间；不是 Longbridge 集成 |
| observed_at | 非 SDK 返回 | 现有 Historical adapter 写 null；不等于历史当时已观测 |

Longbridge 的生产 Daily dataset/store 尚未建立，本轮没有写入它。已有 realtime observation 和金融报表公告时间字段不能作为历史日线 available_at。

因此不能回答“D 收盘后，在当时指定 cutoff 已经知道的是哪一份数据”。仅排除未来 trading_date，不足以避免后来公司行动追溯调整、历史修订等未来信息。

**pit_status = BLOCKED**。未来按真实接收时间冻结可证明以后系统已持有的版本；不能倒造本轮取得之前的 available_at，或宣称已闭合 strict historical PIT。本轮没有实施 prospective ledger。

## 7. 真实样本验证

### 7.1 调用范围与结果

最终完整观察窗口：**2026-10-15 09:44:28.174～09:44:29.826，Asia/Shanghai**（01:44:28.174～01:44:29.826Z）。

每只两次 by_date 请求，显式 NoAdjust/ForwardAdjust；未请求 quote、订阅、TradeContext、Market/Historical Context、证券目录或 Universe。没有写生产数据库/Parquet、缓存或报价数据。诊断通过 Python stdin 在内存运行，不保存或提交脚本、完整供应商响应和凭证；本报告只保留所选公共字段及摘要。

source 均为 `longbridge.history_candlesticks_by_date`，公共 fields 均为 `open/high/low/close/volume/turnover/timestamp/trade_session`。

| symbol | market | 返回 date_range | NoAdjust / ForwardAdjust rows | volume 正整数（每模式） | OHLC 两模式一致 | 读取 status | Momentum status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 700.HK | HK | 2026-07-02～10-13 | 73 / 73 | 73/73 | 是 | SUCCESS | BLOCKED |
| 9988.HK | HK | 同上 | 73 / 73 | 73/73 | 是 | SUCCESS | BLOCKED |
| 3690.HK | HK | 同上 | 73 / 73 | 73/73 | 是 | SUCCESS | BLOCKED |
| AAPL.US | US | 2026-07-01～10-13 | 73 / 73 | 73/73 | 否 | SUCCESS | BLOCKED |
| NVDA.US | US | 同上 | 73 / 73 | 73/73 | 否 | SUCCESS | BLOCKED |
| MSFT.US | US | 同上 | 73 / 73 | 73/73 | 否 | SUCCESS | BLOCKED |

每次结果均日期有序唯一、缺少/意外日历 session 数为 0、OHLC 有限正数且关系有效、turnover 全部有限非负、trade_session 全部 Intraday。六只各自两模式 volume 均相同。这里比较的是已选证券的固定窗口，不是 Universe 完整覆盖或单位验证。

2026-10-13 NoAdjust 末根公共样本：

| symbol | open | high | low | close | volume（unit unknown） | turnover（端点币种未闭合） |
| --- | --- | --- | --- | --- | --- | --- |
| 700.HK | 421.0 | 425.6 | 419.8 | 425.2 | 12724935 | 5384668974.09 |
| 9988.HK | 107.7 | 108.0 | 104.9 | 107.2 | 49272346 | 5248002015.15 |
| 3690.HK | 71.9 | 72.35 | 69.9 | 72.3 | 18240662 | 1303528736.117 |
| AAPL.US | 344.665 | 348.15 | 340.74 | 341.27 | 38983839 | 13395660511.0 |
| NVDA.US | 224.34 | 228.64 | 223.06 | 228.52 | 84036941 | 19047315321.0 |
| MSFT.US | 544.64 | 551.15 | 543.06 | 543.45 | 23851953 | 13031938224.0 |

### 7.2 请求/接收时间（UTC，2026-10-15）

| symbol | NoAdjust requested_at → fetched_at | ForwardAdjust requested_at → fetched_at |
| --- | --- | --- |
| 700.HK | 01:44:28.177442 → 01:44:28.778326 | 01:44:28.782470 → 01:44:28.880842 |
| 9988.HK | 01:44:28.883204 → 01:44:28.962842 | 01:44:28.964531 → 01:44:29.063410 |
| 3690.HK | 01:44:29.063937 → 01:44:29.171635 | 01:44:29.172523 → 01:44:29.261645 |
| AAPL.US | 01:44:29.262176 → 01:44:29.361501 | 01:44:29.362146 → 01:44:29.468655 |
| NVDA.US | 01:44:29.469391 → 01:44:29.557758 | 01:44:29.558938 → 01:44:29.657998 |
| MSFT.US | 01:44:29.659133 → 01:44:29.755844 | 01:44:29.756982 → 01:44:29.826119 |

这些时间只证明现在成功收到，不是历史 D 的 available_at。两模式分开请求，没有源版本原子一致性保证。

### 7.3 初次诊断的归因修正

2026-10-14 13:54:46～13:54:47Z 的首次诊断将网络请求和本地 timestamp 校验放在同一分类边界，700.HK 返回 sdk_or_response 后停止，其余未执行。该结果不能被写成供应商拒绝、TLS 或权限失败。

2026-10-15 01:43:41.515～01:43:42.280Z，独立小窗口 10月12～13日请求明确成功返回两根，随后的类型检查证实 timestamp 为 naive datetime。首次诊断含“tzinfo 必须存在”的本地 gate，因此其结果不足以判断供应商失败；本轮已通过源码与分阶段成功观测澄清，不保留错误的 API failure 推断。

随后完整六证券读取使用已核验的同进程本地时间逆转换，不修改 SDK、生产代码或主机时区。续办不是审批绕过；没有发生审批重试，也未改 SSL/proxy/权限。累计 14 次有限 history 调用（首次1次、时间戳定位1次、最终12次），没有大规模下载。

本次成功仅证明六证券这些读取可用；不推导全市场权限、以后额度、商业授权或 source SLA。此前 yfinance 的 US TLS/API 失败仍是独立来源的既有观察，本轮未重试 yfinance。

## 8. Provider Decision

| Provider | Market | Decision |
| --- | --- | --- |
| Longbridge HK | HK | Production candidate（条件性；当前 Momentum 输入仍 BLOCKED） |
| Longbridge US | US | Production candidate（本次历史读取实证；当前 Momentum 输入仍 BLOCKED） |
| yfinance US | US | Research only（沿用既有代码/官方使用定位，本轮未复验） |

未新增替代源或 fallback。生产候选不是将现有 quantity gate 改为 supported，也不是批准实施 adapter。[Provider Contract](hk-us-historical-provider-contract-v1.md) 的使用权边界继续有效；SDK 开源许可与实际行情数据授权分开。

## 9. GitHub / 官方参考与许可

仅审阅 Longbridge 官方 SDK，未额外引用 Qlib/OpenBB，未引入包或复制代码。

| repo / revision | license 证据 | 本轮用途 | 未采用 | code copied |
| --- | --- | --- | --- | --- |
| longbridge/openapi / v5.2.0 | [python/Cargo.toml](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/python/Cargo.toml) 明确 MIT OR Apache-2.0 | 核验请求编码、类型、timestamp 转换和能力边界 | 不复制实现，不替换当前 SDK/Provider，不将代码许可当行情授权 | NO |

这是对安装版本对应 tag 的公开源码核验；wheel metadata 缺 License 字段的事实仍保留，不假称已修改安装包或完成行情许可审查。官方在线文档可能比 5.2.0 新，因此方法/字段判断同时与本机 pyi 和真实返回交叉核对。

## 10. Blockers 与最小下一步

1. 取得 Longbridge 对 **historical candle + HK/US** 的单位说明：shares/lot、HK碎股/board lot、US跨拆股 volume、turnover币种及交易范围。不是引用其他 endpoint 的 shares 字样。
2. 取得 NoAdjust/ForwardAdjust 的官方公司行动算法说明，区分拆股、合股、现金/股票分红等；用官方事件窗口交叉验证。不能因本次 US 调整差异直接宣布含分红，或将 forward 当 split-only。
3. 确定最终日线发布时间、收市/竞价边界、迟到更正与历史修订规则；历史查询不能套用推送 confirmed 字段。
4. 明确 source vintage / historical available_at 是否可获得；不可获得时，历史 PIT 继续 BLOCKED。若要改为从未来真实冻结开始的 prospective 产品，应另立决定，不在本阶段降低标准。
5. 后续 adapter 必须显式处理 SDK 5.2.0 的宿主本地 naive timestamp，避免把宿主/交易所/UTC混同；本轮只记录问题，不写实现。

**是否可以冻结 Momentum Input Contract 为生产已满足：NO。** 可读性已闭合，volume、split-only price basis、finality 和 PIT 的关键语义未闭合。下一阶段应为供应商端点语义证据确认，而不是 Momentum Engine、Universe、评分或生产接入。

## 11. 收尾边界

- 无代码/依赖/数据库/生产配置修改；不运行 pytest、Ruff、frontend tests/build。
- 仅对文档执行本地链接、敏感内容和 whitespace 检查；未 stage/commit/push。
- 分支与 HEAD 保持 main / 3c6d4eff；原有三个未跟踪报告保留，旧 Git 远端收尾待办不在本轮执行。
