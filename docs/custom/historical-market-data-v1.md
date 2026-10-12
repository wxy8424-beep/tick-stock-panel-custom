# Historical Market Data Provider v1

日期：2026-10-12。基线 main/9ba046626ecf08597eea3c0dc051e7a405a6ef73。

## 架构与隔离

新增 `app/data_providers/historical.py`：`HistoricalDailyProvider`、`HistoricalDailyResult`、`AKShareDailyProvider`、`YFinanceDailyProvider` 及显式 `get_historical_provider(market)`。这是既有 Provider 目录中的按需历史读取适配，沿用 Polars、market_from_symbol 与现有离线 CALENDARS；不注册到生产 registry/plugin，不新增数据库或写盘/缓存/自动回退系统。

现有链路：生产 daily → KlineRepository.get_daily_asset → MarketFactorEngine.from_history → FactorScoringEngine → StrategyResearchRunner；历史仓库目前不承诺完整港美数据。现有 MarketDataProvider/DAILY_COLUMNS 是生产同步契约，normalizer/kline_sync 对显式成交量要求 legacy_100_shares。本阶段不能将 AKShare“手”或 Yahoo未知单位直接送入该链路，因此新增带来源与诊断的研究结果封装，不改变旧契约、quantity白名单、全局 Parquet schema、Factor/Strategy/Portfolio/Experiment 或 Longbridge。

分级：小范围 L3 新能力与可选依赖；现有生产插件输出无法表达两组价格/调整语义/blocked 结果而不触碰写盘契约。没有核心消费入口接线，未来升级热点限于本次新增模块和依赖锁。

已按用户复用约定检查 InStock stockfetch 索引及实际公开源码；它面向现有 CN 抓取/数据库口径，不满足本任务的独立 raw/adjusted、US 和未知单位边界，未复制其代码、依赖或生产作业。

## 安装与接口

```powershell
cd backend
uv sync --frozen --extra historical
```

可选 `historical` extra 固定已审计版本 AKShare 1.19.1、yfinance 1.7.0；uv.lock 管理跨平台依赖，原有包版本未升级。默认应用不要求安装或导入这些 SDK；缺 SDK 返回 sdk_missing，无启动线程。

```python
from datetime import date
from app.data_providers.historical import get_historical_provider

result = get_historical_provider("CN").fetch_daily(
    "600519.SH", date(2024, 6, 3), date(2024, 6, 14), price_mode="adjusted"
)
payload = result.to_dict()
```

单证券/明确 date 起止（两端包含）、price_mode=raw 或 adjusted。raw 仅读来源基础 OHLC；adjusted 先读基础，再独立请求来源复权 OHLC。`frame` 为 Polars，`to_dict()` 可 JSON 序列化。没有静默转换为 DailyHistory/get_daily_asset、无自动研究执行。

## 统一结果契约

| 字段 | 语义 |
| --- | --- |
| symbol / market / trading_date | 原项目证券、CN/US、来源明确的交易日期标签 |
| open/high/low/close | 永远是基础来源 OHLC，不被复权覆盖 |
| adjustment_method | 对应基础 OHLC 的来源方法，CN=none，US=yfinance_auto_adjust_false |
| adjusted_open/high/low/close | 独立复权请求直接返回的值；未请求、失败或缺日期为 null |
| adjusted_adjustment_method | 有复权行才标 akshare_qfq / yfinance_auto_adjust，否则 null |
| source_adjusted_close | Yahoo auto_adjust=False 的实际 Adj Close，独立诊断列；不用它自行推算 OHLC |
| volume / volume_unit | 基础来源原数值，不换算；CN=akshare_lots（官方“手”原词语义），US=unknown |
| currency / source | CN A股人民币=CNY；US 从真实 history metadata 取币种，不按 .US 猜；来源接口标识 |
| fetched_at / observed_at | 本地请求完成 UTC 时刻 / 来源未提供观察时刻则 null，不用 fetch 冒充 quote time |
| dividend / split | Yahoo history(actions=True) 实际返回，仅诊断证据；CN 无则 null |

volume 不是标准 CN legacy 100股量契约。没有 /100、*100、lot-size 或复权因子推导。US SDK 即使 keepna=True 仍内部 fillna(0)；返回的 0 无法区分真零/缺失，因此置 null 并记录 sdk_zero_volume_ambiguous。非零数值原样保留，但单位 unknown，不允许用于依赖 shares/lot 的计算。

结果有 status=completed/partial/empty/unavailable/blocked 和 diagnostics[{code, mode, trading_date?}]。completed 仅表示所请求的来源数据与结构校验完成，不代表日历覆盖、volume 单位、PIT 或历史当时成交价已证明。请求非法 Date/mode 抛 ValueError；不支持市场/证券 blocked；网络/API/SDK/字段错误 unavailable；空返回 empty。复权失败保留基础数据且 partial，缺字段/价格保留 null，不 fill、不 forward-fill。

## 来源价格、调整与日期证据

