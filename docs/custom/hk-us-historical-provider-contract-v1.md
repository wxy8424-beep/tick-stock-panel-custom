# HK/US Historical Data Provider Contract Closure v1

审计日期：2026-10-14（Asia/Shanghai）。
源码基线：`main / 3c6d4eff54e3012e9e5a39cf2eaff15392dd2056`。

**结论：供应方案建议已形成；生产输入契约仍 BLOCKED，不能进入 Momentum Engine 实现。**

Longbridge 为 HK/US 的条件性 Production candidate；当前 yfinance 路径维持 Research only；当前 CN Daily 路径 Reject for HK/US。Production candidate 不表示生产已接入、账号权限已全量验证或数据使用权已确认。

## 1. 范围与证据

本轮仅阅读实际源码、已安装 SDK、公开官方文档和上一阶段脱敏样本报告。没有新建 SDK context、读取凭证、调用历史/实时报价、重试 US 失败请求或写生产数据；没有安装依赖、变更 provider、计算 Score、生成 Ladder/Universe 或修改 policy。

既有证据：

- [Momentum Input Validation](hk-us-momentum-input-contract-validation-v1.md)：本地 HK/US Daily repository 覆盖均为 0；盘中 archive 不是 Daily OHLCV。
- [Historical Sample Provenance](hk-us-historical-sample-provenance-v1.md)：HK 三只各 73 根真实历史 bar；US 三只最近有限请求均未成功。本轮没有重新请求，不把此前观测当作当前 entitlement 复验。

状态区分：字段存在、请求成功、数据语义、历史可得性和可用于生产是五个不同判断。SDK/library license 也不等同于数据许可。

## 2. 实际 Provider 分层

### 2.1 Historical research factory

[historical.py](../../backend/app/data_providers/historical.py) 的 `get_historical_provider(market)` 明确是 research factory，不是 production registry：

| market | 实际返回 | 边界 |
| --- | --- | --- |
| CN | CNHistoricalProvider | BaoStock/AKShare 既有 CN Daily 路径 |
| US | YFinanceDailyProvider | 显式研究查询，不注册生产同步 |
| HK | ValueError | 当前没有已集成 HK Historical Daily adapter |

HK factory 不支持，不能推导 Longbridge vendor 没有 HK 历史能力。

`HISTORICAL_SCHEMA` 保留 raw OHLC、独立 adjusted OHLC、source_adjusted_close、两种 adjustment_method、volume、volume_unit、currency、source、fetched_at、observed_at、dividend、split。没有 source vintage 或 historical available_at；observed_at 当前写 null。

成功行的 fetched_at 是本次请求结束时间。返回 status=completed 也不能证明单位、PIT、split-only 或源定版；当前 material diagnostics 集合并不将所有语义 blocker 都升级为 fetch failure。

### 2.2 Production registry / plugins

- [registry.py](../../backend/app/data_providers/registry.py)：默认 TickFlow，存在 daily/adj_factor 能力；[TickFlowProvider](../../backend/app/data_providers/tickflow_provider.py) 当前 instruments 枚举 SH/SZ/BJ，日线使用 none 和北京时间归一化。没有经过验证的 HK/US Momentum 合同；泛化 daily=True 不构成跨市场证明。
- [Longbridge manifest](../../backend/app/plugins/longbridge/plugin.yaml) 只声明 realtime；[provider.py](../../backend/app/plugins/longbridge/provider.py) 没有生产 Daily dataset。已有 SDK history 方法不等于 production dataset 已启用。
- [Fuyao](../../backend/app/plugins/fuyao/provider.py) 和 [TdxQuant](../../backend/app/plugins/tdxquant/provider.py) 实现、数量归一化与说明均面向 A 股（包含股转手等规则）。当前没有验证过的 HK/US Daily 适配，不将这套单位与公司行动逻辑套到港美股。
- AKShare adapter 使用 stock_zh_a_hist，BaoStock adapter 亦只接受 CN；不因第三方库另有函数就宣称项目已有 HK/US 支持。
- custom loader 的 dataset 声明不足以证明市场适配；[contracts.py](../../backend/app/data_providers/contracts.py) 也区分 market capability 和 quantity contract。

## 3. Longbridge 历史接口合同

审阅已安装 SDK 5.2.0 的 `longbridge/openapi.pyi`，不是照搬当前网站可能新增的 SDK 功能。

