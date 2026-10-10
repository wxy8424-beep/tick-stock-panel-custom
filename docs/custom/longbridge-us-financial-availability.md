# Longbridge US financial availability diagnostics

2026-10-10；起点 main/cdabbeccae898cbd9a26af1a3352ac8e318e9416；SDK 5.2.0。

## 实测结论与证据边界

当前 FundamentalContext 正常，financial_report 方法存在；AAPL.US / NVDA.US
实际进入SDK并返回 FinancialReports.list dict，BS/CF/IS、USD，adapter成功。
候选行数分别129 / 138（按statement/currency/fiscal year/period/source period分组，非原始账户数）。
700.HK同一路径126候选行、HKD；600519.SH合法空dict、0候选行，EMPTY。
本次请求成功是当前availability证据；历史探针仅留下笼统错误分类，不能追溯证明此前究竟是
认证、权限、context还是API异常，更不能声称用户凭证发生改变。

首轮快速对照请求的HK/CN曾返回OpenApiException code429002；
[官方错误码](https://open.longbridge.com/zh-CN/docs/error-codes)明确为API限流。
新smoke固定四标的，每次间隔3秒，无自动重试；四请求均成功。没有用限流伪装EMPTY或权限错误。

本机SDK另有us_financial_overview(symbol, report)、us_financial_statement(symbol, kind, report)、
us_key_financial_metrics(symbol, report)；公开stub注明这些独立方法需要US token。
本轮没有调用独立US端点，也没有把其token要求套用到实际成功的financial_report。
不重查fp_end单位，不解锁financial dataset、不写盘；period_end转换与公告日期逻辑未改。
US声明由过时UNAVAILABLE修正为CONTRACT_BLOCKED，reason=report_period_timestamp_unit_unverified。
此声明表示已有真实上游数据但mandatory period_end契约未满足，不保证任意账号均有权限。
HK仍CONTRACT_BLOCKED，CN代表标的仍EMPTY。九项quantity blocker与realtime完全保持。

## 失败层及固定内部诊断

| 层/情况 | 既有contract status | 固定reason |
| --- | --- | --- |
| SDK无法import | unavailable | sdk_missing |
| context初始化失败 | unavailable | financial_context_unavailable，或更明确认证/网络分类 |
| 实际context没有可调用financial_report | unsupported | sdk_method_unavailable |
| 认证401003/403201/403203 | unavailable | financial_authentication_unavailable |
| IP403205/明确permission文本 | unavailable | financial_permission_denied |
| 明确entitlement文本 | unavailable | financial_market_entitlement_unavailable |
| 明确unsupported market文本 | unavailable | financial_market_unavailable |
| 官方429001/429002 | unavailable | financial_rate_limited |
| 连接异常 | unavailable | financial_network_unavailable |
| 未明确类别的OpenApiException | unavailable | financial_upstream_error |
| 其他SDK请求异常 | unavailable | financial_sdk_exception |
| 请求成功、合法空report | empty | representative_financial_response_empty |
| 有数据、required period_end未证明 | contract_blocked | report_period_timestamp_unit_unverified |
| adapter失败 | contract_blocked | financial_response_shape_mismatch，diagnostic financial_parse_error |

不用新公共状态枚举；SDK_UNSUPPORTED是语义描述，沿用现有unsupported状态，只针对实际method缺失。
context/SDK缺失不声称请求已发送。entered_sdk只证明进入SDK调用，不证明HTTP送达；
返回真实response或upstream错误码才有更强证据。诊断区分context/method/request/adapter。
成功返回diagnostic upstream_available；不是SUPPORTED。
探针不更新声明、不覆写用户设置，不调用其他源，不记录异常全文。
错误码仅输出有限范围int；异常类仅白名单；message仅用于内部固定分类，不向前端或日志透传。
row_count为候选映射行数，adapter出错为null，不伪造0。

## 验证入口

backend: `uv run --frozen python -m app.plugins.longbridge.financial_availability_smoke`。
只读FundamentalContext，复用现有provider context/认证/lock，结束释放context引用。
PASS表示固定四标的可诊断且未出现adapter错误，不代表数据集被启用或单位得到证明。
输出symbol/market/context/request/response shape/candidate row count/固定reason和状态，
不输出token、原始SDK异常、报表值、账户、Authorization或真实凭证。
现有settings已支持contract_blocked及对应中文reason，无前端/API/schema修改，frontend测试/build不适用。

## 最终验证

- Mock targeted150 PASS，新增30项；覆盖缺SDK/method、context/认证/权限/限流/API/网络、
  EMPTY、adapter错误、period_end阻塞、脱敏与context复用、quantity/realtime保持。
- 完整backend2802 passed / 6 skipped / 0 failed，216历史warnings；本次Python Ruff0 violations。
- 真实只读availability smoke四标的PASS，US/HK upstream_available但contract_blocked，CN EMPTY。
- 11候选文件敏感扫描：3项本机凭证匹配0违规；完整diff与diff --check PASS。
- 未修改前端、公共API/schema，frontend tests/build不适用；未使用交易context或交易接口。
