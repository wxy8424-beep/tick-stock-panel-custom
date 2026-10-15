# Longbridge Historical Vendor Evidence Contracts Closure v1

日期：2026-10-15，Asia/Shanghai。
当前仓库：`main / 551f2604473cd25916f29667bb71f29983277e15`。
生产代码仍为此前 `3c6d4eff` 对应实现；本次提交仅保存四份已有审计报告。
安装 SDK：Longbridge **5.2.0**；本轮 SDK 源码判断仅使用官方 **v5.2.0** tag。

**最终判断：D. SUPPLIER CONFIRMATION REQUIRED。不能冻结完整或 price-only Momentum production input contract。**

日线读取能力已证明，不能据此推定单位、调整算法、最终定版和历史可得时间。下文 UNKNOWN 是“本轮所审官方材料未证明”，不是断言供应商任何产品都没有该能力。

## 1. Phase 0：已有文档 Git closure

四份既有审计报告经敏感、链接、whitespace 和完整 staged review 后，单独形成提交：

- commit：`551f2604473cd25916f29667bb71f29983277e15`。
- message：`docs: audit HK US momentum data contracts`。
- 4 files / 1026 insertions，未包括生产代码、运行数据或本报告。
- `git push origin main` 实际成功；独立 `git ls-remote origin refs/heads/main` 返回相同 SHA。
- 当时 main up-to-date、working tree clean、staged empty。完成此检查后才开始本 Vendor Evidence 审计。

本轮按用户要求复用昨日 Skill 的检查点/串行 Git 收尾，不重做升级或测试，不通过额外连接器查询重新阻塞已有 Git 路径；未修改代理、SSL、认证、网络或权限配置。一次成功不代表传输故障永久修复。

本报告只保留在工作区，不自动 stage/commit/push。以下研究不调用真实行情、不接入 Provider、不写数据库、不建 Universe、不计算指标/Score。

## 2. Evidence sources 与优先级

按 A→B→C→D 查阅；搜索出现的第三方 SDK、博客和通用复权介绍不用于闭合合同。公开资料取阅日期均为本审计日期，在线文档可能比安装 SDK 新。

