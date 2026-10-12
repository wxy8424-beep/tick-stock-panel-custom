# Historical Strategy Research Integration v1

2026-10-12；基线 main/030299440807608e0aafb9c1a221c24fdf975336。

新增 `app.services.historical_strategy_research`：HistoricalResearchHistory 适配已存在的 DailyHistory/get_daily_asset，HistoricalStrategyResearch 组合已存在的 StrategyResearchRunner、FactorScoringEngine、PortfolioBuilder 与 PortfolioAnalytics。小范围 L3：现有研究执行只生成提案、不消费历史Provider或串联持有区间，需要新增明确入口；没有复制指标/构造/风险分析或生产回测引擎。Factor Engine、Portfolio Construction、Portfolio Analytics、Experiment Framework、Provider/capability均不修改。

## 显式执行

```python
result = strategy_store.execute_historical(
    strategy_id,
    session_dates=research_sessions,
    history_start=warmup_sessions[0],
    history_dates=complete_sessions,  # 完整预热和研究日历，由调用方核验
)
```

可注入 providers={"CN": provider, "US": provider} 做离线测试。默认按唯一市场使用既有 get_historical_provider，需先 `uv sync --frozen --extra historical`。不注册生产Provider，不启动后台请求或自动研究任务。旧 store.execute 的提案语义不变；新入口将定义、提案、事件、净值、收益、诊断追加到既有 strategy_results JSON，无数据库 schema 变化，旧结果仍可查询。

session_dates 必须为有序唯一 Date（最多1000），history_dates 为完整有序唯一预热/研究交易日网格（最多10000），首日=history_start、研究期间后缀必须完整等于session_dates。没有网格返回 complete_history_calendar_required；不根据星期补日期，不从报价推断缺日是休市/停牌。仅支持单一CN或US市场，币种必须来源真实提供且一致；不混市场/FX，也不接受HK。

## 时间、组合与收益模型

- 原 StrategyResearchRunner 根据定义的频率生成收盘后候选，不修改原筛选、评分或组合规则。
- 信号日 t 的候选，在提供的下一个交易日 t+1 **收盘**成为目标比例。新比例不能获得 t→t+1 的收益；原持有组合先获得边界日收益，再以同一净值切换比例。使用的是明确的理论收盘估值约定，不是证明可按该价格成交。
- 第一次生效前为显式现金阶段，零收益假设；任一必要历史缺失仍会阻塞整个评估，现金不能作为缺行情的fallback。区间内由未改的 PortfolioAnalytics 执行 buy-and-hold，不每日恢复等权，允许权重随价格漂移。
- 各区间归一化NAV按前一区间结束值衔接，不重新从1计收益。没有后续持有区间的末尾候选 deferred，不读取研究结束后的价格、不虚构持有收益。
- portfolio_value_series 为初始1的**归一化价格指数**，不是账户金额或经济总财富。daily_return 为相邻指数变化小数，首日null；summary 保存初末指数、价格总收益、日期数、应用事件数及来源币种。没有分红现金、费用、FX、成交量/股数、借贷或真实成交模拟，不宣称现金分红或股数公司行动已处理。

## 数据与 PIT 边界

每个信号查询截止自己的信号日期，估值查询截止该持有区间终点，任何请求都不超研究终点。适配器拒绝来源越界日期、重复/缺日、错误证券/市场/币种/调整方法、null/非有限/非正价、不合法OHLC及来源不可用/partial；不fill、不ffill、不缩小股票池。预热日期同样要求完整。缺数据时返回 blocker、空净值/收益和null总收益，不把不完整结果标成功。

历史源只请求 price_mode=raw，volume不进入因子或估值。CN基础 none可使用；US仅定义 price_basis=as_provided 可做来源价格探索，不能选raw冒充as-traded；显式US raw返回us_as_traded_raw_unavailable。qfq策略返回pit_adjusted_history_unavailable，不将当前复权价悄悄用于历史信号。

**当前不具备 point-in-time 能力。** 返回 pit.capable=false、state=not_established，记录 current_revision_history_not_pit、universe_survivorship_risk、publication_times_not_available；US额外记录历史拆股修订风险。即使查询截止t，今天获取的数据可能已被来源后续修订；Yahoo基础价格也可能含后来拆股调整。日期无越界不等于消除了这种隐式未来公司行动/修订影响，本框架不能保证历史可得性，结果不可用于声称严格PIT无偏策略收益。

同一次研究重复读取重叠证券日期时，比对来源/调整方法/币种/OHLC，若发生修订立即historical_revision_during_run阻塞。input_fingerprint为此次实际读取内容的SHA256，不含变化的fetch时刻；它只识别输入，不替代完整原数据冻结、可重放存档或来源版本。不同来源同模式也不保证经济调整含义完全等价。

## 验证与限制

测试完全mock已存在的HistoricalDailyResult，不依赖账号或网络。验证固定历史输入复现、日期顺序、信号延迟、buy-and-hold漂移、连续调仓净值、未来条目修改不影响此前结果、缺失/重复/越界/null/修订/错误阻塞、原Store提案执行与新结果共存、JSON保存查询、空输入和PIT声明。

下一阶段若需要PIT严格策略验证，仍须补真实历史可得时间、源数据冻结/版本、历史证券池、完整交易日历、拆股股数/分红现金等证据；不是修改warning即可解除。未接前端/API、真实交易、broker、定时自动调仓、高频或预测模型。
