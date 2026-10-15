# HK/US Historical Sample Provenance Validation v1

审计日期：2026-10-14，Asia/Shanghai。
源码基线：`main / 3c6d4eff54e3012e9e5a39cf2eaff15392dd2056`。

**结论：HK 有真实 Daily OHLCV 样本；US 本轮取数未成功。六只证券均未闭合 Momentum Input Contract，overall_status=BLOCKED。**

## 1. 范围及证据类别

- US：AAPL.US、NVDA.US、MSFT.US，使用项目已有 YFinanceDailyProvider。
- HK：0700.HK、9988.HK、3690.HK，使用既有 Longbridge SDK 5.2.0 和本地凭证机制做有限只读诊断，不注册 Daily Provider。
- 固定请求范围：2026-07-01～2026-10-13，两端包含。上限在本次读取日前一天，避免混入当日未完成 bar。
- 未写 Momentum Engine，未计算 Score/VR20，未生成 Ladder/Universe，未写生产行情、archive、context、policy 或 snapshot。
- 未调用 TradeContext、订阅、实时 quote、Dashboard、生产 bootstrap 或回填；未安装依赖，未修改 SSL/proxy/凭证/Git 配置。
- 项目内仅新增本报告；保留上一阶段未跟踪的 input-validation 文档，不暂存、不 commit、不 push。

诊断脚本与脱敏证据保存在项目外开发根的 `.tools/`：
`probe-momentum-historical-provenance-v1.py` 和 `hk-us-historical-provenance-v1/`。
这些不是生产 Provider、数据归档或项目 Git 内容。证据只保留请求范围、公开证券元数据、选定 OHLCV/turnover 字段、摘要与固定错误分类，不保存授权请求、凭证、完整供应商响应或原始 SDK 异常。

yfinance 的 timezone/cookie 缓存隔离到诊断临时目录，宿主完成后关闭并清理；未写项目 data 或常规用户 yfinance 缓存。首次沙箱临时目录清理失败，不宣称该沙箱目录已清理；未修改其权限或据此重试供应商网络配置。

## 2. 请求路径和标识映射

### US

`YFinanceDailyProvider.fetch_daily(symbol, start, end, price_mode=adjusted)`：

- SDK yfinance 1.7.0；source=`yfinance.Ticker.history/yahoo`。
- 日频1d；基础模式 auto_adjust=False，调整模式为独立 auto_adjust=True 请求。
- back_adjust=False、repair=False、keepna=True、rounding=False、prepost=False、actions=True。
- 检查 metadata 中 symbol、EQUITY、America/New_York 与 currency。
- raw 阶段无有效数据时适配器提前返回，不继续请求 adjusted；本轮三个 US 样本均如此。

### HK

使用既有 `LongbridgeProvider._get_context()`，未通过生产行情注册或 QuoteService：

1. `QuoteContext.static_info([symbol])`，核对返回 symbol/name/currency/exchange。
2. `history_candlesticks_by_date`，Period.Day、NoAdjust、固定起止日期、TradeSessions.Intraday。
3. 同范围独立请求 ForwardAdjust，对齐两组日期并检查价格/volume。

总计3次 static_info 和6次有限历史请求，无无限范围或全市场下载。
供应商权限只证明这些调用本次可用，不代表其它市场/数据集或未来权限保证。

0700.HK 显式映射为供应商 `700.HK`：