- [AKShare 官方 stock_zh_a_hist 文档](https://akshare.akfamily.xyz/data/stock/stock.html)：adjust="" 不复权，"qfq" 前复权；日期列为交易日，成交量单位“手”。当前安装实现直接请求东财 fqt=0/1；独立结果不混合。qfq 会随未来除权更新，文档也允许历史价格为负；负复权值保留但 partial/non_positive_adjusted_price，不宣称研究就绪。A股人民币口径依据[上交所 A-share 说明](https://english.sse.com.cn/markets/equities/overview/)。
- [yfinance history API](https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html)及安装版 PriceHistory.history / utils.auto_adjust 已读源代码：显式 interval=1d、auto_adjust=False/True、back_adjust=False、repair=False、keepna=True、rounding=False、prepost=False、actions=True、timeout=15、raise_errors=True；end 为排除端，适配仅加一天实现包含 end_date。
- True 请求委托 SDK 的官方 auto_adjust 路径直接取返回 OHLC；其实现使用 Adj Close/Close 变换，但本项目没有复制或重算该比率。Yahoo adjusted close 包含拆股/分派影响（[Yahoo 说明](https://in.help.yahoo.com/kb/finance/adjusted-close-sln28256.html)），不等同 AKShare qfq。
- **US raw 只是 auto_adjust=False 的来源基础价格，绝不承诺完全未复权的历史当时成交价。** NVDA 拆股前后来源价格已处于可比量级，因此不能直接用于拆股前历史股数/资金成交模拟。始终附 as_traded_raw_not_established。没有反推拆股因子或“恢复原价”。
- Yahoo 1d Date index 实际为交易所本地午夜 America/New_York；只接受此 schema 与真实 EQUITY/security metadata。支持通用大写字母/数字/连字符 ticker；点号类别、指数、ETF 或其他市场不猜映射。600519.SH→600519，300750.SZ→300750；CN 仅确认的沪深 A股前缀，不接 BJ/HK/ETF/index。
- 按 trading_date 升序，重复日期直接拒绝整批，不任意择一。拒绝范围外、周末、已有 2026 日历明确休市日；2026 之外附 calendar_coverage_unknown，不假造节假日。Yahoo SDK 本身可能预先去重，附 sdk_may_deduplicate_source_dates；适配器能查 SDK 返回重复，不能证明底层原始网络数据无重复。今日/未来来源行标 daily_bar_not_final/partial。

## 真实只读验收（2026-10-12）

命令：`uv run --frozen --extra historical python scripts/smoke_historical_daily.py --run`；可用 `--market CN/US` 做有限复验。脚本不读 .env/secrets，不写运行库或行情文件。

| 样本 | 窗口 | 行数 | 返回日期范围 / 日期升序唯一 / OHLC | 价格语义 | volume / currency | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| 600519.SH | 2024-06-03..14 | 9 | 同请求两端，全部通过 | none + akshare_qfq 独立 | 原值 / akshare_lots / CNY | PASS |
| 300750.SZ | 2024-06-03..14 | 9 | 同请求两端，全部通过 | none + akshare_qfq 独立 | 原值 / akshare_lots / CNY | PASS |
| AAPL.US | 2024-05-06..17 | 10 | 同请求两端，全部通过 | auto_adjust=False 基础 + True 独立 | 原值 / unknown / USD | PASS（单位仍未知） |
| NVDA.US | 2024-06-03..14 | 10 | 同请求两端，全部通过 | auto_adjust=False 基础 + True 独立 | 原值 / unknown / USD | PASS（单位仍未知） |

首次 US 被 metadata 类型适配拒绝，真实 HistoryMetadata 是 Mapping 非 dict；已经修复并补 mock 后两个 US 样本复验 PASS，未放宽证券/币种边界。2024 均超现有日历范围，明确诊断，未把来源日期当独立交易所日历证明。

AAPL 来源 2024-05-10 返回 dividend=0.25；[Apple 官方公告](https://www.apple.com/newsroom/2024/05/apple-reports-second-quarter-results/)确认该次分红数额/登记/支付信息，不把登记日当除息日。NVDA 来源 2024-06-10 split=10、06-11 dividend=0.01；[SEC 官方披露](https://www.sec.gov/Archives/edgar/data/1045810/000104581024000144/nvda-20240607.htm)与[公司拆股 FAQ](https://investor.nvidia.com/files/doc_downloads/2024/05/NVIDIA-2024-Stock-Split-FAQ.pdf)确认 06-10 为拆股后交易开始。价格差异仅作为来源行为证据，不据此推断成交量单位或构造复权系数。

NVDA 最终 smoke 中基础 close：06-07=120.88800048828125，06-10=121.79000091552734；auto_adjust=True 同日分别为120.5442886352539、121.44371032714844。说明此次 Yahoo 基础序列并未表现为拆股前当时千美元成交价，不能将 False 标签解释为 as-traded raw。数字只是此次观测，不作为固定测试 fixture 或单位推断依据。

最终验证：mock/现有 Factor/Strategy/Provider 定向106 PASS（新增51用例），backend full3242 passed/6 skipped/0 failed，217既有warnings；本次Python Ruff零违规，四标的smoke PASS。US量与2024日历仍unknown，不因PASS提升语义声明。没有修改前端，不要求前端测试/build。

## Strategy v2 接入前 blocker

完整历史交易日历、输入数据冻结/修订版本、PIT/幸存者偏差、Yahoo 历史当时成交价语义、US volume 单位及 SDK零填充/去重证据、跨市场币种/分红/费用仍需解决。当前不自动填补停牌或缺日，不保证研究期间无遗漏；CN历史负 qfq 也不能直接交给现有要求正价格的研究评估。

将这些结果接入 Strategy/Factor、持久化归档、研究收益或生产 Provider 注册均需另行明确任务，本阶段不解锁 Longbridge daily/minute/depth/financial、HK、分钟或实盘。数据库与原有行情目录未修改。
