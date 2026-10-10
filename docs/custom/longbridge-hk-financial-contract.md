# Longbridge HK Financial Contract Closure

基线：`0ec44bb`。范围仅财务契约与只读验证，数量单位 blocker 不变。

## 现有项目契约（不修改）

项目没有覆盖五张财务表的统一必填 Pydantic domain model。
Provider 按既有 `get_financials(table, symbols, latest_only)` 鸭子类型返回 Polars 表；
`financial_sync._fetch_table` 入口仅检查 symbol，不能据此认定正式 contract 满足。
历史累积 `_merge_report_history` 必须有非空 `symbol + period_end`；
前端 Financial*Record 类型要求 period_end 为 string，现有 fuyao 日期 adapter 输出 ISO 日期。
API 原样返回表行，分析器按 period_end 排序。不能把上游原始 timestamp 字符串当 ISO 日期。

| 项目字段 | 必填性 / 语义 | Longbridge 来源 | 判定 |
|---|---|---|---|
| symbol | 历史合并必填 | 请求标的 | 满足，高置信 |
| period_end | 历史合并必填；ISO 报告期末日期 | values.fp_end | 阻塞：官方只定义报告期结束时间戳，单位未确认 |
| announce_date | 表类型 optional/null；不等于报告期 | 未确认来源 | null；不能用于公告日/PIT 判断 |
| revenue / net_income | optional/null | OperatingRevenue / NetProfit（IS） | Decimal 候选，高置信 |
| total_assets / total_liabilities | optional/null | TotalAssets / TotalLiability（BS） | Decimal 候选，高置信 |
| net_operating_cash_flow | optional/null | NetOperateCashFlow（CF） | Decimal 候选，高置信 |
| net_investing_cash_flow | optional/null | NetInvestCashFlow（CF） | Decimal 候选，高置信 |
| net_financing_cash_flow | optional/null | NetFinanceCashFlow（CF） | Decimal 候选，高置信 |
| bps | metrics optional/null | BPS（BS） | 高置信源值；候选保留来源报表，尚不正式组装 metrics |
| basic_eps / diluted_eps；metrics eps_basic / eps_diluted | optional/null；明确 basic/diluted | generic EPS | 不映射，口径未确认 |
| yoy / ratio | optional；前端 pct 使用百分点 | 源字符串 | 不映射、不缩放，语义未确认 |
| currency | 现有类型没有强制要求；多币种金额必须可辨识 | indicator.currency | 原样保留，不按后缀猜 |
| report type / fiscal year | 项目按 income/balance_sheet/cash_flow 分表 | IS/BS/CF / values.year | 保留候选 statement/fiscal_year；period 标签不推导日期 |

前端金额格式器沿用 legacy 元/亿显示习惯，没有显式消费 currency；财务同步和 instruments 路径
也没有现成的 HK 专用路由入口。这些是现有隐式假设，不能以改标题/改全局 contract 的方式绕过。
缺失公告日的行可以存储，但不能声称是已验证的公告时点数据或支持 PIT 回测。

## 本阶段结论

HK **CONTRACT_BLOCKED**：mandatory period_end 不能安全满足。候选直接从源字符串解析 Decimal，
无 float round-trip；缺失金额为 None，无补零。保留 HKD（如果源返回其他币种，同样原样保留）。
不解析 period 标签，不猜 fp_end 秒/毫秒，不将 fp_end 冒充公告日。
financial dataset 不加入 config.datasets，不将候选写入正式 financials Parquet。

`probe_financial_contract(symbol)` 通过现有复用上下文只读调用 FundamentalContext.financial_report，
返回状态和字段摘要，不返回原始金额、日期样本、凭证或 SDK 异常文本，不自动改变静态 capability。
CN 代表证券真实空响应为 EMPTY；US 方法存在，当前上下文不可用为 UNAVAILABLE，
独立网络故障另归类 financial_network_unavailable，不按 429002 猜 rate limit。

官方依据：[Financial report](https://open.longbridge.com/zh-CN/docs/fundamental/fundamental/financial-report)。
字段定义不足以确认时间戳单位、EPS basic/diluted 或 yoy/ratio 缩放；样本一致性不替代契约。
