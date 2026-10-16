# Longbridge HK/US Momentum Production Input Evidence & Read-only Field Mapping Audit v1

审计日期：2026-10-16（Asia/Shanghai）。审计起点：main / `93b92b8c4276194e03eb070b58f5b2780fd8aa96`。

## 1. Executive Summary

**SUPPLIER CONFIRMATION REQUIRED；HK/US Production Momentum Input 仍 BLOCKED。**

本轮只新增本报告，不修改任何生产代码、冻结模型、公式或 Gate。开始时 Engine/Input Gate 的九个计划文件仍未提交，不能把任务背景的“已推送”当作实际 Git 状态。保留已有候选实现，并按本轮明确授权单独收尾，再提交本报告；此前 no-commit 的文档描述是其阶段历史记录。

已有六证券、两种模式、每模式73根 Daily 的真实读取支持 API 可读性；不能证明数量尺度、split-only、源端 finality 或历史 PIT。四项核心 blocker 本轮均未升级。Calendar exact identity 可复用；这不认证供应商 Daily 发布语义。正式 Universe/成员历史仍未闭合。

没有新 Longbridge 请求、生产数据库写入、provider/QuoteService/Archive 变化、Universe/生产 Momentum producer、API/frontend 或生产执行。没有寻找替代凭证，也没有读取秘密配置。下文 mapping 是证据要求和现有 typed 字段之间的映射审计，不是已经上线的 Historical adapter。

## 2. Evidence hierarchy

P0：官方 API/SDK 文档及锁定 SDK 5.2.0 源码；P1：官方类型、示例、changelog；P2：项目既有真实只读报告与隔离测试；P3：第三方只能背景，本轮不用于解除 blocker。

