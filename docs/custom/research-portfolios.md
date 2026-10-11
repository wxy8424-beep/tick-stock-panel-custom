# Portfolio Construction Layer v1

`app.services.research_portfolios`提供PortfolioDefinition、PortfolioBuilder、PortfolioStore。
这是显式研究组合，不连接行情/交易接口，不计算持仓或收益，不发出订单、不自动调仓。
Factor Engine、Scoring Engine、Experiment Framework及Provider/Capability保持不变。

## 使用

```python
from app.services.research_portfolios import PortfolioDefinition, PortfolioBuilder, PortfolioStore

# factor_scores 是已有 FactorScoringEngine.score() 的返回值。
definition = PortfolioDefinition(
    name="Top 10研究组合", symbols=["AAPL.US", "NVDA.US", "SPY.US"],
    selection={"top_n": 10, "weighting": "equal"},
)
result = PortfolioBuilder().build(definition, factor_scores)  # 纯计算，不写盘
saved = PortfolioStore(data_dir).save(definition, factor_scores)  # 显式原子保存
```

输入必须是现有评分结果：0–1、equal_weight_complete_case、同一as_of日期，带
各因子值/得分和方向/权重/输出列信息。不重新打分或改变因子定义。
输入证券/因子重复、非有限或越界分数、分数与总分矛盾均拒绝。
缺失分数不填0；不可用记录必须保持null语义。未知诊断字段被过滤，不存储任意原始payload。

按总分降序选top_n（1–100），并列按symbol字典序，不依赖输入顺序或随机数。
仅在定义symbols范围选择；原评分样本集不同会提示score_universe_differs_from_portfolio，
不重新缩放其分数。有效证券不足top_n时全选有效证券，以实际入选数量k分配1/k。
无有效证券或空列表返回empty、selected_symbols=[]、weights={}，均分null。
等权在浮点容差内和为1，不强行给最后一只股票不同权重。权重表示研究组合比例，非
可交易股数/金额；不验证上市、停牌、流动性、币种或可成交性，不宣称可直接实盘使用。

结果含选中证券、权重、请求/有效/入选数量、所选总分及各因子值/得分均值、
每只排除证券的原因和经过字段白名单过滤的完整评分快照（含未选证券，方便审计）。
跨市场保留未做FX转换提示，不添加风险优化或行业中性化。

纯build固定输入可复现且不会改输入。持久化在独立
`data/user_data/research_portfolios.sqlite3`：portfolio_definitions保存不可覆盖定义，
portfolio_results追加结果；定义与结果同事务保存，失败不报告保存成功。
重复相同定义可追加结果；同ID不同定义拒绝，不覆盖历史。结果无随机字段或构造时间，
保存行ID只用于查询先后，不参与计算。created_at属于定义，需要固定定义才保证同一输入。

`get_definition(id)`及`get_results(id, limit=20)`只读打开数据库，缺失返回None/空列表，
查询不创建库。数据库属于本地运行数据，不入Git；容量清理/备份需另行安排。
没有新增API/UI、实验自动执行、风险优化、学习权重、ML或交易功能。