- [腾讯经 HKEX 披露的文件](https://www.hkexnews.hk/listedco/listconews/sehk/2025/0408/2025040800720.pdf)区分代码700的港币柜台和80700的人民币柜台。
- [Longbridge 历史 K 线接口](https://open.longbridge.com/docs/quote/pull/history-candlestick)使用 ticker.region 标识并展示700.HK。
- 本次 static_info 实际返回700.HK/TENCENT/SEHK/HKD，保留 requested_symbol 与 provider_symbol，不改生产 canonicalization，不按通用去零算法改其它证券。

## 3. 真实请求结果

### 3.1 每个 symbol 的最终状态

这里 price_status 指是否满足 **split_adjusted_price_only**，volume_status 指是否满足可比较的历史 volume/VR20 输入契约，pit_status 指历史 D 时点可得性。它们不是 API 成功率。

| Symbol | Source | Coverage | price_status | volume_status | pit_status | overall_status |
| --- | --- | --- | --- | --- | --- | --- |
| AAPL.US | yfinance/Yahoo，实际尝试 | 0 returned；覆盖未知，TLS错误 | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| NVDA.US | yfinance/Yahoo，实际尝试 | 0 returned；覆盖未知，TLS错误 | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| MSFT.US | yfinance/Yahoo，实际尝试 | 0 returned；覆盖未知，source API错误 | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| 0700.HK → 700.HK | Longbridge history_candlesticks_by_date | 73 rows；2026-07-02～2026-10-13 | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| 9988.HK | Longbridge history_candlesticks_by_date | 73 rows；2026-07-02～2026-10-13 | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| 3690.HK | Longbridge history_candlesticks_by_date | 73 rows；2026-07-02～2026-10-13 | BLOCKED | BLOCKED | BLOCKED | BLOCKED |

US Daily 数据取得状态为 **UNAVAILABLE**，并不表示这三只股票在该窗口没有交易。
HK Daily 数据结构/窗口观测可以通过，但完整输入契约仍 BLOCKED。
不存在把 successful API access 直接标成价格、单位或 PIT READY 的步骤。

### 3.2 US：执行环境错误与供应商结果分开

首次沙箱运行约20:41:23上海时间，三只均返回 source_api_error，随后诊断临时目录清理发生 Windows PermissionError。不能据此认定 Yahoo 故障、symbol 不支持或权限不足。

使用项目外可写临时目录，在宿主完成有限复验，审批成功且命令实际执行：

| Symbol | 请求开始 UTC | 请求结束 UTC | 适配结果 / 固定诊断 |
| --- | --- | --- | --- |
| AAPL.US | 2026-10-14T12:42:26.453786Z | 12:42:26.595833Z | unavailable；network_error / tls_error |
| NVDA.US | 2026-10-14T12:42:26.596836Z | 12:42:26.606180Z | unavailable；network_error / tls_error |
| MSFT.US | 2026-10-14T12:42:26.607210Z | 12:42:26.626085Z | unavailable；source_api_error，原因未细分 |

三个结果的成功 fetched_at 列表为空、date_range=null、volume_available_ratio=null，没有 OHLC/Volume/adjusted/action rows。
请求完成时间不是成功取到 bar 的 fetched_at。空集合的 ordered_unique=true 是逻辑空值性质，不算日期校验PASS；无数据也不等于 OHLC 数值错误。

窗口按冻结 US 日历预期有73个 session，但0 returned 只表示未取得这些输入，不是供应商缺失73个交易日的事实。共享 SDK 状态、缓存或错误传播可能影响后续调用，不声称每只都已完成独立的服务器往返。

宿主结果出现后未重试 US 请求，未切换其它数据源、SSL、证书或代理；没有执行额外 NVDA 公司行动窗口请求。MSFT 的错误不能从相邻证券的 TLS 分类推断。
这是实际数据请求失败，**不是 approval transport failure，也没有证明 entitlement 被拒绝**；US entitlement 仍 UNKNOWN。

### 3.3 HK：OHLCV 结构和日期覆盖

| 项目 | 700.HK | 9988.HK | 3690.HK |
| --- | --- | --- | --- |
| SDK返回名称 | TENCENT | BABA-W | MEITUAN |
| exchange / current currency metadata | SEHK / HKD | SEHK / HKD | SEHK / HKD |
| Frequency / returned trade_session | Day / Intraday | Day / Intraday | Day / Intraday |
| 基础 / 调整后 rows | 73 / 73 | 73 / 73 | 73 / 73 |
| 日期升序唯一 | PASS | PASS | PASS |
| 两个调整模式日期完全一致 | PASS | PASS | PASS |
| 冻结HK日历预期 session / missing / unexpected | 73 / 0 / 0 | 73 / 0 / 0 | 73 / 0 / 0 |
| 基础与调整后 OHLC 正值且满足 low/open/close/high 关系 | PASS | PASS | PASS |
| volume 非空 / 整数 / 非负 | 73 / 73 / 73 | 73 / 73 / 73 | 73 / 73 / 73 |
| volume 为0行数 | 0 | 0 | 0 |
| volume_available_ratio（数值存在性） | 100% | 100% | 100% |
| 两个调整模式 volume 相同 | 73/73 | 73/73 | 73/73 |
| 两个调整模式 OHLC 全部相同 | 73/73 | 73/73 | 73/73 |
| turnover 有限非负 | 73/73 | 73/73 | 73/73 |

HK请求起点7月1日为既有日历假日，返回首日7月2日与其一致。
仅检查固定窗口，不宣称上市以来完整覆盖、全市场覆盖、无历史修订或缺日一定等于停牌。

选定实际端点值（供应商基础价格和原数量，未缩放）：

| Symbol | 日期 | close | ForwardAdjust close | volume | turnover 原字段 |
| --- | --- | ---: | ---: | ---: | ---: |
| 700.HK | 2026-07-02 | 430.2 | 430.2 | 40905100 | 17910774601.0 |
| 700.HK | 2026-10-13 | 425.2 | 425.2 | 12724935 | 5384668974.09 |
| 9988.HK | 2026-07-02 | 94.5 | 94.5 | 106165597 | 10101039459.0 |
| 9988.HK | 2026-10-13 | 107.2 | 107.2 | 49272346 | 5248002015.15 |
| 3690.HK | 2026-07-02 | 70.85 | 70.85 | 68122830 | 4875791932.0 |
| 3690.HK | 2026-10-13 | 72.3 | 72.3 | 18240662 | 1303528736.117 |

这些价格不是收益/Score，turnover 列也不是换手率。
诊断序列化将 Decimal 转为有限浮点用于结构检查，不能作为原始响应的逐字节或精确小数档案。

## 4. Completed bar 与 timestamp

**可以确认：**请求Period.Day；只返回截至10月13日的历史日期；本次获取在10月14日，交易日历上的这些 session 已结束，日期与73个预期session对齐。

**尚不能确认：**供应商对于每根 bar 的最终定版、修订规则与当时的发布时间。SDK Candlestick 没有本次可用的 per-bar final/publication/vintage 证据。`provider_finality_verified=false`，不能将本轮 structural PASS 改成 finality READY。

HK首尾 SDK timestamp 经既有5.2.0 timestamp逆转换得到：

- 首行2026-07-01T16:00:00Z，对应HK本地2026-07-02 00:00。
- 尾行2026-10-12T16:00:00Z，对应HK本地2026-10-13 00:00。

这是返回日期标签的观测，不是16:00收盘或数据可得时间。按 Asia/Hong_Kong 转成日期后对齐；没有把 UTC 日期、午夜或 SDK timestamp 冒充发布/接收时间。
现有 frozen HK calendar ID/version用于日期检查；它没有消除收盘竞价/源定版证据缺口。

## 5. Price basis / corporate-action semantics

目标：同一比较尺度、仅拆并股调整，不混入现金分红总收益，且调整证据在相应cutoff已可得。

| 来源模式 | 本轮证据 | 判断 |
| --- | --- | --- |
| yfinance auto_adjust=False | 宿主请求失败，无新base close | 不能认定as-traded或split-only；BLOCKED |
| yfinance auto_adjust=True | raw失败提前返回，未执行此阶段 | 未取得adjusted close；BLOCKED |
| Longbridge NoAdjust | 三只73根基础OHLC | 模式存在、结构已观察；不等于目标split-only契约 |
| Longbridge ForwardAdjust | 三只73根调整后OHLC，与基础数值一致 | 不能由相等推断“没有公司行动”或“只调拆股”；BLOCKED |
| Longbridge动作证据 | Candlestick未返回action history；本轮未另查公司行动集 | 无完整split/dividend事件到价格/volume的映射 |

[Longbridge AdjustType 定义](https://open.longbridge.com/docs/quote/objects)只确认NoAdjust/ForwardAdjust的模式标签；本轮检查的历史K线文档未闭合拆股、现金分红及数量回溯的完整计算语义。
现有yfinance1.7.0代码的auto_adjust委托Adj Close/Close比值变换OHLC，不能因方法名称认定为split_adjusted_price_only。没有反推因子或尝试移除分红调整。

作为后续行动窗口的官方线索，[NVIDIA 2024年6月7日8-K](https://www.sec.gov/Archives/edgar/data/1045810/000104581024000144/nvda-20240607.htm)说明10拆1并自2024-06-10按调整后基础交易。本轮只核验该官方记录，没有成功取得该行动窗口的价格/volume，所以不能用于宣称NVDA样本已证明调整等价。

价格字段/模式的结构观测为HK PARTIAL，**目标split-only等价性六只均BLOCKED**。

## 6. Volume / currency / turnover / consistency

| 检查 | HK真实样本 | US真实样本 |
| --- | --- | --- |
| Volume存在性 | 三只均73个正整数 | 未取得数据 |
| Unit | unknown；整数不等于shares或lots证明 | 当前adapter声明unknown；本轮无观测 |
| Currency | 当前static_info均HKD；非逐日历史币种证明 | 未取得metadata，不填USD |
| Turnover | 返回独立数值字段，原样保留 | 本路径无成功观察到的turnover数据 |
| 同窗口/调整模式一致性 | 日期对齐、两模式volume逐行相同 | 无法检查 |
| 跨公司行动历史可比性 | 无完整动作/volume调整证据 | 无法检查 |
| VR20输入契约 | BLOCKED | BLOCKED |

官方历史接口将volume描述为Volume、turnover描述为Turnover，未在本次可用字段定义中证明具体数量单位和历史缩放约定。turnover 与另列的turnover_rate不同；金额用途应映射到单独amount语义并核实币种/范围，不能将该原字段当作换手率，也不能仅凭数值大小或amount/price比值断定“股”。

Volume本身无币种；HKD是现价/金额解释需要的元数据，不能证明volume单位或所有历史期间的币种一致性。未知绝对单位只有在整个窗口稳定尺度和统计范围已证明时才可能在比值中消去；本轮只证明同窗口返回字段一致，没有证明拆股/合股和半日市下的完整可比性。

未使用lot_size、未乘除100、未用价格因子修复数量、未把turnover/close反算成volume、未计算VR20。已有production quantity blockers保持不变。

## 7. PIT 与 provenance

| Symbol | 本地成功 fetched_at UTC | historical available_at | source vintage |
| --- | --- | --- | --- |
| AAPL.US | null（失败，仅有attempt时间） | null | null |
| NVDA.US | null（失败，仅有attempt时间） | null | null |
| MSFT.US | null（失败，仅有attempt时间） | null | null |
| 0700.HK | 2026-10-14T12:42:57.043691Z | null | null |
| 9988.HK | 2026-10-14T12:42:57.228474Z | null | null |
| 3690.HK | 2026-10-14T12:42:57.432710Z | null | null |

HK数据在成功读取结束时已被本次诊断观察到，但这不证明在每个历史D收盘后已存在同一组值。SDK版本不是数据vintage，bar timestamp不是available_at，当前static_info不是历史security master。

本地诊断证据文件与hash可以追溯本次观测，不能替代供应商历史vintage/定版/发布证据，也没有补造过去可得的Snapshot。
**PIT：六只均BLOCKED。**

## 8. 脱敏证据索引

以下文件位于项目外诊断目录，不纳入Git。hash针对规范化JSON证据文件，非供应商原响应，也不是凭证摘要：

| 最终宿主证据文件 | SHA-256 |
| --- | --- |
| us-AAPL.US-20261014T124226Z.json | `7a6fbd231a9bc36a3370de3ff34c07f03fe1e8ad4c13117540a70fdeb698d8af` |
| us-NVDA.US-20261014T124226Z.json | `a5958a0ae4e35499848ff3af78a896dfac0cf348e4e006b8829a468d1351def2` |
| us-MSFT.US-20261014T124226Z.json | `def22f2e7e4a2463072c85dc7a25598befca7d5bf588de5fd3fd68077437a0a4` |
| hk-0700.HK-20261014T124257Z.json | `eb5703ac685576d9ab1687f2d66d82ee85d1571c81f3af3ffe690d89261a74c1` |
| hk-9988.HK-20261014T124257Z.json | `0232350df23a7778a545aef97db76847e5e6ab2ea17f762cab3b2d4faafcf28b` |
| hk-3690.HK-20261014T124257Z.json | `2c95258dbdf7cc032f6ede7f316345929cba59eee0e3bf61aace65da3602b5e6` |

首次沙箱的三个US不可用摘要单独保留，不替代宿主结果。它们不含成功行，不参与覆盖/单位/价格判断。

## 9. 最小下一步

1. US：单独定位现有yfinance TLS/source错误，不调整SSL校验、不自动切换新provider、不把失败解释为需要付费。当前US取数路径未恢复前不做Score/Engine。
2. HK：真实有限取数已经证明可达，不需要重新把“无生产Daily接入”误报为“供应商不能提供”。但仍需要针对历史candlestick端点的单位、turnover金额/币种及调整语义证据。
3. 在官方确定的拆股/分红窗口取得有限原始/调整后数据，并建立动作→价格/volume映射。数据未取得或规则不明就保持BLOCKED，不能从三只相等的价格序列推导普遍公式。
4. 定义未来输入冻结时的本地可用时间和数据引用；历史source vintage无法追溯时，明确retrospective/PARTIAL边界，不允许回填历史available_at。

本轮不创建Universe、不解锁Daily production dataset、不修改archive/QuoteService/Evidence Policy。报告完成不意味着Momentum implementation-ready。

## 10. 验证边界

- 真实只读数据请求与环境复验已执行；没有fixture行情或合成事件。
- 只检查数据结构/日期/元数据，不运行backend/frontend测试、build或Engine。
- 源码参考：[历史适配](../../backend/app/data_providers/historical.py)、[既有Longbridge机制](../../backend/app/plugins/longbridge/provider.py)、[未闭合数量契约](../../backend/app/plugins/longbridge/quantity.py)、[前阶段报告](hk-us-momentum-input-contract-validation-v1.md)。
- 文档收尾检查：内容、敏感信息、链接与空白；无Git暂存/commit/push。本轮未解决原有main远端同步待办。