| ID | 官方材料（本轮核验） | 可支持的范围 |
|---|---|---|
| O1 | [Historical Candlesticks](https://open.longbridge.com/docs/quote/pull/history-candlestick) | 请求、响应及历史能力；未给出本轮要求的完整源语义 |
| O2 | [Definition](https://open.longbridge.com/docs/quote/objects) | period/adjustment/board 等词典 |
| O3 | [Static Info](https://open.longbridge.com/docs/quote/pull/static) | exchange/currency/lot_size/board/支持的衍生品信息 |
| O4 | [Overnight Eligible Securities](https://open.longbridge.com/docs/quote/security/security_list) | 专用 API 文档为 US/Overnight 资格集合 |
| O5 | [CLI security-list](https://open.longbridge.com/docs/cli/market-data/security-list) | CLI 声称多市场清单；不替代5.2.0端点合同与完整性证明 |
| O6 | [Quotes](https://open.longbridge.com/docs/quote/pull/quote) | 当前 trade_status；不能推为历史 membership/status |
| O7 | [Candlestick push](https://open.longbridge.com/zh-HK/docs/quote/push/candlestick) | Realtime/Confirmed 推送周期边界，与历史读取分开 |
| S1 | [Python context.rs @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/python/src/quote/context.rs) | by_date/by_offset/static_info/security_list 绑定 |
| S2 | [Python types.rs @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/python/src/quote/types.rs) | Candlestick、AdjustType、Security、SecurityBoard、PushCandlestick |
| S3 | [Python time.rs @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/python/src/time.rs) | Python 时间转换 |
| S4 | [Rust context.rs @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/rust/src/quote/context.rs) | 请求编码、security_list HTTP 路由及 category 参数 |
| S5 | [Rust types.rs @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/rust/src/quote/types.rs) | Decimal/volume/epoch 反序列化 |
| S6 | [CHANGELOG @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/CHANGELOG.md) | 版本背景，不提供历史数据 vintage 保证 |
| S7 | [python/Cargo.toml @v5.2.0](https://raw.githubusercontent.com/longbridge/openapi/v5.2.0/python/Cargo.toml) | 许可 MIT OR Apache-2.0；不是行情使用授权 |

本地 metadata 再核验为 longbridge **5.2.0**；对照 `backend/.venv/Lib/site-packages/longbridge/openapi.pyi`。只使用官方 `longbridge/openapi / v5.2.0`，未用 master 推断安装版本；未取得并声称 tag commit SHA。**Code copied: NO**，无新依赖。公开滚动文档与专用端点描述不一致时保留疑点，不选择更宽松解释。

## 3. Historical Daily API capability

O1/S1/S4：业务指令27；`history_candlesticks_by_date(symbol, period, adjust_type, start, end, trade_sessions)` 以及 by_offset 存在。Daily 为 `Period.Day`；模式为 `NoAdjust` / `ForwardAdjust`。请求身份必须外部保留，SDK candle 列表没有逐行 symbol。

O1/S2/S5：OHLC、volume、turnover、timestamp、trade_session 存在。Decimal 价格/金额与整型数量的结构已证明。Rust candle 解析 OHLC/turnover 时存在解析失败落默认值行为：数值存在或为零不能证明原始字段有效；未来需独立校验并保留解析证据，本轮不写 parser。

P2：HK/US 六样本真实可读，范围见第14节；不是全市场授权或覆盖保证。当前 `backend/app/plugins/longbridge/provider.py` 的 manifest 仍为 realtime，`backend/app/data_providers/historical.py` 的 research 路径不等于已上线 Longbridge production Daily。没有用 yfinance 补证。

## 4. Volume semantics

O1/S2 仅确证 volume 字段，未闭合端点级 shares/board lots/其他单位。HK board lot、碎股范围；US 成交范围；split/reverse split 后数量是否重述；其他行动及 adjustment 对数量的影响，均 **UNKNOWN**。不能从整数值、lot_size 或两模式样本相等反推。

| Contract | HK | US |
|---|---|---|
| 数量字段可读取 | PROVEN（既有样本） | PROVEN（既有样本） |
| 精确单位与行动后跨日可比性 | BLOCKED | BLOCKED |
| 跨证券/窗口可比性 | 未证明 | 未证明 |
| VR20 eligibility | **NO / BLOCKED** | **NO / BLOCKED** |

比例消去单位的数学性质不足以证明21个session同尺度。不存在 fallback 到 turnover/绝对量/盘中量的授权。

## 5. Turnover semantics

O1/S2：turnover 是与 volume 独立的金额字段，不是 turnover_rate；历史 candle 无独立 amount/value 字段。具体币种、数量级、交易覆盖与公司行动重述规则仍未闭合。O3 当前证券 currency 可作为候选元数据，但不能单独认证历史金额口径。

未来可分别保存 volume/turnover 及各自证明；不允许反算 quantity 或把金额当 VR20 分母。当前金额语义 **PARTIAL**，严格生产金额输入 **BLOCKED**。

## 6. Adjustment semantics

O2/S1/S2：`NoAdjust`（Actual）和 `ForwardAdjust`（Adjust forward）是实际支持的模式。未发现独立 backward 或 split-only 开关。保留 vendor 标签，不将 Actual 扩写成已认证的 as-traded/PIT，不把 forward 扩写成 split-only 或 total-return。

| Corporate action | HK OHLC / volume / turnover | US OHLC / volume / turnover |
|---|---|---|
| split | UNKNOWN / UNKNOWN / UNKNOWN | UNKNOWN / UNKNOWN / UNKNOWN |
| reverse split / consolidation | UNKNOWN / UNKNOWN / UNKNOWN | UNKNOWN / UNKNOWN / UNKNOWN |
| stock dividend / bonus | UNKNOWN / UNKNOWN / UNKNOWN | UNKNOWN / UNKNOWN / UNKNOWN |
| cash dividend | UNKNOWN / UNKNOWN / UNKNOWN | UNKNOWN / UNKNOWN / UNKNOWN |
| rights issue | UNKNOWN / UNKNOWN / UNKNOWN | UNKNOWN / UNKNOWN / UNKNOWN |
| special distribution / spin-off | UNKNOWN / UNKNOWN / UNKNOWN | UNKNOWN / UNKNOWN / UNKNOWN |

矩阵针对两个模式各自的具体算法、锚点、重述与事件顺序；未知不表示供应商没有公司行动数据。一次请求选择一个模式支持结构一致性，但不足以证明四个价格均满足目标 split-only 数学基准。两次不同模式读取亦无源版本原子一致性证明。

## 7. split-only feasibility

没有官方充分证据证明某模式严格等于 `split_adjusted_price_only`，也没有经核验的拆股开/现金分红关组合。不得自行去分红、重建因子或按样本差异猜公司行动。

**price_basis = BLOCKED**。纯价格指标的阻断来自自身价格/finality/PIT要求，不是被 volume blocker 连带阻断；本轮不能冻结 price-only production contract。

## 8. Daily finality

S2 的 historical Candlestick 不暴露 final/confirmed/revision 字段；PushCandlestick 的 is_confirmed 和 O7 的周期结束推送语义不能移用为 historical 不再修订保证。S5 的内部 open_updated 也不是源端 FINAL。

缺少HK/US各自盘中返回 provisional 政策、收盘后定版 SLA、竞价/延长时段归属、half-day 发布和迟到成交/更正重述规则。过去日期加完整日历只证明session已过去，不证明某源版本已最终定版。

**finality = PARTIAL，生产 gate 仍 BLOCKED**。10月13日返回有P2证据，10月14日不在既有73根窗口内，没有本轮新响应；不声称已经验证14日数据。等待下一个session边界可作未来保守规则候选，但无官方保证其充分，不在本轮实施。

## 9. PIT / vintage

S1/S2及O1所审请求/响应没有历史 as-of/vintage 选择或首次发布时间、available_at、revision timestamp/id、源snapshot版本。结论仅限这些接口，不断言供应商所有产品均不存在该能力。

S3 明确使用 `from_timestamp(epoch, None)`，SDK 5.2.0的Python绑定返回宿主本地 naive datetime。它是 candle 时间表达，不是 UTC、源发布或历史可得时间。不能直接 `.replace(tzinfo=UTC)`，也不能把当前 fetched_at、SDK版本或市场午夜标签当 vintage。

`available_at=null`、`source_vintage=null` 保持合法缺证据状态，**strict PIT BLOCKED**。现在读取的 retrospective observation 与历史D时已可得是不同声明。未来从真实接收开始冻结只能证明此后系统持有版本，不能补造过去 availability。本轮无 ledger 或生产DB写入。

## 10. HK instrument eligibility

O3/S2 支持 symbol/name/exchange/currency/lot_size/board。HKEquity、HKWarrant、HKPreIPO 等粗分类不完整覆盖 common stock/ETF/REIT/preferred/CBBC/rights 的排他资格；stock_derivatives 是支持的衍生品，不等于该证券自身类型。名称和数值代码不能代替分类。

O4 专用 API 为 US/Overnight，O5 CLI 则列多市场；5.2.0虽接受 Market参数，不能据此证明HK完整目录。**HK eligibility证据 PARTIAL，正式Universe BLOCKED**：缺完整分母、稳定身份/alias、精细类型、有效期和历史 membership/vintage。没有实际拉清单或创建Universe。

## 11. US instrument eligibility

S2 的 Security只有symbol与多语言名称，SecurityListCategory只有Overnight；O4不是完整US security master。当前项目 `get_realtime_universe('US')` 将 security_list 结果投影成symbol，未提供排他instrument证据、完整性或历史成员版本。

USMain/USPink等board不足以分清普通股、ADR、ETF、preferred/REIT；O6 当前 trade_status不是历史上市/停牌/退市membership。**US eligibility PARTIAL、正式Universe BLOCKED**。当前currency不证明历史整窗currency一致；目录/watchlist/动态候选/UI集合仍各守边界。

## 12. Calendar identity

本轮内存调用 `TradingCalendarContract.from_canonical`，未注册/写Store或修改定义。单一事实源仍为 `backend/app/market_calendar.py`，exact contract位于 `backend/app/services/evidence_execution.py`。

| Market | ID / version | SHA-256 | Coverage / regular windows |
|---|---|---|---|
| HK | hk-cash-equity-official / 2026-v1 | `945fbd11e669fc27d1c76712969871a7151d854da1547f6c05fd71a4fa733b91` | 2026-01-01..12-31；Asia/Hong_Kong 09:30–12:00 /13:00–16:00 |
| US | us-cash-equity-official / 2026-v1 | `cfb976ea41ff8037ab0dd5225f061dcb960976cd404bcd10eae2bb74a1084d76` | 同年；America/New_York 09:30–16:00 |

holidays/half-days/early-close/segmented-session及既有边界冻结在artifact内。HK closing-auction窗口也在artifact中，不能把regular-window末端自动当供应商Daily最终发布时间。coverage外BLOCKED、不选latest、不以最近bar跳session。**Calendar身份 READY，不代表源finality READY**。

## 13. Field mapping table

N列指未来归一化目标，目前没有生产Longbridge Daily adapter。G=`MomentumDailyInput`；S=`MomentumSnapshotRecord`/新版本候选。S不存每个OHLC原值；历史窗口由input_references追踪，不虚构不存在的Snapshot字段。nullable描述缺证据容器，非Gate允许READY。

| Longbridge来源 → N | G → S / metric | Unit / definition / adjustment | Timezone / nullable | Evidence / status / blocker |
|---|---|---|---|---|
| candle.close → close | G.close → S.close；change/连续涨/returns/breakout/sigma | price；vendor mode未等于split-only | 非时间；容器可null，评分输入不可缺 | O1/S2/P2；结构PROVEN，basis BLOCKED |
| candle.high → high | G.high → input refs；breakout/high_break | price；需与close完全同basis | 非时间；可null→非READY | 同上；不得混复权 |
| candle.low → low | G.low → input refs；OHLC合法性 | price，同basis | 非时间；可null→非READY | O1/S2；结构PROVEN，basis BLOCKED |
| candle.open → open | G.open → input refs；OHLC合法性 | price，同basis | 非时间；可null→非READY | O1/S2；结构PROVEN，basis BLOCKED |
| candle.volume → volume | G.volume/unit/semantics/reference → S.volume/unit；VR20 | quantity unit/CA尺度未知 | 非时间；null合法但Gate拒绝 | O1/S2；volume_unit未知，BLOCKED |
| candle.turnover → turnover | G.turnover → S.turnover（候选保留待实现映射）；不用于VR20 | 独立trade value，非rate，币种/调整未知 | 非时间；optional | O1/S2；字段PROVEN，金额合同PARTIAL |
| static_info.currency → currency | G.currency；S无独立currency槽，留input refs | trading currency，非历史金额保证 | 非时间；null→quantity gate不通过 | O3；metadata PARTIAL，需有效期/同版本证明 |
| candle.timestamp＋明确转换 → trading_date | G.trading_date → S.trading_date | session label，非publication | 市场日期；不得直接取宿主date | S3/P2；既有样本对齐PROVEN，生产归一化未实现 |
| candle.timestamp → vendor_candle_time | 不直接赋G.timestamp/S.session_timestamp | 原SDK host-local naive；不是session close | 保留转换来源，不能冒UTC；未证时null | S3；转换行为PROVEN，未来需显式适配 |
| exact Calendar＋D → session_close | G.timestamp → S.session_timestamp | 冻结日历的session锚点，不是vendor发布时间 | aware UTC；与vendor原time分开 | 本地Calendar READY；不解除finality |
| 请求symbol / Market上下文 → identity | G.symbol/market → S.symbol/market | 请求身份关联，不凭display name猜 | 非时间；required | S1；HK alias须显式验证，不静默改写 |
| 审计时明确来源 → source/source_version | G.source/version/input_reference → S.source/provider/input_references | SDK5.2.0是客户端版本，非源vintage | 非时间；缺证据→非READY | 本地模型；生产版本/来源引用待定义 |
| request.adjust_type → adjustment_method | G.adjustment_method/version/reference/price_basis → S.adjustment_method/price_basis | 保留vendor mode；不得填SPLIT_ONLY | 非时间；可null→BLOCKED | O2/S2；split-only BLOCKED |
| 无对应返回字段 → source_vintage/revision | G.source_vintage/vintage_reference → S.source_vintage/source_revision | 未知保持null，不用SDK版本替代 | 非时间；可null，PIT不能READY | O1/S2；BLOCKED |
| 无对应返回字段 → available_at | G.available_at/availability_reference；S.available_at是派生artifact可得时间，非自动等于源bar可得时间 | 需独立首次availability证据及cutoff | aware UTC或null；不能用fetched_at替代 | O1/S3；BLOCKED |
| 本次成功读取时刻 → fetched_at | G.fetched_at；S.generated_at是计算生成时间，stored_at是Store时间 | 系统观测，非历史源availability | aware UTC；optional | 本次无新读取；P2历史观测已记录 |
| 无historical final flag → finality | G.bar_final/source/reference/verified_at → metric evidence/blockers | Push confirmed不可跨接口填充 | verified_at需aware，未知保留null | O7/S2；PARTIAL→Gate BLOCKED |
| 项目artifact → calendar_id/version/hash | G与S exact三字段 | 不是SDK last_updated/latest | 非时间；required | 本地artifact READY；coverage严格 |
| static_info.board/目录 → instrument/Universe | G.instrument_type＋显式Universe → S exact universe三字段 | board非普通股认证，目录非冻结Universe | membership有效与available分别证明 | O3/O4/S2；eligibility PARTIAL，Universe BLOCKED |

**实现映射限制**：现有Gate保存原rows/receipt，当前Engine projection保留OHLCV/turnover等Daily证据；Engine candidate并未自动把所有原始字段投影到S的展示槽。本轮不补写这些槽，也不把声明可保存当作生产映射完成。Snapshot available_at需区分派生结果生成时可得与原始历史bar曾何时可得，不能据前者关闭PIT。

## 14. Real sample evidence

P2只复用 [Longbridge Semantics Closure](longbridge-historical-semantics-closure-v1.md) 的真实观察：2026-10-15 09:44:28.174–09:44:29.826上海；参数窗口2026-07-01..10-13、Period.Day、TradeSessions.Intraday，两种adjustment分别读取。

| Symbol | Market | 实际date range | NoAdjust / ForwardAdjust | 证据边界 |
|---|---|---|---|---|
| 700.HK | HK | 2026-07-02..10-13 | 73 / 73 | 数值/日期结构，不证明单位、finality、PIT |
| 9988.HK | HK | 同上 | 73 / 73 | 同上 |
| 3690.HK | HK | 同上 | 73 / 73 | 同上 |
| AAPL.US | US | 2026-07-01..10-13 | 73 / 73 | 同上；模式价格差异非行动类型证明 |
| NVDA.US | US | 同上 | 73 / 73 | 同上 |
| MSFT.US | US | 同上 | 73 / 73 | 同上 |

共876根，既有报告记录有序/唯一、窗口内实际session对齐、有效OHLC和非负turnover；六只两模式volume相同不能推广为数量不调整。本轮没有原始数据DB读取或新样本响应，没有10月14日读取证据，也不重新认证旧报告中的数值。

本轮仅检查进程环境的凭证是否存在：项目使用的三项LONGBRIDGE凭证均不在当前进程环境；未查找/读取.env、凭证Store或其他账号，未实例化QuoteContext。不能据此断言宿主其他runtime未配置，也不能宣称账号历史权限失败。**新真实只读请求：NO；生产数据库写入：NO。** 复核测试仅使用隔离临时fixture数据库，不属于生产证据。

## 15. Current blockers

1. HK/US historical数量单位、范围、split/consolidation重述及可比性未证明。
2. vendor模式到split-only的严格映射及全OHLC行动算法未证明。
3. historical Daily最终发布时间、provisional与修订策略未证明。
4. historical available_at/vintage/revision及as-of证据未提供。
5. 正式HK/US目录完整性、精细instrument资格、历史membership/vintage未证明；API/CLI范围差异待澄清。
6. SDK naive时间需要未来明确适配，不能直接进入aware UTC Gate。
7. 生产Input Contract尚未安装；canonical Gate v1明确production_enabled=false，仅synthetic完整fixture可READY。官方证据补齐也不自动启用该Gate。

## 16. READY / PARTIAL / BLOCKED matrix

| Capability | HK | US | 本轮状态变化 |
|---|---|---|---|
| Daily SDK/API形状及既有固定样本可读 | PROVEN（限定范围） | PROVEN（限定范围） | 无升级 |
| exact Calendar artifact | READY | READY | 原能力复核 |
| instrument metadata候选字段 | PARTIAL | PARTIAL | 澄清边界，非Universe解除 |
| volume/VR20 | BLOCKED | BLOCKED | 无升级 |
| adjustment选择能力 / split-only basis | PARTIAL / BLOCKED | PARTIAL / BLOCKED | 无升级 |
| source Daily finality | PARTIAL | PARTIAL | 无升级，严格Gate仍BLOCKED |
| historical PIT/vintage | BLOCKED | BLOCKED | 无升级 |
| 正式Universe/历史membership | BLOCKED | BLOCKED | 无升级 |
| price-based indicators生产输入 | BLOCKED | BLOCKED | 各自basis/finality/PIT不足 |
| Technical Score production execution | BLOCKED | BLOCKED | 数学定义已闭合不等于输入通过 |

五个Calculation/Profile与Gate hash本轮内存复核均与既有候选文档一致；不更新任何旧canonical内容、Snapshot/Universe identity或记录。

## 17. Exact next closure requirements

**唯一推荐动作：取得并归档Longbridge官方对既有供应商问题的带版本/日期回复，同时澄清security_list范围和类型证据。** 不开启生产Engine、接源或全市场请求。

现有 [Vendor Evidence Closure](longbridge-historical-vendor-evidence-closure-v1.md) 的10条问题继续有效；需可核验答复覆盖：

- HK/US historical volume的单位、交易范围，board lot/碎股与各类公司行动重述；adjust_type是否改变volume；turnover币种/尺度及调整规则。
- NoAdjust/ForwardAdjust在拆股/合股、现金与股票分红、rights、特殊分配中的全OHLC算法；哪种模式能严格排除现金分红而仅调整拆股，或明确不能。
- historical Daily在正常日/half-day收盘后的完成与最终定版时间、provisional、迟到更正/历史修订规则；不能只说明push confirmed。
- 是否有publication/available_at、revision/vintage/as-of；如不提供，strict historical PIT继续BLOCKED，产品模式变更须另行决定。
- SDK5.2.0 security_list在HK/US、category省略/Overnight下的实际保证；完整分母、下市记录、common stock/ADR/ETF/REIT/preferred/warrant/CBBC的权威分类、历史membership及其availability来源。

得到答复后先做证据重评及小范围只读一致性验证，再决定是否需要新的生产Input Contract/Gate版本；不能修改旧hash或自动解锁。Supplier reply仍pending，未发送邮件或支持请求。

本轮新增仅此文档；前期九文件的既有验收记录为577 related PASS、backend full4169 passed/6 skipped/1 xfailed，正常线程，无worker timing复现。本轮重新执行同组受影响测试：577 passed（18.22秒）；六个候选Python文件Ruff PASS。docs-only审计不重复无关frontend/full suite。五个Calculation/Profile及Gate hash内存复核一致，十文件敏感扫描/本地文档链接检查通过。

保留的九文件已单独形成 `4983ade7`（feat: add momentum engine and input gate）；没有重新实现或修改候选代码。本报告另行提交。实际push、完整SHA与独立远端核验以本轮收尾报告为准，不预先宣称远端成功。
