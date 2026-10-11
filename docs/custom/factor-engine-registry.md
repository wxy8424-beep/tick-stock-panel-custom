# Factor Engine 只读元数据

现有 `app.factors.registry` 仍是元数据唯一入口。本阶段添加
`engine_factors()` 与 `get_engine_factor(name)`，描述 MA、EMA、MACD、RSI、
ROC、ATR、volatility 七类 Engine 请求，不把它们追加到历史列目录。
旧 `FactorSpec`、API、评分依赖、目录数量和顺序保持不变。

每条描述包括 name、category、description、parameters、supported_modes、version。
name 为小写规范名，查询忽略大小写；未知名称（包括具体输出列 `ma20`）返回
None。对象及嵌套参数不可变；`to_dict()` 返回独立、可 JSON 序列化的副本。
version=1 表示元数据版本，不表示计算定义有变化。

已注册族及模式从 Engine 的 `DEFAULT_FACTORS` 和 `CalculationMode` 读取；
说明文案集中在同一注册表，不保存计算代码。读取没有计算、数据查询、扩展同步、
写盘或动态注册副作用。没有新增 API 或迁移生产消费者。

参数遵循现有请求语义：period 默认 null，明确委托 `FactorRequest` 的默认周期，
具体周期约束仍由其 `definition()` 校验。MACD 没有可配置 period。
compatibility_backend 在 research 中为 null；backtest_compat 必须显式指定
polars 或 matrix。Registry 不代替请求校验，不复制周期白名单或计算实现。

新增因子族时，在 Engine 已真实支持后补充本模块描述并测试；不能仅注册元数据
就宣称具有计算能力。未修改 engine、backtest、screener、provider、capability
或 snapshot archive。
