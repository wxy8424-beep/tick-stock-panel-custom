# HK/US 异动监控 Preview v1

## 实际入口审计

基线 main / 39997b23d641f20e4dc30738aeed7b44c8fcf880，起始工作区 clean，独立 origin/main SHA 一致。
侧栏“异动监控”为 `custom/abnormal/extension.tsx` 注册的 `/abnormal`；`/anomalies` 是另一个“实时异动流”，消费生产 AnomalyEvent/交付游标/health/历史与市场证据，不能混为同一入口。
本次扩展 `/abnormal`，不改 `/anomalies` 或 AnomalyEvent schema，其既有测试继续回归。

CN 原页分竞价、盘中、偏移三页签：

- 竞价读取 auctionBenchmark，展示名单/采集状态。
- 盘中读取 abnormalIntraday(500)，共享 quoteStatus 控制轮询频率，原有涨停/炸板/翘板/新高/新低/放量、板块、ST、代码名称过滤和排序/候选导航不变。
- 偏移通过 abnormalOverview 读多日偏离结果，默认计算关闭；开关与上次结果由既有 storage 管理，过滤/日期/阈值与 CN 交易所规则保持原样。
- 真实副作用入口包括本页偏移计算开关/刷新、localStorage 上次结果、股票详情查询，以及跳监控中心设置告警规则；本页不直接提供生产确认/忽略按钮。

采用最小 L3：现有注册/插槽不能替换页内市场主体，只给原扩展加 URL 市场外壳、原位 MarketSwitcher 控件和隐藏市场股票弹窗保护，不复制原页或新建后端。
原 CN 主体、数据、算法和 handler 不重写。上游合并只需重点复核原扩展外壳、MarketSwitcher 及弹窗可见性接线。

## Preview 专用数据

文件 `frontend/tests/fixtures/abnormal_preview/index.ts` 独立编写 HK3 / US4 个样本，不导入其他页面 fixture，不将监控中心合成告警转成异动事件。
HK：0700.HK/9988.HK/3690.HK；US：AAPL.US/NVDA.US/MSFT.US/AMZN.US，仅为显示标识，不作 provider 请求。
复用现有纯展示 ANOMALY_TYPES / SEVERITY_LABELS：rapid_price_move、intraday_breakout、volatility_expansion。
这些类别在 Preview 仅为固定显示名称，不证明相应生产能力启用；不实现跳空/突破/波动或量价检测，不套用 A 股涨停、竞价、累计偏离公式。
不新增生产事件类型；专用 DTO 以 sample_id、sample_state 标记，不能当 AnomalyEvent、MonitorRule 或 AlertEvent 使用。

统一 provenance：status PREVIEW、source synthetic-fixture、data_mode preview、is_production false、is_investment_signal false、fixture_only true、synthetic true。
固定 trading_date 2026-09-16、generated_at 2026-09-17T03:00:00Z；样本事件时间为固定 UTC，不使用系统时钟、不宣称经真实 regular-session gate 验证。
部分样本 change_pct=null，另有时间/严重程度/状态缺失样本；附 missing_fields 和原因，不以零、当前时间或默认正常状态代替。真实零值正常显示。
样例状态 OBSERVATION_SAMPLE / BLOCKED_SAMPLE / null，均明确“非真实事件”，不推断 production readiness。
校验限定 Preview 标识、精确市场/交易日、唯一样本、既有类型/等级、有限涨跌幅、UTC样稿时间、null 缺失原因和 evidence/blocker/warning。

## 展示、交互与隔离

复用已有 Index / Review / Environment / Monitor 的 URL 市场、访问后保留独立页面树及 provenance；复用 PageHeader、MarketSwitcherBar、StockDataTable/useTableSort、fmtPct、EmptyState/ErrorState。
默认 CN，明确 HK/US 进入独立页面；保留其他 URL 参数、刷新与浏览器返回。
已访问 CN 保留原 tab/筛选/详情本地状态与既有观察器；直接 HK/US 不挂 CN，不调用任何真实查询或 API、不读取或写入 storage。
隐藏 CN 时不显示股票详情弹窗；返回 CN 才恢复显示。
HK/US 搜索名称/代码、类型/严重程度筛选、按事件时间/涨跌幅/等级排序。仅对非空值排序，null 始终排末；类型/等级/详情及筛选集合不跨市场。
详情展示名称/市场/类型、条件说明、固定时间、状态、source、evidence、缺失字段/reasons 与 blockers/warnings；不读取 Historical/Market/Intelligence 证据服务，不发实时提醒。
原告警规则入口在 Preview 禁用且无真实 handler；不增设无业务意义的确认/忽略/通知按钮。空/错/加载态也保留非生产声明，不回退生产接口。

统一声明：**演示数据｜非生产行情｜不构成真实异动事件或投资信号**。

## 生产边界

未修改 provider、QuoteService、Snapshot Archive、Historical Provider、Detector、AnomalyEvent、真实告警/通知处理、生产数据库或冻结 Momentum/Input Gate 契约。
不新增 API、真实 HK/US anomaly producer、行情请求、Universe 或投资信号。
Volume/VR20、split-only、PIT/vintage、正式 Universe 等继续 BLOCKED，Daily finality PARTIAL，corporate actions UNKNOWN。波动扩张样本也不得解除相应数据限制。
供应商确认继续独立跟进，不阻塞前端 Preview 工作。

## 验收边界

仅隔离 fixture/mock 验证：默认 CN/三页签及原刷新/查询/开关默认关闭、市场切换/返回/URL、固定时间、独立样本、类型/等级/搜索/排序、null 原因、证据/详情、声明、禁用操作及无生产调用。
真实浏览器视觉验收未执行；构建与 jsdom 不代表真实浏览器验收，也不构成真实行情验证。

2026-10-17：新增12项测试通过（含同证券多个样本按 sample_id 分离），前期相关33项回归通过，最终完整前端42文件/320项 Vitest 通过，独立 node:test 5项通过，TypeScript/Vite build 通过。
原 CN 主体排除已审查的市场外壳、控件注入、股票弹窗可见性差异后逐字等价；敏感模式扫描、Preview API/存储/producer/通知隔离及 diff check 通过。
仅保留既有 React Router future flags 提示和 Vite 大 chunk 警告，无本轮类型或构建错误。

**本阶段完成的是异动监控页面 HK/US Preview，不代表 HK/US 真实异动检测、实时行情或投资信号已经接入生产。**
