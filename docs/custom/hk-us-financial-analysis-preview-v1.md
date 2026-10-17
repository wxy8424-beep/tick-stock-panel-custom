# HK/US 财务分析 Preview v1

## 基线、审计与范围

开发与验收基线为 main / a4440eaf030666a31f2a8e3348534b9d704a7bc9。续验收保留此前五个候选源码/fixture/测试文件，不重新设计或重写实现；本阶段没有后端、供应商、数据库或冻结契约变更。

实际入口为 `frontend/src/custom/financials/extension.tsx` 注册的 `/financials`，不是独立的 pages/Financials 路由。CN 原流程：

- capability matrix / capabilities 与 financial status 决定来源可用性，原不可用提示和数据源配置链接保留。
- `lib/useFinancials.ts` 通过既有 API 和 financials Query Keys 查询 status、metrics、income、balance-sheet、cash-flow、shares；同步调用 financialSync，更新状态和财务缓存。
- `StockFinancialSearch` 通过 instrument-search 查询代码/名称；`useLastStock('financials')` 在用户选股时保存 CN 最近查看证券。
- `StockFinancialDetail` 按 period_end 降序展示字段卡，分别标注 period_end 与 announce_date；原百分比是百分点，金额转换/每股值格式不变。
- `ReportHistoryPanel` 挂载时读取 AI 报告历史，支持查看/删除；AI 分析可以请求流并保存报告。同步、下载、搜索、历史与 AI 调用均属于实际生产路径，不被 Preview 使用。
- 原详情没有可直接复用的同频财务历史趋势图，因此 Preview 增加专用纯 SVG 趋势与对应数值表，不引入图表依赖，不改 CN 图表或报表组件。

采用最小 L3 接线：当前页面虽为源码扩展，但现有插槽没有整页市场隔离能力，L1 配置或 L2 局部插槽不能阻止生产 hooks 挂载。仅在原 Financials 导出入口包一层市场分流，原主体为 ChinaFinancials，向两种原 PageHeader 分支传入市场控件。新展示位于 custom/damon/financial-preview，不复制 CN 页面或建立第二个 API client/cache。上游升级复核点仅该入口、import 和 Header 接线。

## 文件

- `frontend/src/custom/financials/extension.tsx`：原页面最小市场接线。
- `frontend/src/custom/damon/financial-preview/contract.ts`：Preview 专用类型、字段定义及一致性校验，复用 IndexPreviewProvenance，不改变 Anomaly/Momentum/Provider schema。
- `frontend/src/custom/damon/financial-preview/Presentation.tsx`：只读概览、财报/估值/趋势/字段详情、声明与市场切换。
- `frontend/tests/fixtures/financial_preview/index.ts`：HK、US 独立固定合成财报，每次构造新对象。
- `frontend/src/pages/FinancialPreview.test.tsx`：新增12项前端测试。
- 本文档。

## 合成财报与时间/单位

HK 证券展示代码 0700.HK / 9988.HK，US 为 AAPL.US / MSFT.US。企业显示名称明确为“演示企业甲/乙（虚构财报）”；代码只是展示标识，不证明数值来自对应真实公司。没有复制 CN 数据、券商记录或其他页面 fixture。source=synthetic-fixture、status=PREVIEW、data_mode=preview、is_production=false、is_investment_signal=false，fixture_only/synthetic 为 true。

每个企业五份独立报告：2023/2024/2025 年度、2026Q1/2026Q2 单季度。年度 FULL_YEAR、季度 SINGLE_QUARTER；不是 YTD，不从半年或年度累计值拆季。资产、负债、权益为相应报告期末 PERIOD_END 余额，不与流量字段混淆。金额统一为百万 HKD 或百万 USD，不自动换汇或将单位套用真实公司财报。

固定交易日 2026-09-16；generated_at=2026-09-17T07:00:00Z，仅为样稿生成时间。年度公告/可得时间分别为次年4月15日08:00Z，Q1为2026-05-15T08:00:00Z、Q2为2026-08-15T08:00:00Z；这些均为合成时间，不是供应商发布/vintage 证据。乙企业 Q2 公告/可得时间与净利润缺失，保留 null + reason，不能用报告期、generated_at 或当前日期替代。

字段明确区分 SYNTHETIC_INPUT 与 DERIVED_SAMPLE：前者不是供应商原始字段。仅有以下确定性样稿派生，输入缺失则结果 null：

- FCF = 同期经营活动现金流 - 同期资本开支；capex 声明为正数流出。
- 净利率 = 同期净利润 / 同期营业收入 × 100，单位为百分点。

