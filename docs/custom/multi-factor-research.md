# Multi-Factor Research Layer v1

`app.factors.research_scoring.FactorScoringEngine` 是独立只读研究入口，不接入
生产strategy scoring、backtest、experiment framework，不保存或执行交易。
Registry负责族元数据，FactorRequest/Engine负责计算；不复制因子公式或改变语义。

## 使用

```python
from datetime import date
from app.factors.research_scoring import FactorScoringEngine, ScoringFactor

result = FactorScoringEngine().score(
    repository, ("AAPL.US", "NVDA.US"),
    (ScoringFactor("ma", 20, direction="high"),
     ScoringFactor("rsi", 14, direction="low")),
    as_of=date(2026, 3, 31), history_start=date(2026, 1, 1),
    method="rank",
)
```

as_of必须为共同评分日期，history_start由研究者显式指定用于预热，不推算交易日。
只读现有stock历史API；无当天记录则缺失，不用前一交易日冒充当天，日期/证券过滤
继承Engine.from_history。默认research，也可显式backtest_compat+polars/matrix。
price_basis仅传递既有Engine约定，不另行复权。最多100个证券、7个不同因子族。
MACD多输出必须选择macd_dif/macd_dea/macd_hist之一，不自动选择或额外加权。

## 分数定义（0到1）

- rank：有效值升序并列平均排名r，n>1时 `(r-1)/(n-1)`。
- normalization：min-max，`(x-min)/(max-min)`，不是z-score。
- direction=high保持上述结果，low为 `1-score`；方向不由Registry或财务含义猜测。
- 单一有效值或全部相同均为0.5中性分；无有效值时null。非有限值不参与评分。
- 每个因子等权，全部因子有分数才返回总分（算术平均），否则总分null。
  不填0、不按可用因子重新分配权重。

每股票返回原始因子值、分数、缺失原因、total_score与状态。顶层记录方法、日期、
模式、价格口径、输出列、方向、权重、Registry元数据版本、有效样本数量和min/max。
输入顺序保留，不自动筛选或排序股票。无证券返回empty；全不可评分unavailable；
部分可评分partial。单证券历史异常仅保留固定错误码，不泄露原异常或凭证。

跨市场会提示cross_market_no_currency_adjustment，不做FX转换或市场/行业中性化。
MA、ATR等价格尺度因子即使同市场也受名义价格影响；分数只是对用户选择的原始值
机械排序/缩放，不宣称经济可比性、预测能力或交易信号。volume不参与，不猜单位。

固定输入/模式/参数可复现且可JSON序列化，不附随机ID或运行时间。数据仓库变化
仍可能改变结果；v1不提供数据冻结、自动权重学习、AI预测、调参或收益评估。
