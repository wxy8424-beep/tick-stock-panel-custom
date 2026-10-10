# Longbridge quantity-unit evidence chain

核查日期：2026-10-10；起点 `e3d43bfd026f30b1ba3d6c27bb2731b6ebbbc20b`。
实际安装 `longbridge 5.2.0`（importlib.metadata 与本地 dist-info 一致），不是任务背景中的 5.1.0。
结论：本次查阅范围内没有足以确定以下九项 market + endpoint 数量单位的官方证据。
全部保持 CONTRACT_BLOCKED，不新增 daily/minute/depth5 dataset，不做任何数量换算。
这不等于断言官方任何地方都不存在单位说明，也不等于 SDK 没有相关行情接口。

## 证据与覆盖范围

| 来源 | 字段 / 摘要 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| 安装包 `longbridge/openapi.pyi`，5.2.0 | Candlestick.volume:int，Depth.volume:int；turnover:Decimal；position:int；order_num:int | 类型和字段语义分离 | int/Volume 不证明 shares、手或 board lots；不证明任何市场的转换比例 |
| [5.2.0 Python 绑定](https://github.com/longbridge/openapi/blob/v5.2.0/python/src/quote/types.rs) | Candlestick.volume、Depth.volume 为 i64，turnover 单独映射 PyDecimal | 绑定暴露公开字段；可按对象属性读 | 未定义市场特有数量单位 |
| [5.2.0 Rust 类型](https://github.com/longbridge/openapi/blob/v5.2.0/rust/src/quote/types.rs) | Candlestick / Depth / PushQuote / Trade 的 volume 注释为 Volume，Depth.order_num 为订单数 | 字段类型及数量与订单数不相同 | 不证明这些不同端点的 volume 单位相同 |
| [历史 K 线](https://open.longbridge.com/zh-CN/docs/quote/pull/history-candlestick) | 当前周期成交量 int64，成交额单独为 turnover | history_candlesticks_by_offset/by_date 与周期参数、历史配额 | 没有按 CN/HK/US 说明股/手/lot；日K证据不能跨推分钟K |
| [K 线](https://open.longbridge.com/zh-CN/docs/quote/pull/candlestick) | 周期成交量与成交额独立字段 | candlesticks 响应结构 | 没有明确市场与单位对应关系 |
| [分时](https://open.longbridge.com/zh-CN/docs/quote/pull/intraday) | price、volume、turnover、avg_price | IntradayLine 的字段 | 并非完整 OHLC K线；不能直接视为项目 minute contract；成交量无明确单位 |
| [盘口](https://open.longbridge.com/zh-CN/docs/quote/pull/depth) | position 档位，volume 挂单量，order_num 订单数 | 挂单量不能当订单笔数；报价与数量分别存放 | 没有市场特有股/手/board lot 定义；档位数或样本值不能补证 |
| SDK 当前对象与 inspect.signature | QuoteContext 提供 candlesticks、history_candlesticks_by_offset、history_candlesticks_by_date、intraday、depth | 方法实际存在；签名与本机版本匹配 | 方法存在、返回成功、数值碰巧吻合均不证明单位 |

仅以上官方来源用于 contract 判断。官方示例中的数字、lot_size、样本行情、市场习惯均未作为解锁依据。
SDK 其他端点即使明确写 shares，也不能替 daily/minute/depth 的 volume 建立单位契约。

## 当前项目消费者

- `docs/plugin-development.md` 的单位制：volume 为 100股单位 / 手；amount 为元；日K原始未复权价。
- daily：`data_providers.normalizer.normalize_daily` 和 `services.kline_sync._normalize_daily`
  在 cast/select 前调用 `validate_quantity_units`；自定义日K落盘入口也校验。
- minute：`kline_sync._normalize_minute`、`_try_custom_minute` 及 GenericHTTPProvider._normalize_minute
  校验 quantity；时间仍是北京墙钟，不能因证明 volume 就扩大成完整 HK/US minute 支持。
- depth：`DepthService._call_depth_batch` 检查声明、get_depth_batch，逐记录单位校验；五档
  bid_volumes/ask_volumes 沿用手，前端封单额乘100。Depth.position 和 order_num 不参与换算。
- `contracts.validate_quantity_units` 只接受显式 legacy_100_shares；unknown/null 和 shares/board_lots/contracts
  拒绝；缺 metadata 的老 Provider 保留原行为。本阶段不改这些核心流程。
- Longbridge 原先没有 get_daily/get_minute/get_depth_batch 实现，仅声明 realtime；不能把 SDK 原始对象
  当标准 dataset frame。Settings 使用同一 market_capabilities，不应因诊断成功变绿。

## Evidence matrix

| Market | Capability | SDK field / endpoint | Project semantic | Official unit evidence | Conversion | Status |
| --- | --- | --- | --- | --- | --- | --- |
| CN | daily | Candlestick.volume / history_candlesticks_by_offset(Day) | legacy_100_shares | 缺 CN 日K单位明文 | 无 | CONTRACT_BLOCKED |
| CN | minute | Candlestick.volume / history_candlesticks_by_offset(Min_1) | legacy_100_shares | 缺 CN 分钟K单位明文 | 无 | CONTRACT_BLOCKED |
| CN | depth5 | Depth.volume / depth | legacy_100_shares | 缺 CN 挂单量单位明文 | 无 | CONTRACT_BLOCKED |
| HK | daily | Candlestick.volume / history_candlesticks_by_offset(Day) | 当前 legacy 消费者仍为100股单位 | 缺 HK 日K单位明文 | 无 | CONTRACT_BLOCKED |
| HK | minute | Candlestick.volume / history_candlesticks_by_offset(Min_1) | 当前 legacy 消费者仍为100股单位 | 缺 HK 分钟K单位明文 | 无 | CONTRACT_BLOCKED |
| HK | depth5 | Depth.volume / depth | 当前 legacy 消费者仍为100股单位 | 缺 HK 挂单量单位明文 | 无 | CONTRACT_BLOCKED |
| US | daily | Candlestick.volume / history_candlesticks_by_offset(Day) | 当前 legacy 消费者仍为100股单位 | 缺 US 日K单位明文 | 无 | CONTRACT_BLOCKED |
| US | minute | Candlestick.volume / history_candlesticks_by_offset(Min_1) | 当前 legacy 消费者仍为100股单位 | 缺 US 分钟K单位明文 | 无 | CONTRACT_BLOCKED |
| US | depth5 | Depth.volume / depth | 当前 legacy 消费者仍为100股单位 | 缺 US 挂单量单位明文 | 无 | CONTRACT_BLOCKED |

正式 metadata quantity_unit 保持 unknown。三种 reason 分别是
`candlestick_volume_unit_evidence_missing`、`minute_candlestick_volume_unit_evidence_missing`、
`depth_volume_unit_evidence_missing`；Settings 用中文解释缺少市场对应的官方证据。
realtime 与 financial 的既有状态不变；adj_factor/full_minute 的 unsupported 不变。

## 安全诊断

在 backend：`uv run --frozen python -m app.plugins.longbridge.quantity_smoke`。
固定600519.SH、700.HK、AAPL.US，各两根未复权日K、两根未复权1分钟K及一次盘口，
只通过现有 provider 的 QuoteContext/lock/认证 bundle 读取，不订阅，不使用交易或账户接口。
历史查询可能消耗当月标的额度；只测三个标的，不探全市场。
打印 SDK version、symbol、market、dataset、固定 method、行数、字段类型与固定状态。
不打印原始对象、价格、成交量数值、lot_size、exception原文、credentials或完整环境。
不写证券目录、Parquet、偏好、缓存文件或任何运行数据；close 清引用。

`status` 仅 SUPPORTED/CONTRACT_BLOCKED/SDK_UNSUPPORTED/EMPTY。本次不会返回 SUPPORTED。
成功但单位未证实为 CONTRACT_BLOCKED；空数据为 EMPTY；缺SDK或方法为 SDK_UNSUPPORTED。
另一个 `request_status` 区分 success、empty、method_missing、sdk_missing、response_shape_mismatch、
entitlement_denied、authentication、network、symbol、sdk_exception。权限失败保留静态能力阻塞，
不根据一只股票无权限把整个市场记成 SDK 不支持。
诊断退出0表示诊断正常完成（允许空响应和行情权限不足），绝非 capability 已支持。
真实观察仅作结构与调用验证，绝不改变 capability、quantity_unit 或写盘路径。

## 后续解除条件

逐 market + endpoint 获得明确单位定义与版本/URL；再核对项目量、金额币种、时区、复权、
资产类型与路由范围。只有这些契约均满足且对应 adapter/回归通过才声明 supported。
即便明确 shares，也不能直接把 shares metadata 放进 legacy消费者；必须审查有依据的转换、
只转换一次且保留原源语义。不得通过 lot_size、样本比较或未注明单位的整数类型替代证据。

## 本阶段验证进度

- mock targeted：103 passed（quantity、market contracts、realtime Provider、financial、credentials）。
- Ruff 本次五个 Python 文件：PASS，0 violations。
- 真实 quantity_smoke：PASS，SDK 5.2.0；600519.SH、700.HK、AAPL.US 各 daily/minute 两根，
  depth 分别10/20/2档，九次 request_status=success、volume_type=int，退出0。
  所有 status=CONTRACT_BLOCKED、quantity_unit=unknown；结构验证不构成单位证明。
- backend full：2743 passed / 6 skipped / 0 failed，216历史warnings；比2712基线新增31项测试。
- frontend settings：9 passed；pnpm build PASS，仅既有大chunk提示。两处前端文件仅新增中文原因及测试，
  metadata schema/API字段结构未变；无需扩大为无关全前端回归。
- 候选9文件敏感扫描PASS，匹配3项本机凭证，0违规；完整diff审查及diff --check PASS。