| ID / 优先级 | 官方来源 | 用途与证据边界 |
| --- | --- | --- |
| A1 | [Historical Candlesticks](https://open.longbridge.com/docs/quote/pull/history-candlestick) | 业务指令27、参数与响应字段；字段表无市场级数量单位或历史发布/修订信息 |
| A2 | [Definition](https://open.longbridge.com/docs/quote/objects) | Period.Day=1000、NoAdjust/ForwardAdjust、trade session；枚举不是公司行动公式 |
| A3 | [Candlesticks pull](https://open.longbridge.com/docs/quote/pull/candlestick) | 与 historical pull 区分；不能据另一端点的 latest 语义补充历史定版保证 |
| A4 | [K线 push](https://open.longbridge.com/zh-HK/docs/quote/push/candlestick) | Realtime/Confirmed 的推送周期边界；不是历史版本保证 |
| B1 | [Python quote/context.rs @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/python/src/quote/context.rs) | Python by_date/by_offset 向底层转交参数、返回列表 |
| B2 | [Python quote/types.rs @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/python/src/quote/types.rs) | Candlestick / AdjustType / PushCandlestick 类型 |
| B3 | [Rust quote/context.rs @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/rust/src/quote/context.rs) | 请求编码、业务命令与反序列化调用链 |
| B4 | [Rust quote/types.rs @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/rust/src/quote/types.rs) | OHLC/turnover 解析、volume 直映射、epoch 转换 |
| B5 | [Python time.rs @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/python/src/time.rs) | epoch → 宿主本地 naive datetime |
| C1 | [CHANGELOG @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/CHANGELOG.md) | 5.2.0发布日期2026-09-30；历史加入 push is_confirmed，不构成历史 finality SLA |
| C2 | [python/Cargo.toml @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/python/Cargo.toml) | MIT OR Apache-2.0 代码许可；不是行情授权 |
| D1 | [Quote FAQ](https://open.longbridge.com/docs/qa/broker) | 行情权限、请求限制、日切及 overnight；未给出本轮所需历史定版/单位/修订承诺 |

repo 为 `longbridge/openapi`，tag 为 `v5.2.0`；本轮公开 Git ref API 页面未取得可用内容，因此不填写未核实的 tag commit SHA。没有用 main/master/develop 的实现代替5.2.0，也没有复制代码、安装 SDK 或借其他框架作事实权威。

## 3. SDK 5.2.0 findings

本地 `backend/.venv/Lib/site-packages/longbridge/openapi.pyi` 与版本 metadata 再核验为5.2.0。

| 文件 / 符号 | 实际发现 | 不能推导 |
| --- | --- | --- |
| Python context.rs: history_candlesticks_by_date，约295～317行 | symbol、period、adjust_type、start/end、trade_sessions 转交底层；返回 List[Candlestick] | 客户端没有实现可核验的 split/dividend 调整算法 |
| Rust context.rs: history_candlesticks_by_date，约914～964行 | SecurityHistoryCandlestickRequest；QueryByDate；日期YYYYMMDD；统一 adjustment 参数；业务指令27 | 请求参数不是每条bar的版本/发布时间 |
| Rust context.rs: request，约203～210行 | Protobuf 请求编码和响应 decode | 传输 envelope 不是数据 vintage |
| Python types.rs: Candlestick，约635～655行 | OHLC/turnover 为 PyDecimal，volume=i64，timestamp=PyOffsetDateTimeWrapper，trade_session | 无 volume_unit、currency、action version、published_at、revision_id、final flag |
| Rust types.rs: Candlestick转换，约775～813行 | 价格与turnover解析为Decimal，失败可落默认数值；volume直接映射；epoch转OffsetDateTime | 零值不自动等于有效无成交；原样映射不证明单位 |
| Python types.rs: AdjustType，约253～262行 | NoAdjust / ForwardAdjust；本地pyi一致 | 没有单独 split-only、backward-adjust、total-return 开关 |
| Python time.rs，约45～51行 | from_timestamp(epoch, None)，返回宿主本地naive datetime | 不能直接附加UTC或当作market wall clock / available_at |
| Python time.rs，约18～35行 | 输入datetime按年月日时分秒构造值、assume_utc | offset调用还需独立核验时间输入语义；本次不实施适配 |
| PushCandlestick / Config push mode | push有is_confirmed，与historical Candlestick不同 | confirmed不能证明历史返回永不修订 |

OHLC 在同一个 candle、同一次请求的 adjustment mode 下返回，字段结构未显示分别选模式；这仅是结构一致性 PARTIAL，尚非“同一已证明 split-only 数学基准”的保证。raw/adjusted 分两次请求，也没有源版本原子一致性证明。

## 4. HK / US historical volume contract

| 必须确认的问题 | HK 官方端点证据 | US 官方端点证据 |
| --- | --- | --- |
| shares / board lots / contracts / provider-specific | UNKNOWN；当前仅定义为成交量 | UNKNOWN；当前仅定义为Volume |
| board lot / 碎股影响 | UNKNOWN；不能用static_info.lot_size替代定义 | 不把HK规则移植到US |
| split / consolidation后历史volume是否重述 | UNKNOWN | UNKNOWN |
| adjustment mode是否改变volume | UNKNOWN；样本相同不能推广 | UNKNOWN；样本相同不能推广 |
| 历史范围/交易范围是否一致 | UNKNOWN，包括竞价/碎股等 | UNKNOWN，包括场所/成交类型/延长时段边界 |
| 跨证券volume ratio可比性 | 未证明；需要单位/类型/时段/行动尺度和比较定义 | 同左 |
| 同证券VR20跨日可比性 | 未证明 | 未证明 |

虽然比例可在确定的同尺度条件下消去绝对单位，本轮尚未证明这些条件，不能据此放行。

独立金额字段为 **turnover**；历史 Candlestick 没有独立 amount/value/trade_value 字段或已证明 alias。中文字段说明将turnover与成交量分开，但其端点币种、数量级、复权/公司行动重述行为以及历史范围未闭合。证券当前报价币种不能替代逐端点金额合同；turnover也不是turnover_rate。不得通过 price×volume 或金额/价格反算补证。

**HK volume=BLOCKED；US volume=BLOCKED；两市场 VR20 eligibility=NO。** 现有quantity门控不改变。

## 5. Adjustment contract

| 模式 | 正式标签 | 本轮可确认 | split-only | cash-dividend / total-return-like | backward |
| --- | --- | --- | --- | --- | --- |
| NoAdjust / 0 | Actual / NoAdjust | 参数和模式存在；应保留vendor原标记 | UNKNOWN | UNKNOWN，不能据NoAdjust名义保证排除所有追溯行动处理 | 此模式不是独立backward选项 |
| ForwardAdjust / 1 | Adjust forward | 参数和模式存在 | UNKNOWN | UNKNOWN，不能据forward推定现金分红公式或再投资收益 | 此模式不是独立backward选项 |

没有找到可将某一模式严格、一一映射为目标 `split_adjusted_price_only` 的本轮官方材料。没有独立的“拆股调整开、现金分红调整关”选项证据。HK与US是否使用同一公式、调整基准日/锚点、复合事件顺序、舍入与重述范围均需确认。

**adjustment verdict=PARTIAL（选择能力已知、算法未知）；split-only price_basis=BLOCKED。** 不实现反向去分红、重建因子或把NoAdjust直接认定为事件当时真实成交价。

## 6. Corporate-action matrix

每格 UNKNOWN 指未找到历史candle模式对应的公式/重述规则；不是证券没有此类行动，也不是供应商一定不能提供事件。

| Action | HK NoAdjust OHLC / ForwardAdjust OHLC | US NoAdjust OHLC / ForwardAdjust OHLC | HK volume/turnover | US volume/turnover |
| --- | --- | --- | --- | --- |
| split | UNKNOWN / UNKNOWN | UNKNOWN / UNKNOWN | UNKNOWN | UNKNOWN |
| reverse split / consolidation | UNKNOWN / UNKNOWN | UNKNOWN / UNKNOWN | UNKNOWN | UNKNOWN |
| stock dividend / bonus shares | UNKNOWN / UNKNOWN | UNKNOWN / UNKNOWN | UNKNOWN | UNKNOWN |
| cash dividend | UNKNOWN / UNKNOWN | UNKNOWN / UNKNOWN | UNKNOWN | UNKNOWN |
| rights issue | UNKNOWN / UNKNOWN | UNKNOWN / UNKNOWN | UNKNOWN | UNKNOWN |
| special distribution / spin-off | UNKNOWN / UNKNOWN | UNKNOWN / UNKNOWN | UNKNOWN | UNKNOWN |

其他 SDK context 的 dividend/split/event 字段存在，不等于该事件与历史OHLCV调整算法、价格尺度和历史可得性的映射已经成立。通用投资教育文章和客户端图表说明亦不能替代具体 OpenAPI 历史端点合同。

**corporate-action verdict=BLOCKED。** 本轮未新增公司行动请求或扩大历史窗口，未从六样本差值反推事件或公式。

## 7. Daily finality

| 问题 | 本轮官方证据 / 判断 |
| --- | --- |
| 当日交易中historical Daily是否返回未完成bar | 未取得明确的端点级保证；latest/current date参数不等于finality证明，保持UNKNOWN |
| 收盘后多久最终定版 | 未找到HK/US分别的发布时点、延迟上限或SLA，UNKNOWN |
| final / confirmed flag | historical Candlestick无；push事件有confirmed，不能跨接口移用 |
| 盘后修订 / 迟到成交 / 错单更正 | 未取得不可修订保证或规则；不能宣称永不修订 |
| HK竞价、half-day、early-close | 项目calendar能识别边界，vendor历史发布/覆盖/定版映射未证 |
| US regular / extended / half-day | 请求能选Intraday/All；不能据此推定发布、盘后更正或最终close政策 |
| SDK release notes | 早期记录加入push is_confirmed及Daily订阅修复，没有历史Daily最终版保证 |

FAQ的Quote Change By Date Time属于报价日切说明，不能拿09:20/08:50等值当作历史Daily final时间。

未来可讨论“只在下一个已确认session边界后请求D”的保守 gate，但现有官方材料未保证等待这个边界就不会再修订。它只能减少当日未完成bar风险，不能独立闭合FINAL或PIT；本阶段不实现，不设任意分钟缓冲。

**bar_finality=PARTIAL**：过去session/日期对齐有既有证据，source FINAL保证仍不足，不能标READY。

## 8. Historical availability / revision / vintage

所审historical请求没有as_of/vintage/revision选择参数；响应/本地pyi字段没有：publication timestamp、available_at、revision timestamp、revision id、source snapshot version。

因此精确结论是：**当前所审接口未暴露这些证据，未找到可复现历史版本的官方替代合同；STRICT PIT=BLOCKED。** 不扩写为“Longbridge所有产品都绝对没有历史版本能力”，该问题留给供应商确认。

SDK candle timestamp只表示candle/session时间，并由5.2.0转为宿主本地naive；不是返回时间、源发布、历史availability或source vintage。SDK版本和取得时间均不是数据版本。

### 与retrospective模式的区别

可以定义未来的 **retrospective vendor-history observation**：只声明在某次真实fetched_at读到供应商当前历史结果，保留模式、请求范围、字段、接收时间和证据引用；不声明历史D当时已知道，不覆盖之前版本，不伪造available_at。

但目前不能把它命名为已获源保证的“retrospective completed-session FINAL production mode”。要做该模式仍需完整的价格基准、最终bar/修订与时区合同。只按日历排除当前交易日的研究观察不等于源端最终版；本轮不选择或实现一个降低标准的新产品模式。

## 9. 既有真实样本 consistency check

使用已提交的 [Semantics Closure](longbridge-historical-semantics-closure-v1.md) 中2026-10-15 09:44:28～09:44:29（上海）观察，不发新行情请求。

| market / symbols | 历史窗口 | 每只每模式bars | 对官方结构的支持 | 不足以证明 |
| --- | --- | --- | --- | --- |
| HK：700.HK / 9988.HK / 3690.HK | 2026-07-02～10-13 | 73，NoAdjust与ForwardAdjust各一组 | OHLC有效、volume正整数、turnover有限非负、日期匹配 | 具体单位、无公司行动、split-only、finality、历史PIT |
| US：AAPL.US / NVDA.US / MSFT.US | 2026-07-01～10-13 | 同上 | 同左；两模式价格有差异、volume相同 | 差异是何类行动、是否排除分红、跨行动volume规则 |

六证券两模式合计876根；样本是“与已知字段/模式一致”的有限观察，不是语义权威，不扩张为所有市场/证券/日期的单位或权限证明。

## 10. Momentum indicator eligibility

以下判断针对用户已要求的production输入合同，不是“拿任意数值能否套公式”。价格类按价格尺度、completed-bar和PIT独立判定，不以volume作为其阻断理由。

| 指标 | HK | US | 直接阻断原因 |
| --- | --- | --- | --- |
| consecutive_up_days | BLOCKED | BLOCKED | 跨行动一致close basis未证；finality/PIT缺口 |
| 3D return | BLOCKED | BLOCKED | 起止价格同一split-only basis未证；finality/PIT缺口 |
| 5D return | BLOCKED | BLOCKED | 同上 |
| 10D return | BLOCKED | BLOCKED | 同上 |
| B20 | BLOCKED | BLOCKED | 价格基准/finality/PIT；所审持久文档还未给该缩写唯一公式，不猜close/high边界 |
| B60 | BLOCKED | BLOCKED | 同上，且需完整实际session窗口 |
| HB20 | BLOCKED | BLOCKED | 价格基准/finality/PIT；不擅自定义high-break比较字段、等号与D是否排除 |
| HB60 | BLOCKED | BLOCKED | 同上 |
| volatility20 | BLOCKED | BLOCKED | 价格基准/finality/PIT；return类型、样本分母及是否年化还需显式公式 |
| VR20 | BLOCKED | BLOCKED | volume单位/范围/跨行动可比性、session/half-day处理、finality/PIT |

VR20的已记录输入形式为D的量除以前20个session均量，分母不包含D；本轮不计算。若将来价格基准和finality闭合，价格指标可独立重评，不必等待volume；本轮并无足够证据给price-only READY。PIT还需按最终选择的明确产品模式独立门控，不能被悄悄移除。

## 11. HK / US Provider Decision

| 项目 | HK Historical | US Historical |
| --- | --- | --- |
| OHLC接口/字段与有限读取 | PROVEN；生产价格基准PARTIAL | PROVEN；生产价格基准PARTIAL |
| volume | BLOCKED | BLOCKED |
| adjustment模式 / split-only | 模式PARTIAL；split-only BLOCKED | 同左 |
| finality | PARTIAL | PARTIAL |
| strict historical PIT | BLOCKED | BLOCKED |
| Decision（针对Momentum生产输入） | **BLOCKED** | **BLOCKED** |

本轮不用candidate掩盖最终门槛。可观察当前历史返回不等于RETROSPECTIVE_ONLY Momentum计算已经获批；也没有证据支持PRODUCTION_READY或PRODUCTION_WITH_LIMITATIONS。不能据官方材料不足直接断定必须更换来源。

## 12. Longbridge Vendor Questions

以下问题可直接提交供应商；本轮只拟好问题，**没有发送消息、创建Issue或联系支持**。请供应商逐HK/US普通股、history by_date/by_offset、Period.Day回答，并提供适用于SDK5.2.0所用服务的文档版本/日期。

1. For historical **Daily candlesticks**, what exact unit does `volume` use for HK equities and for US equities? Is it shares, board lots, contracts, or another unit? For HK, does it include odd lots, and does a board-lot-size change affect the historical series?
2. Under **NoAdjust** and **ForwardAdjust**, is historical volume restated after a split, reverse split/consolidation, or stock dividend? Please specify the event ratio, reference date, rounding, restated range, and whether both modes return the same volume by design.
3. What exactly does `turnover` measure for each market: currency and multiplier, included trade venues/types and sessions, and corporate-action adjustment/restatement policy? Is there any separately defined `amount`/`trade_value` alias for this endpoint?
4. Please define both adjustment modes for **all OHLC fields**, separately for HK and US. Which mode, if any, adjusts splits/consolidations but **excludes cash-dividend adjustment**? Does NoAdjust already include any historical split adjustment? Is there a backward-adjusted or total-return series available through a documented option?
5. Please provide the historical OHLC/volume/turnover treatment for split, consolidation, stock dividend, cash dividend, rights issue and special distribution/spin-off, including compound-event ordering, anchor date, precision and historical restatements.
6. Can a history query with a Daily period return the current incomplete session? At what documented point is D's Daily bar complete/final for HK and US, including HK closing auction, US extended hours, half-days and early closes? Is there a **historical-pull** final/confirmed indicator rather than only the push event flag?
7. Can a previously returned historical candle change due to late trades, corrections or corporate-action updates? What are the revision rules and maximum delay? Does querying after the next confirmed session boundary provide any finality guarantee?
8. Is historical candle `timestamp` a session date label, interval start or another timestamp for Daily bars? Please define market-timezone/date attribution, half-day behavior and the distinction from publication/availability time. We observed the Python5.2.0 binding returning host-local naive datetime.
9. Does any documented API expose the original publication time, revision time/id, data vintage, immutable source snapshot version, or an **as-of query** that reproduces values available at a past cutoff? If not, please explicitly distinguish supported retrospective history use from point-in-time historical use.
10. For a 21-session volume window, are unit, trading scope and split/consolidation treatment stable across sessions? What restrictions apply to comparing such ratios across HK/US securities or half-days? Please identify instrument categories needing different contracts.

一条“可以前复权”或“volume是成交量”的回答不足以解除以上P0；需要端点/市场/字段级的可归档官方说明。收到答复后更新证据矩阵，再决定是否做有限事件窗口一致性检查。未自动购买套餐、升级账号、换源或新增依赖。

## 13. 最终选择与交付状态

- **选择 D：SUPPLIER CONFIRMATION REQUIRED。**
- 不选择A：完整production输入未闭合。
- 不选择B：价格基准与finality仍未闭合，不能冻结price-only生产合同。
- C只描述当前最多能做原样retrospective研究观察，不代表已冻结任何Momentum计算合同。
- 不选择E：尚无证据证明必须换数据源；先取得供应商明确答复。

最小下一步：由用户向Longbridge官方支持提交上述问题，取得带版本/日期的答复后重评。继续保持生产代码、factory、archive、QuoteService、数据库与policy不变。

本轮没有新实时/历史请求、测试、Ruff或build；文档敏感/链接/whitespace/内容检查单独执行。四份旧报告已本地提交并远端验证；本报告按授权保持未跟踪、未暂存、未提交、未推送。
