# Strategy Research Framework v1

独立入口 `app.services.strategy_research`，不注册到生产 StrategyEngine，不触发订单、定时任务、实盘或自动调仓。新增服务是只读历史研究容器，复用 Factor Registry / FactorScoringEngine / PortfolioBuilder；不修改已有因子、组合、组合分析、实验或 Provider/capability 契约。

## 定义、执行和保存

`StrategyDefinition` 保存 strategy_id、name、universe、factors、portfolio_rules、rebalance_frequency，以及评分方法、语义模式、历史价格口径与 created_at。因子参数/分量/方向通过现有 scorer、registry 和 engine 校验，组合只支持 top_n / equal。

`StrategyResearchStore(data_dir).save_definition(definition)` 原子保存不可覆写定义。同 ID 相同定义可重试，不同定义必须使用新 ID。

`store.execute(strategy_id, history_repository, session_dates=..., history_start=...)` 用已有 `DailyHistory.get_daily_asset` 计算并追加研究结果，包含定义快照、execution_status、events 和 result_summary。未知 ID 或非法日期在写结果前失败。仓库读取失败保存脱敏 blocker，不保存原始异常或文件路径。

`get_definition(id)` 和 `get_results(id, limit=20)` 使用 SQLite mode=ro；空库查询不会创建文件。独立存储位置为 `data/user_data/research_strategies.sqlite3`，运行库不提交 Git，不修改 Snapshot Archive schema 或实验数据库。

## 日期、缺失与复现边界

- 调用方必须提供已核验、严格递增且不重复的交易日期列表（最多 1000 个），历史起点不得晚于第一日。v1 不生成或验证市场日历，不推测休市日；跨市场需调用方选择有效的共同日期。
- daily 每个给定日期创建事件；weekly 按 ISO 年/周，monthly 按年月，取给定区间内每周期首个提供的日期。区间从周期中间开始也只取首个提供日期，不补区间外交易日。
- 事件在日期对应收盘因子可计算后生成，属于收盘后候选提案，不能解释为该日开盘可执行的仓位。历史查询最多到事件日，不请求未来价格。
- 任何股票/因子缺数据、预热不足或读取失败，该整个事件 blocked，保留因素值和固定原因，不静默缩小 universe。成功事件调用既有组合构造，稳定排序/等权保持不变。
- 空股票池/空日历为 empty；全成功为 completed，混合为 partial，全阻塞为 blocked。没有收益评估：returns=null、returns_status=not_evaluated_v1，绝不填零或虚构回测收益。
- 固定定义、日期、模式和历史输入可复现相同结果。结果保留评分值和候选组合；v1 不冻结外部历史库，不保证日后修订数据重跑相同，也不解决历史 PIT、汇率、幸存者偏差或调整口径问题。
- 候选 portfolio_id 由 strategy_id + 事件日期稳定生成，识别策略事件槽位；不同执行的候选内容可不同，SQLite result id 才区分追加执行。rebalance events 仅记录提案，不生成交易数量或真实成交。

## 验证范围

覆盖固定输入候选/权重、频率分组、严格日期、预热与缺失阻塞、脱敏错误、空输入、注册参数与兼容模式、定义不可覆写、结果追加和只读查询。已有 backtest/screener 不迁移，无前端、broker 或预测能力变更。
