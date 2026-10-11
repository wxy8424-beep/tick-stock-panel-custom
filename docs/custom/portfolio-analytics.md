# Portfolio Analytics Layer v1

`app.services.portfolio_analytics.PortfolioAnalytics.analyze()`读取现有组合结果和
DailyHistory/get_daily_asset(stock)历史，不修改组合构造、Factor、Experiment或Backtest。
没有交易、调仓、实盘、自动权重优化、数据写盘或Provider补数据。

```python
result = PortfolioAnalytics().analyze(
    portfolio_result, repository, start=start, end=end,
    expected_dates=verified_trading_dates,
    periods_per_year=252, annual_risk_free_rate=0.0,
)
```

expected_dates必须由调用者明确提供研究区间预期交易日期，来源需要调用者验证。
本模块不推断休市/缺日，不自动使用工作日序列；缺少日期网格则expected_dates_unknown。
组合评分as_of不得晚于首个价格日期，避免用未来选股结果分析过去；不模拟同日成交。
混合市场缺FX统一口径时blocked，不假设人民币/港币/美元可混合。

价格口径为仓库as_provided，不自动转换复权、不计分红、费用或FX。因此total_return
是本研究净值累计价格收益，不是包含分红的总回报。不宣称真实可成交的策略收益。
positions为研究构成，不是实盘持仓：保留初始权重、首末价格、标的价格收益与末期漂移权重。
factor_score_summary复制现有组合摘要，不重新计算评分。

初始净值1，`NAV(t)=sum(w_i * P_i(t)/P_i(0))`。始终固定初始分配，不每日重置权重。
daily_return首行null（基准日），其余为`NAV(t)/NAV(t-1)-1`，均为小数制。
annualized_return使用实际收益观测数量m：`(NAV末/NAV初)^(periods_per_year/m)-1`。
252是显式研究年化假设，不是对每个市场实际年交易天数的声明。
volatility为收益样本标准差（ddof=1）乘sqrt(periods_per_year)。max_drawdown为
`min(NAV/累计峰值-1)`，负数小数制。Sharpe使用日收益均值减日无风险收益后除以
样本标准差并年化；日无风险收益由`(1+annual_risk_free_rate)^(1/periods_per_year)-1`转换。

缺标的历史、日期不齐/冲突、重复日期、无效/非正价格、数据读取异常：整体blocked，
指标null/空，不前向填充、不删坏日、不把缺数据证券剔除并重新配权。异常只输出固定码。
少于两个价格日期无法分析；只有一个收益观测可计算累计收益/回撤/年化，但风险null、
status=partial并记录blocker。零波动可真实输出0，Sharpe未定义则null，不能伪造0或inf。
数值溢出指标保持null并记录blocker；空组合status=empty。固定输入无随机数/运行时字段，
可JSON序列化；可复现依赖历史数据和调用者日期网格不变，不提供数据冻结或存储。
