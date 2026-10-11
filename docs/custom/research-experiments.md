# Research Experiment Framework v1

显式、同步执行容器位于 `app.services.research_experiments`。没有新增自动任务、
HTTP API、UI、策略、交易或消费者迁移。Registry、Engine、语义模式及数据契约不变。

## 定义与结果

`ExperimentDefinition` 包含 experiment_id、name、description、symbols、factors、
parameters、date_range、created_at。未知字段、未知因子、重复证券/因子、非法周期、
无时区创建时间、倒置区间均拒绝。最多100个证券、7个已注册因子族，名称可忽略大小写，
periods键使用规范小写名。不在本阶段判断证券是否为普通股票；输入由用户明确指定，
Runner统一调用stock历史接口，不增加ETF/index分类或自动选股。

parameters只允许periods、mode、compatibility_backend、history_start、price_basis。
默认research/as_provided；backtest_compat必须显式选择polars或matrix。
history_start是调用者指定的额外预热起点，不推算交易日或自动补历史。

存储复用现有SQLite技术与SnapshotArchive的本地目录约定，但使用独立
`data/user_data/research_experiments.sqlite3`，不修改快照schema。
experiments保存不可覆盖的定义；experiment_runs保存每次执行独立run_id及结果。
定义在写入前重新验证并序列化，结果原子写入；数据库写入失败向调用者报错，不能
把未保存结果宣称成功。数据库是本地运行数据，不入Git。

## 使用

```python
from app.services.research_experiments import ExperimentDefinition, ExperimentStore, ExperimentRunner
from app.services.snapshot_archive import SnapshotArchive

# data_dir与repository由调用者提供：现有KlineRepository也供BacktestEngine使用。
store = ExperimentStore(data_dir)
definition = ExperimentDefinition(
    name="MA与RSI研究", symbols=["AAPL.US"], factors=["ma", "rsi"],
    parameters={"periods": {"ma": 20}},
    date_range={"start": "2026-01-01", "end": "2026-03-31"},
)
store.create(definition)
run = ExperimentRunner(store, repository, SnapshotArchive(data_dir)).execute(definition.experiment_id)
saved_definition = store.get_definition(definition.experiment_id)
saved_runs = store.get_results(definition.experiment_id, limit=20)
```

Registry验证因子并保存元数据版本快照；Engine.from_history直接复用回测基础仓库的
get_daily_asset接口，只读已有历史、不触发Provider补数据。SnapshotArchive可选，
只读取每个证券执行时最新快照及诊断作为上下文；它可能在研究日期范围外，
不是历史区间证据，不把实时价格拼造日线或给因子补OHLC/volume。

## 结果与失败

每个证券保存Engine序列化结果（含模式、预热与null语义）。空历史为empty，读取或
计算失败为failed；部分证券失败为partial，全部失败为failed，全部空为empty。
completed表示执行完成，可含空证券或预热null，不等于全部因子有效或策略有收益。
单证券失败不丢其它结果；诊断归档不可用不阻断因子执行。异常仅记录固定错误码，
不存储原始异常、凭证或traceback。不提供错误自动修复/重试。

查询只读打开数据库，缺失实验返回None/空列表，查询不会创建库；执行未知ID抛KeyError。
每次运行独立追加，查询按最新执行开始时间排序。v1不提供定义修改、删除、自动清理、
调参、IC/收益评估、数据冻结或跨版本重放保证；仓库历史变化可导致重复执行结果变化。
若将来需要回测评估，应另行复用BacktestEngine，不在本容器复制其交易/收益逻辑。
