# Market session calendar

本阶段只完善市场状态，不新增行情能力，不改 quantity/financial contract。

## 权威来源与覆盖

`app.market_calendar` 保存官方 2026 年证券市场日历；`app.market_session`
是唯一实时市场状态 resolver，纯内存计算，不调用 SDK 或交易所网页。
所有市场覆盖 2026-01-01 至 2026-12-31，核验更新时间 2026-10-10。
API 提供 calendar_year / coverage_start / coverage_end / source / last_updated。
覆盖范围外（包括周末）返回 unknown，而非根据工作日猜测开市。
更新下一年度时必须重新核验官方公告、半日市和小时规则并更新测试。

官方来源：

- [SSE 休市安排](https://www.sse.com.cn/disclosure/dealinstruc/closed/)
- [SZSE 2026 公告](https://www.szse.cn/disclosure/notice/general/t20251222_618087.html)
- [BSE 2026 公告](https://www.bse.cn/important_news/200027428.html)
- [HKEX 2026 证券日历 CT/075/25](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2025/ce_SEHK_CT_075_2025.pdf)
- [HKEX 证券交易时段](https://www.hkex.com.hk/Services/Trading-hours-and-Severe-Weather-Arrangements/Trading-Hours/Securities-Market)
- [NYSE 日历与时段](https://www.nyse.com/trade/hours-calendars)
- [Nasdaq 2026 日历及日间扩展时段](https://www.nasdaq.com/market-activity/stock-market-holiday-schedule)

这是普通现金股票市场的计划状态，不是证券级成交许可，也不保证所有证券、
交易场所、期权、衍生品或券商盘前盘后权限具有相同交易时间。

## 时区与时段

内部只接受 aware datetime，通过 ZoneInfo 转为既有 Asia/Shanghai、
Asia/Hong_Kong、America/New_York。不依赖 Windows 时区，不手写美东偏移。
DST 由时区数据库处理，测试固定春秋切换相邻交易日。

沿用 `regular / pre_open / break / closed`，新增 `post_market / holiday / unknown`。
半日市采用 regular + half_day / early_close 元数据，不增第二套枚举。

| 市场 | regular | 午休 | 其他时段 |
| --- | --- | --- | --- |
| CN | 09:30–11:30、13:00–15:00 | 11:30 后至 13:00 前 | 开盘前沿用 pre_open，15:00 后 closed |
| HK | 09:30–12:00、13:00–16:00 | 12:00 后至 13:00 前 | regular 后最多10分钟为收盘竞价窗口，随后 closed |
| US | 09:30–16:00 | 无 | 04:00 起 pre_open，regular 后至20:00前 post_market，其余 closed |

保留原 CN 精确端点包含约定，不改变 morning_final / close_final 的边界和定版确认。
CN 预热/final 调度不是第二套市场状态；盘口轮询和监控使用同一活跃守卫。
交易日探针仍为 CN 摄取额外安全门控，
不能推翻官方 holiday / uncovered / unknown。监控的活跃时间使用统一 resolver。
`market_time` 中历史交易分钟、量比等经济计算继续原样，不作为权威实时状态。

HK 2026-02-16、12-24、12-31 为半日市，regular 在12:00结束，没有午休/下午。
HK 收盘竞价实际在16:08–16:10（半日12:08–12:10）随机结束；本模型只标注
`closing_auction_window` 上限，不声称知道实际结束瞬间，不授权 regular 轮询。
HK 部分证券的延长早市不在普通股票窗口范围内。

US 2026-11-27、12-24 在13:00提早收盘。半日 post_market 至17:00前，依据
NYSE American/Arca/National/Texas late session；不能推广为所有券商/场所的许可。
[Nasdaq 宣布拟于2026-12-06启用23小时交易](https://www.nasdaq.com/23-5-trading)，
尚未在当前 Longbridge contract 核验 overnight；该日期后潜在夜盘窗口返回 unknown。
不启用夜盘，也不声称 2026 全年小时规则永久不变。

## 临时状态、优先级与冲突

`MarketRuntimeSignal` 只接收已核验语义的市场级状态、aware checked_at、来源标识
和 TTL（默认120秒）。缓存只内存保存，不网络取数；拒绝证券 scope、原始数字码、
证券停牌状态和跨市场输入；较旧更新不能覆盖较新缓存。

- 无运行时信号：返回官方计划状态，runtime_status=unavailable，明确临时休市未核验。
- 新鲜且明确 closed/holiday：可停止计划开市，并输出 calendar_provider_conflict。
- active 信号与假日/时段/覆盖冲突：unknown，不擅自开市。
- unknown、过期或未来时间信号：unknown，不伪造 healthy；需要新鲜信号或明确清除缓存恢复。
- 单只证券 halt、无成交、没有报价，不参与市场状态计算。

本机 Longbridge 5.2.0 正式类型：QuoteContext.trading_days（含 half_trading_days）、
trading_session；MarketContext.market_status() 返回 MarketStatusResponse.market_time，
其中 trade_status/sub_status 是 raw int。当前官方文档未提供足以核验的完整数字码映射，
因此**不自动发布 Longbridge raw code 到运行时缓存**，不通过观察样本猜码。
trading_days 是日期证据，不是临时实时开市证明；TradeStatus 是证券级，不能当市场状态。
[官方市场状态接口](https://open.longbridge.com/zh-CN/docs/market/market-status)。

[HKEX 恶劣天气继续交易安排](https://www.hkex.com.hk/services/trading-hours-and-severe-weather-arrangements/severe-weather-arrangements/overview?sc_lang=en)
意味着不能静态编码“台风即休市”。临时特别休市依赖已确认的市场级来源；未接入时
前端明确展示“计划时段、临时休市未核验”，而不宣称实时交易所状态已获确认。

## Health / API / UI

仅 regular 对 received_at 应用120秒 freshness；lunch / pre / post / holiday / closed
不因旧快照判 stale。unknown 不能 healthy。没有历史 receipt 仍保留 no_data，
上下文不可用仍 unavailable，contract status 与 runtime status 独立。

Dashboard market 和 CN quote_status.market 提供同源状态/覆盖/半日 metadata；
provider_health 添加 optional metadata，不改变既有能力矩阵和旧字段。
前端共用 marketSession formatter，仅中文展示后端状态，不读浏览器时钟推断开盘。
旧响应无新增字段仍可渲染，未知枚举显示“市场状态未确认”。

## 验证

离线测试包含官方假日、午休、DST、半日市、覆盖过期、运行时冲突/TTL、
证券 halt 隔离、health/provider-health、CN final、quantity/financial 回归。
真实只读验证使用 QuoteContext 和安装 SDK 的公开类型/只读市场状态，
不使用任何交易上下文，不伪造 active 数据；原始市场码不被擅自解释。

2026-10-10 验收：定向193 PASS；完整后端2888 passed / 6 skipped / 0 failed；
前端Vitest158、node:test5 PASS；TypeScript/生产build PASS；Ruff新增0，
quote/depth/trading_day 测试的62项历史baseline保留。初轮全量发现盘口旧守卫与
resolver 不一致，统一守卫后全量复验通过，没有解锁 Longbridge depth 能力。
三标的真实快照600519.SH/700.HK/AAPL.US和SDK当日trading_days均核验通过，
评估时间13:46 UTC三市场均closed，health=market_closed。MarketStatusResponse
真实存在，但数字码未应用为语义；临时休市自动信号仍未接入。
