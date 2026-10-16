# HK/US Market Environment Preview v1

## 现有能力审计与修改边界

基线：520da46631159950dc6902698f09be5b5a4b1bbd，main，工作区 clean。
市场环境入口 `frontend/src/pages/Regime.tsx`（`/regime`），读取 coverage/history/states/phases/mainline，通过 ECharts 与日历展示 A 股离线环境时序。
原页支持 1年/2年/全部/自定义范围、环境/情绪周期切换、时间轴选日、主线过滤、全量重算。
现有 MarketSwitcherBar 原为 CN-only；Index / Watchlist / Review 已有 URL 市场切换与独立 fixture 的 Preview 模式。
Dashboard 另有自己的数据契约与组件，不作为本页市场环境数据来源。

L3 最小接线：现有注册/插槽不能替换 `/regime` 的市场主体，故只在 Regime 增加市场外壳、原位 controls 和隐藏市场的自定义范围弹窗可见性控制；不复制原页。
其余文件放在 `custom/damon/environment-preview`、`tests/fixtures/environment_preview`、页面测试和本文档。
复用既有 provenance 类型、MarketSwitcherBar、卡片视觉、PageHeader、StockDataTable/useTableSort、格式化及 EmptyState/ErrorState。不新增 API、框架、依赖或查询缓存。
上游合并需复核 Regime 的外壳和原位工具条；原 CN 计算、查询、日期和事件处理保持不变。

## HK/US 专用 fixture

`frontend/tests/fixtures/environment_preview/index.ts` 是独立编写的数据源，不导入 Dashboard、Index、Review 或 CN 数据。
两市场分别维护展示集合，固定日期 2026-09-16 / 2026-09-15；生成时间固定 UTC，不依据系统日期或真实日历推断。
展示代码不充当 provider 身份，未请求 Longbridge。

- HK：恒生指数、恒生科技指数、国企指数。
- US：S&P 500、Nasdaq Composite、Dow Jones、Russell 2000。
- 每条指数附样稿点位、fraction 涨跌幅、预编写趋势、PREVIEW 状态、source 和 evidence。
- 市场总体状态显示市场、日期、Session、POST_CLOSE/CLOSED 固定演示状态；它们不表示当前市场正在开闭，也不证明已完成/最终日线。
- 宽度展示上涨/下跌/平盘数、上涨数量除以下跌数量的样稿比值与预编写状态。
- 强弱展示强势/弱势数、强势数量除以弱势数量的样稿比值、Breakout 数量；这些数值和比值预先给定，不定义阈值、扫描、指标或排名。
- Volume Spike 不提供统计，保持 null 并显示原因；每市场末条指数点位亦 null，不通过其他页面补齐。
- BULLISH/NEUTRAL/WEAK 是演示标签，不是环境分类公式或 Momentum Score。US 较早日期未编写结论，显示 UNAVAILABLE 和原因。

## Preview contract / 数据质量

envelope、日期记录和指数均带：status PREVIEW、source synthetic-fixture、data_mode preview、is_production false、is_investment_signal false、fixture_only true、synthetic true。
专用校验检查市场/日期一致性、唯一身份、固定格式时间、非有限值、非负整数计数、负比值、null 原因、missing_fields 与实际数值缺口一致；禁止把 available_at 填成已知生产可得时间。
null 显示破折号与原因，合法零值仍显示零；不把未知数据补成零。
数据质量区明确展示 trading_date、generated_at、available_at=null（历史可得时间未证明）、data_status、missing_fields、blockers、warnings、source 和 evidence。
趋势 UNAVAILABLE 也有独立解释，不从涨跌幅反推；环境结论缺失不调用 A 股或 Momentum 算法。

统一声明：**演示数据｜非生产行情｜不构成投资信号**。
样本统计不代表真实市场宽度或全市场覆盖，固定 Session 不意味着供应商 finality 已闭合。

## 交互与 CN 隔离

URL `market=CN|HK|US` 控制市场，缺省/未知值为 CN；保留其他查询参数与浏览器返回行为。直接刷新 HK/US 不挂载 CN 查询、图表或生产 API。
每个已访问市场保留自己的页面树和日期、搜索、缺失筛选、排序状态；HK/US 只读固定日期列表，无真实历史查询。
已访问 CN 保持既有查询观察器和页面交互状态；Preview 不启动、取消或改变原有重算。隐藏 CN 时不显示自定义范围弹窗，返回后状态保留。
HK/US 不提供生产重算、同步、配置写入或股票行情详情。加载、空数据、错误不会回退到 CN 或其他数据源。

## 验证范围

测试覆盖默认 CN 范围 query key、情绪周期与自定义天数状态、三市场切换、固定日期与独立状态、浏览器返回、HK3/US4 指数、fraction/零值/null 原因、排序/筛选、来源/证据、数据质量、禁用生产重算、空/错/加载态、fixture 可复现性和隔离。
直接 HK/US 监控查询、fetch、localStorage 写入及 CN 图表初始化，均不得调用。仅 fixture/mock 验证，不构成生产行情验收。

2026-10-16 验收：新增 12 项测试通过，市场环境/复盘/指数相关 33 项通过；完整前端 Vitest 40 个文件、296 项通过；独立 node:test 5 项通过；TypeScript / Vite build 通过。
原 CN 主体排除已审查的市场外壳、原位 controls 和隐藏弹窗可见性差异后逐字等价，敏感模式扫描及 diff check 通过。
仅保留既有 React Router future flags 提示和 Vite 大 chunk 警告；未做真实浏览器视觉截图验收，不能把 jsdom/build 当成该项验收。

## 生产限制保持

未改 backend、Longbridge provider/selection、QuoteService、Historical Provider、Snapshot Archive、生产数据库或冻结 Momentum Calculation/Profile/Snapshot/Universe 契约。
未创建真实 HK/US Universe、Momentum Producer、实时任务或投资信号。
Volume/VR20、split-only price basis、historical PIT/vintage 继续 BLOCKED，Daily finality PARTIAL，corporate actions UNKNOWN；供应商确认独立待跟进，不阻止前端 Preview 开发。

**本阶段完成的是市场环境 HK/US Preview，不代表真实 HK/US 市场环境统计已经接入生产。**