实际可用签名：`history_candlesticks_by_date(symbol, period, adjust_type, start, end, trade_sessions)`；另有 offset/count 接口。目标为 `Period.Day`、显式日期边界及 `TradeSessions.Intraday`。

官方 [History Candlestick](https://open.longbridge.com/docs/quote/pull/history-candlestick) 提供 HK/US 日线查询、日期/偏移模式及调整选项；日期查询超过单次限制会截断，不能把一次结果视为无限历史覆盖。官方 [Quote Overview](https://open.longbridge.com/docs/quote/overview) 定义 ticker.region；例为 700.HK、AAPL.US。

| 输入要求 | SDK/公开合同 | 语义结论 |
| --- | --- | --- |
| Daily OHLC | Candlestick.open/high/low/close，Decimal | 字段满足结构要求；每证券覆盖须另证 |
| volume | Candlestick.volume，int | 有字段；HK/US shares/board-lots、拆股调整边界未闭合 |
| turnover | Candlestick.turnover，Decimal | 独立于 volume 和换手率；字段可读，币种/成交范围/历史一致性未完全证明 |
| timestamp | Candlestick.timestamp，datetime；API timestamp 为 epoch | HK 样本为交易日午夜标签，不能当收盘时刻或可得时间 |
| session | trade_session；请求指定 Intraday | 可限定常规时段；不等于 source 已最终定版 |
| adjustment | NoAdjust / ForwardAdjust | 有选项；未证明 ForwardAdjust=仅拆股复权，NoAdjust 亦需明确公司行动语义 |
| completed bar | 历史日期查询 + exact market calendar 可检查日期 | response 未提供逐 bar finality/publication/vintage 证明 |
| PIT | 本地可记录接收时刻 | 没有历史 available_at/source vintage；strict historical PIT BLOCKED |

枚举意义依据官方 [Definition](https://open.longbridge.com/docs/quote/objects)；它不足以证明复权公式。不能以 SDK 中新出现的其他 context 或其他端点替代当前已验证能力。

### 3.1 HK 真实证据与边界

上一阶段 700.HK、9988.HK、3690.HK 均获得 73 根，2026-07-02～2026-10-13，Day/Intraday，OHLC 有效，volume 均为正整数，turnover 有限非负，static metadata 为 SEHK/HKD。0700.HK→700.HK 是样本专属、经元数据与官方代码交叉核对的映射，不是通用去零算法。

NoAdjust 与 ForwardAdjust 在该窗口的 OHLC/volume 相同，不证明 split-only，也不证明期间没有公司行动。HKD 证券报价币种不自动证明 turnover 的端点币种/聚合范围。当前 [quantity.py](../../backend/app/plugins/longbridge/quantity.py) 仍标 daily=contract_blocked / candlestick_volume_unit_evidence_missing，本轮不放宽。

### 3.2 US 能力与权限

公开接口和本地 SDK 支持 US symbol/Day history；本轮没有执行 US Longbridge 历史请求。US 真实 Daily 覆盖、当前账号权限及单位仍 UNKNOWN，不能用 HK 成功或 US realtime 成功替代验证。

官方 overview 说明 OpenAPI 与 App/PC/Web 行情权限分离；历史接口另有行情权限和唯一证券额度说明。公开页面的分层描述不能用来推断当前账号必须购买哪种套餐。HK 三样本成功仅证明当时这几次读取可用，不证明全市场权限、未来额度或存储/再分发权。

## 4. Completed-session 与价格基准

目标 price basis 为 `split_adjusted_price_only`：价格需在一致拆股/合股尺度上比较，不能混入现金分红总回报处理；还需说明比较窗口、调整基准日、事件来源与版本。

HK/US 已有 immutable calendar 可用于 session 日期判断；它不提供 provider finality，也不证明收盘后哪一刻收到最终 bar。HK 午夜 timestamp 不含收市/竞价完成信息；US 必须保持 regular session 与盘前盘后分离。

下列推断均不成立：

- 请求截止昨天 → provider 当时已发布最终版本。
- raw/forward 相等 → 已满足拆股调整合同。
- 只用 NoAdjust → 跨拆股窗口可直接比较。
- 当前拉取成功 → 在历史 D 收盘后已知道相同数据。

**HK price_status=BLOCKED；US price_status=BLOCKED。** 缺少公司行动语义证明时，不开始调整实现。

## 5. yfinance 当前路径

实际安装 yfinance 1.7.0；来源标记 `yfinance.Ticker.history/yahoo`。项目 adapter 只接受 US，移除 .US 后校验 ticker；还检查 metadata 中 symbol、EQUITY、America/New_York、currency。没有港股映射，不支持所有 share-class 格式；不应扩大为任意 provider universe。

读取参数为 interval=1d、auto_adjust=False/True 分开请求、back_adjust=False、actions=True、repair=False、keepna=True、rounding=False、prepost=False。请求 end 为项目包含式上界加一天；raw 为空/失败会提前返回，不能假称 adjusted 已执行。

已安装 `yfinance/utils.py::auto_adjust` 使用 Adj Close / Close 比率调整 OHL，并以 Adj Close 作为 close；该函数不改 volume。这个算法不是“仅拆股复权”的证明；Yahoo source Close 的公司行动基准也不能仅由 auto_adjust=False 推导为真实历史成交原价。Dividends/Stock Splits 列若有返回会保留，但不构成完整、带历史可得性的事件账本。

项目明确 volume_unit=unknown；零量可能置 null；fetched_at 写入成功结果行，observed_at=null，没有 historical available_at 或 source vintage。两次 raw/adjusted 请求也不提供同一供应商版本的原子保证。

上一阶段 AAPL/NVDA 失败归类为 network_error/tls_error，MSFT 为 source_api_error 未细分，均 0 行；没有成功行 fetched_at/metadata。未证明 entitlement denial，也未证明符号永久不支持。本轮不重试、不改 SSL/proxy、不自动换源。

官方 [yfinance README](https://github.com/ranaroussi/yfinance) 将工具定位于研究/教育，提醒 Yahoo API 的个人使用边界，并要求另查实际数据使用条款。库的 Apache-2.0 不授予 Yahoo 数据生产分发许可。结论：**Research only；不选为本项目 Momentum 生产依赖。**

## 6. Volume / turnover 合同

VR20 目标为 `V_D / mean(V_(D-20), ..., V_(D-1))`，需要 21 个明确 completed sessions，分母不包含 D。此处只定义核验要求，不计算指标。

需证明同一 symbol 全窗口：数量单位、交易场所/时段覆盖、拆股前后 volume 是否追溯调整、缺失/停牌/零成交含义及修订规则一致。即使比例数学上可能约去绝对单位，也不能绕过跨日期尺度一致性验证。

报价币种不是成交量单位；lot_size 不是 candlestick.volume 单位证明；turnover 不能由 close×volume 伪造，也不能当作换手率。不能把 CN 股→手转换、ETF volume、期权 contracts 混入港美普通股窗口。

当前 HK/US 的 Momentum volume_status 均 BLOCKED。

## 7. License 与数据使用边界

| 组件 | 已安装版本 | 查到的代码许可 | 数据权利结论 |
| --- | --- | --- | --- |
| longbridge | 5.2.0 | wheel metadata 无 License/License-Expression；官方 Python README 声明 Apache-2.0 OR MIT | 安装版本许可归档待补齐；SDK 许可不代表行情权利 |
| yfinance | 1.7.0 | 安装 metadata / LICENSE.txt 为 Apache-2.0 | 按 Yahoo 数据条款另判；本项目仅研究 |
| akshare | 1.19.1 | MIT | 第三方来源权利独立；当前 adapter 仅 CN |
| baostock | 0.9.4 | metadata 为 BSD License（未据此推断具体 BSD 变体） | HK/US 当前不适用 |
| tdxaidata | 1.2.2 | License-Expression MIT | 账号/数据许可独立；当前适配面向 CN |
| tickflow | 0.1.25 | metadata MIT | 当前 HK/US 合同未验证，不能由代码许可推导 |
| Fuyao REST adapter | 项目 HEAD | 项目 MIT；未新增第三方 SDK | REST 服务数据条款/港美能力本轮未确认 |

Longbridge 代码许可来源：[官方 Python README](https://github.com/longbridge/openapi/blob/main/python/README.md)。当前网页不冒充安装包 5.2.0 的精确 release 归档；本轮没有复制代码。

官方开发文档链接的 [平台条款及 Schedule A](https://longbridge.com/sg/support/topics/us-trade/user-agreement) 区分市场数据使用与分发授权，并描述个人使用及第三方限制。该 SG 条款不是用户账户地区/协议已经核实的证明；缓存、内部分析、衍生展示及再分发是否获准须按实际签约主体和行情协议确认。本轮未确认用户合同、未购买或升级套餐。Production candidate 附带权利确认条件，不作已获许可结论。

## 8. Provider Matrix

PIT 列针对“在历史 D 时已知”的严格要求；不是指现在能否查询旧日期。

| provider | market | OHLC | volume | adjustment | PIT | production suitability |
| --- | --- | --- | --- | --- | --- | --- |
| Longbridge SDK history | HK | 真实三样本各73根；尚无生产 Daily adapter | 字段/正整数已证，单位/历史尺度 BLOCKED | NoAdjust/ForwardAdjust；split-only BLOCKED | historical available_at/vintage 缺失，BLOCKED | Production candidate，条件未闭合，NOT READY |
| Longbridge SDK history | US | 接口/SDK具备；当前账号 Daily 未实测 | 字段存在；市场语义 UNKNOWN | 同上；US事件窗口未验证 | BLOCKED | Production candidate，权限/数据/权利待证，NOT READY |
| YFinanceDailyProvider | US | 研究适配存在；最近三样本 TLS/API 失败 | unit=unknown | 分离 raw/auto-adjust；split-only 未证明 | fetched_at 有成功行实现；历史 PIT BLOCKED | Research only |
| 当前 yfinance adapter | HK | factory/adapter 不支持 | 不适用 | 不适用 | 不适用 | Reject for current HK route；不是断言库本身无HK能力 |
| AKShareDailyProvider / BaoStockDailyProvider | HK/US | 当前 adapter 仅 CN | CN 规则不可移植 | CN none/qfq 不可移植 | 港美未验证 | Reject for HK/US current adapters |
| TickFlow / Fuyao / TdxQuant 当前集成 | HK/US | 通用 daily 声明不证明港美可用 | 当前 CN 归一化不能复用为港美证明 | 港美未验证 | 港美未验证 | Reject as presently evidenced HK/US solution；不判断 vendor 全部产品能力 |

目前没有一项可标为 Momentum Production READY；本轮也没有新证据把任何 UNKNOWN 改成权限/付费阻塞。

## 9. 推荐方案与最小后续验证

1. **Production candidate：优先验证既有 Longbridge HK/US history。** 复用已安装 SDK 和当前来源边界；HK 有真实结构证据，US 仍需独立有限样本验证。这是选型建议，不是自动接入授权或 silent fallback。
2. **Research only：保留现有 US yfinance 路径。** 其连接故障单独诊断；即使恢复也不会自动解除单位、复权、PIT 或权利限制。
3. **Reject：将当前 CN-only 或市场语义未验证的集成直接用于 HK/US Momentum。** 不新增来源依赖，不把现有 CN 数据规则迁移过来。

进入后续 Provider 实现前，至少完成：

| Gate | 需要的证据 | 当前结论 |
| --- | --- | --- |
| 数量 | 官方端点/市场单位、session覆盖、拆股时volume行为；真实事件窗口交叉核验 | BLOCKED |
| price basis | 拆股/合股及现金分红各自如何影响 NoAdjust/ForwardAdjust；官方事件与数值对齐 | BLOCKED |
| final Daily | 交易日/竞价边界、发布和修订规则；不能只检查日期小于今天 | PARTIAL |
| US Longbridge 可达与权限 | 未来独立授权范围内的少量 Day 历史读取；固定错误分类，不推断付费 | UNKNOWN |
| historical PIT | 逐版本历史可得时间/归档；今天取得的数据不能回填成过去已知 | BLOCKED |
| 使用权 | 账户对应行情协议、缓存/本地分析/展示范围；安装版本许可归档 | PARTIAL |

未来首次观测并冻结数据，可以证明那次采集以后系统持有什么版本；不能逆向证明过去 D 的历史 PIT。若来源根本不提供 vintage，必须单独决定是否仅支持 prospective observation；不能在本阶段降低 strict PIT 条件。

**结案：Provider strategy recommendation COMPLETE；provider production contract NOT CLOSED；Momentum implementation BLOCKED。** 下一步先闭合 Longbridge 单位、调整和最终日线语义，再进行受限 US 读取与使用权核验，不写 Momentum Engine。

## 10. 本轮交付与检查

- 仅新增本报告；保留两个既有未跟踪审计文档，无业务代码、配置、runtime DB 修改。
- 未运行 backend/frontend tests、build 或 Ruff：本轮是文档/只读审计。
- 提交前检查在本任务不适用：按用户要求不 stage、不 commit、不 push；只进行文档敏感内容、链接及 whitespace 检查。
- 原 main 的远端升级收尾待办仍独立存在，不因本报告宣称同步成功。