2024 年度经营现金流刻意缺失，FCF 同样缺失，图表不插值、不补零。READY 仅限定该样稿数值的展示状态，不代表真实财报质量、历史可得性或生产输入已就绪。

## 估值口径

估值单独绑定 FY2025 报告 ID/期末，使用固定样稿价格时点：HK 2026-09-16T08:00:00Z / US 2026-09-16T20:00:00Z。币种与报表一致，财报合成 available_at 早于价格时点；不随上方报告期选择而重新拼接，不声称 TTM 或真实同一时点估值。

每项保留 value、unit、currency、formula、input_source、inputs、price/price_at、report_id/financial_period、status/reason、evidence：

- PE：固定价 / FY2025 合成 EPS，非 TTM。
- PB：固定价 × 对应股数 / FY2025 期末权益。甲企业股数有明确样稿设定；乙企业缺少期末权益对应股数，BLOCKED/null，不借用当期股数或 EPS 加权股数。
- PS：固定样稿市值 / FY2025 全年营收，非 TTM。
- 股息率：观察期、分配口径和币种证据缺失，BLOCKED/null，不填0。
- 市值：固定价 × 明确合成当期股数（百万股）。
- EPS：FY2025 合成净利润（百万）/ 合成加权平均普通股数（百万股）；仅为简单样稿公式，不声称真实法定或稀释 EPS。该项不使用价格，price/price_at 为 null 并说明不适用。

这些是供界面验收的假设输入/公式，不建立真实价格与财务数据的可执行生产合约。

## 交互、趋势与质量

- URL market 支持 CN/HK/US，CN 默认；保留其他 query 参数，支持直接刷新和浏览器返回。
- 每次跨市场切换卸载旧页面树，清除该页证券选择、搜索、报告类型/期、报表页签、趋势指标和字段详情；回到某市场重新进入默认状态，不保留未提交 UI 草稿。CN 最近证券存储机制不变，但不把它读取为 HK/US 样稿选择。
- 搜索证券、选择公司、年度/季度和报告期筛选、三张报表切换、项目搜索、字段 evidence 详情均只读。无结果、Loading、Error 保留声明，不回退真实接口。
- 趋势可选营收、净利润、经营现金流、净利率；同一条图只使用同市场/公司/频率/单位，按 period_end 映射节点，缺失的相邻点不连线。数值表与图共用报告集合，日期一一对应。
- 财务观察仅描述性呈现和同口径逐项对照，不设置真实风险评级、阈值或投资信号。
- 所有数值有限，派生输入与资产负债恒等式一致；校验拒绝市场/币种混用、错误流量口径、非有限值、缺失却标 READY、无可得时间证明的有值价格估值和错误报告绑定。

页面声明始终在加载/错误/空态外：**演示财务数据｜非真实公司财报｜估值仅用于界面演示｜不构成投资建议**。

## 生产边界

HK/US 不挂载 CN financial status、搜索、报表、ReportHistoryPanel 或 useLastStock，不调用同步、下载、AI 分析、报告保存/删除、通知或持久化。现有同步与 AI 按钮在 Preview 明确禁用，不新增假操作按钮。原 CN 已发出的后台同步或全局 AI 任务不被 Preview 自动取消、改写或重新提交。

未修改 backend、Longbridge provider、QuoteService、Archive、Historical Provider、运行数据库、Momentum Engine/Producer/Calculation/Profile/Snapshot/Universe/Input Gate 或冻结生产契约。未读取真实 HK/US 财报/行情，不升级任何 supplier blocker；Volume/VR20、split-only、PIT/vintage 与正式 Universe 继续 BLOCKED，finality PARTIAL、corporate actions UNKNOWN。

## 验收结果

- 现有候选实现未重写、测试断言未削弱；本轮正常审批和测试执行成功，不代表未来审批传输永久恢复。
- 相关测试：FinancialPreview 12 + MarkdownRenderer 6，18 PASS。
- 完整前端：46文件 / 367 Vitest PASS。
- node:test：5 PASS。
- TypeScript / Vite build PASS；仅既有 Router future / chunk 大小提示，没有失败项。
- 六个计划文件的敏感扫描、diff whitespace 和范围审查 PASS；逐文件暂存后复核 staged 内容与已审查工作文件一致，不夹带运行数据或无关修改。
- CN 主体排除已审查市场接线后逐字等价；Preview 无 API/query/storage/current-clock 路径，声明与 fixture 隔离检查通过。
- 真实浏览器视觉验收 NOT RUN；单元测试和构建不等于浏览器视觉验收。

**本阶段完成的是财务分析页面 HK/US Preview，不代表 HK/US 真实财报、实时估值或财务风险模型已经接入生产。**
