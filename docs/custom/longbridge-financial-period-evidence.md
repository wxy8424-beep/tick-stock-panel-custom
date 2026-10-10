# Longbridge financial period-end evidence chain

2026-10-10；基线 `9bae40b79bd5542a1b265a45e723a9985c6f8c92`；installed SDK 5.2.0。
后续当前US availability已重新验证为上游可用、CONTRACT_BLOCKED；下文US不可用是本阶段历史快照。
最新状态与失败分类见[US availability](longbridge-us-financial-availability.md)，不改变fp_end证据结论。
范围仅 financial 的 fp_end → period_end，数量证据矩阵及九项数量 blocker 不改。

## 完整证据链

| 环节 / 官方来源 | fp_end 相关事实 | 已证明 | 未证明 |
| --- | --- | --- | --- |
| [API FinancialValue schema](https://open.longbridge.com/zh-CN/docs/fundamental/fundamental/financial-report#financialvalue) | fp_end:string，optional，报告期结束时间戳 | 指向报告期而非公告日；wire schema 为string | epoch、秒/毫秒或其他编码、市场报告日期时区 |
| [v5.2.0 Rust FinancialReports](https://github.com/longbridge/openapi/blob/v5.2.0/rust/src/fundamental/types.rs) | list:serde_json::Value，注释说结构变化，原样保留JSON | SDK不是将嵌套fp_end解成Date/OffsetDateTime | 原始JSON中的日期单位；不能借别的时间字段转换器推断 |
| [v5.2.0 Python binding types](https://github.com/longbridge/openapi/blob/v5.2.0/python/src/fundamental/types.rs) | FinancialReports.list:JsonValue；From将v.list包装；JsonValue IntoPyObject 使用pythonize::pythonize | 嵌套JSON直接转Python dict/list/标量，无fp_end特定转换 | 不定义epoch单位或时区 |
| [v5.2.0 Python context](https://github.com/longbridge/openapi/blob/v5.2.0/python/src/fundamental/context.rs) | financial_report将symbol/kind/period交给ctx，转换响应对象 | 当前响应模型FinancialReports | 不增加日期定义 |
| installed openapi.pyi + [Python docs](https://longbridge.github.io/openapi/python/reference_all/#longbridge.openapi.FinancialReports) | FinancialReports.list:object，为raw nested financial data | Python公开对象与嵌套数据形状 | 没有fp_end日期类型/时间单位注释 |
| 同版本Rust USFinancialStatementPeriod / USKeyMetricItem | fp_end:String，fiscal-period end date；另有rpt_date:String | 财务期间日期与发表日期分离 | 独立US端点的编码未明，不能跨推HK financial_report |

Rust context.rs 网络读取未完成（普通连接超时），不把该文件视为已验证证据。
API官方当前文档示例虽有数字字符串，示例数值不是单位定义；不据长度、fromtimestamp结果、季度标签、
lot_size或第三方报表对照推断。也不能将别的端点中同名fp_end字段定义移植到此接口。
本次查阅未找到明确单位/编码及业务日期时区；不是宣称所有官方资料均无证据。

## 现有 adapter / contract

`FinancialReports.list → indicators → accounts → values.fp_end` 是当前HK映射路径。
`financial_candidates` 保留source_fp_end原值供内部候选审计，不生成period_end；Decimal金额路径不变。
`inspect_period_end` 只检查optional string wire类型，无数值解析、Unix/毫秒/年月日识别、时区或日期推算。
null/空串显示financial_period_end_missing；非string拒绝financial_period_end_type_invalid；有string仍为
report_period_timestamp_unit_unverified。脱敏探针只返回固定分类，不暴露原始值。
证据摘要明确semantic=report_period_end_timestamp，encoding/unit/timezone均unverified，conversion_performed=false。

正式项目合并历史要求symbol+period_end。内部readiness现在要求**严格YYYY-MM-DD**，拒绝compact ISO、
ISO week date、datetime和非法日期；即使候选标签可解析为合理日期也绝不作为source period_end。
announce_date始终null；generic EPS、YoY、ratio不新增映射，不补0、不按日期推公告、不声称PIT可用。
existing financial dataset仍未声明；既有settings generic renderer显示HK契约阻塞，无需修改前端组件或API schema。

## 市场矩阵

| 市场 | 当前响应 | 类型 / 来源 | 编码证据 | 转换 | Capability |
| --- | --- | --- | --- | --- | --- |
| HK | 700.HK有IS/BS/CF及HKD | 原始JSON嵌套fp_end字符串 | 单位/epoch/业务时区未证实 | 无，period_end=null | CONTRACT_BLOCKED |
| CN | 600519.SH此前/本轮空list | FinancialReports | 空响应不能证明编码 | 无 | EMPTY |
| US | 当前context/token不可用；方法存在 | 不拿HK响应猜US | 独立US端点str不证明单位 | 无 | UNAVAILABLE，非SDK_UNSUPPORTED |

## 只读诊断和解锁条件

backend运行 `uv run --frozen python -m app.plugins.longbridge.financial_period_smoke`。
只读FundamentalContext.financial_report，固定600519.SH/700.HK/AAPL.US/NVDA.US。
复用Provider认证、context、lock；只打印字段/类型/固定状态，异常原文和原始数据不打印。
不交易、不写业务数据、证券目录或正式financial Parquet；样本仅验证形状和parser。
smoke PASS表示本轮四个代表标的的预期只读状态得到验证，不表示HK已supported。

未来须取得**此endpoint/market**明确的epoch单位/编码及业务日期时区再实现显式转换。
不能仅证明seconds就假定UTC截日一定等于报告期末业务日期；异常输入应fail closed。
如有证据只覆盖HK，只局部声明；还须审查现有HK路由和currency消费契约，不能只移除一个blocker就虚报支持。

## 验证记录

- 最终完整后端回归2772 passed、6 skipped、0 failed（包含新增29项测试）。
- 定向120 PASS，包含新增29项period/type/timezone防误转换测试及既有financial/quantity/realtime回归。
- 真实financial_period_smoke PASS：CN EMPTY；HK IS/BS/CF、HKD、fp_end string，CONTRACT_BLOCKED；
  AAPL.US/NVDA.US当前context/token UNAVAILABLE（SDK方法存在）。未转换日期、未打印原始值或凭证。
- Ruff四个Python文件0 violations；现有settings状态渲染5 PASS。前端源码与API/schema未变，build不适用。
- 候选6文件敏感扫描PASS，3项本机凭证匹配0违规；diff --check PASS。
