# HK/US 持仓提醒 Preview v1

## 现有页面审计与接线

基线 main / 46217cde8581ef5e5d8510b3d4cdb7fb87fa9d68；起始 clean，独立 origin/main SHA 一致。
`custom/lots/extension.tsx` 注册 `/lots`。“持仓提醒”实际记录用于生成监控规则的买入批次，并非券商账户持仓账本。
原 CN 通过 lotsList、instrumentNames、klineDailyBatch(5) 读取批次、名称和日 K 参考价；按买入日期排序，CostPnL 计算纯价格盈亏比例，RemainingDays 依原有系统日期显示到期剩余天数。
新增/编辑调用 lotSave；两步删除调用 lotDelete，并失效 lots / monitorRules。保存会生成真实止盈止损/到期规则；原页还能查询证券、打开日 K 详情和进入监控中心。

最小 L3 接线：现有注册/插槽不能替换页内市场主体，只在原扩展增加 URL 市场外壳、原位 MarketSwitcher 和隐藏市场弹窗可见性控制。
不复制整个 CN 页，不修改查询、计算、排序、规则、保存/删除 handler、原日期组件或 API。
上游合并需复核原扩展外壳、工具条与弹窗控制。没有 API、缓存 schema、数据库或依赖变化。

## 独立样稿与现有契约

专用 `tests/fixtures/lots_preview/index.ts` 独立编写 HK3/US3 个样稿，不读取账户、原 Lot 数据或其他页面 fixture。
HK：0700.HK/9988.HK/3690.HK；US：AAPL.US/NVDA.US/MSFT.US。代码只用于界面展示，不作为任何 provider 请求。
交易日固定 2026-09-16；generated_at 固定 2026-09-17T04:00:00Z，提醒检查样稿固定 2026-09-17T01:00:00Z 或 null。
不使用当前系统时间生成事件或推算剩余天数。

每个 envelope / 批次 / 提醒都沿用既有 provenance：status PREVIEW、source synthetic-fixture、data_mode preview、is_production false、is_investment_signal false、fixture_only true、synthetic true。
专用 sample_id 不作为真实 Lot.id，不进入真实账户、Lot/MonitorRule 或提醒 store。
规则结构仅从既有 Lot 类型选取 target_pct、stop_pct、remind_date、lead_days，并显式允许 null；百分比字段沿用原 Lot 百分数值（10表示10%），盈亏/回撤/集中度为独立 fraction 展示口径（.05表示5%）。
数量明确 synthetic-shares，不证明供应商真实股数/board lot/可比性契约。
HKD/USD 分开显示，禁止跨币种合并。

## 概览、列表和风险

- 每市场3个合成批次，其中2个有完整预给定成本/参考价/盈亏，第3个数量、价格、盈亏、规则和状态等保留 null + 原因。
- 概览的成本/参考市值/演示盈亏明确为“已知样稿子集 2/3”，不是全部持仓或账户净值。HK预给定34000/35300/1300 HKD；US预给定2400/2460/60 USD。
- 全部批次总盈亏未知，始终 null 并说明第3个样稿缺证据，绝不把子集盈亏当总额。
- 列表显示代码/名称/市场/币种、合成数量、演示成本/参考价格/盈亏金额和比例、提醒样例状态、source/evidence。
- 止损线/目标价/回撤全为固定样稿，不计算或给出实际投资建议。完整组合未知，集中度 null；部分回撤也 null，显示原因。
- 提醒列表按当前筛选显示名称、演示说明、样例状态、固定检查时间、来源/证据和原因。
- 详情提供风险提示与规则结构查看，只读、不保存、不从价格比较得出触发状态。

PENDING_SAMPLE / BLOCKED_SAMPLE / null 分别显示待观察样例、阻塞样例（非真实风险结论）、状态未知；不推断默认正常。
校验限定市场/币种/Preview身份、唯一样本、有限数值、非负数量/风险线/规则参数、整数提前天数、UTC样稿时间、完整缺失字段/原因及子集覆盖；不自动补零或修复矛盾。

## 交互与副作用隔离

沿用已有 Index/Watchlist/Review/Monitor/Abnormal Preview 的 URL market 和独立页面树；复用 PageHeader、MarketSwitcherBar、StockDataTable/useTableSort、格式化、EmptyState/ErrorState 和原页卡片视觉。
CN 默认，HK/US 精确切换、刷新和浏览器返回保留市场；其他参数保留。搜索、提醒状态筛选、列排序和样稿详情在各市场独立，null 始终排末。
直接 HK/US 不挂 CN，不查询真实账户/批次/证券/价格/规则，无生产 mutation、storage 写入、通知或订单。
已访问 CN 保留树及原查询观察器；隐藏时编辑/日K弹窗不浮到 Preview 上，返回仍可操作原批次。未保存弹窗内部草稿不承诺跨市场持久化，不写回真实配置。
新增/编辑/删除展示为 disabled 并说明 Preview 不可执行，无生产 handler；不添加假的下单/确认/通知按钮，也不跳到真实监控执行页。
空、加载、错误及无匹配状态均不回退生产数据。

统一显著声明：**演示数据｜非真实账户持仓｜非生产行情｜不构成投资建议**。

## 生产边界和验收

不修改 Longbridge、QuoteService、Snapshot Archive、Historical Provider、真实持仓/交易/提醒/通知、生产数据库、Momentum Engine/Producer/Calculation/Profile/Universe/Input Gate 或冻结 hash。
无真实 HK/US 持仓、新后端 API、真实提醒 Producer 或真实投资信号；Volume/VR20、split-only、PIT/vintage 和正式 Universe 仍 BLOCKED，Daily finality PARTIAL、corporate actions UNKNOWN。
只运行隔离前端 mock/fixture 测试，不构成真实账户或盈亏验收。
真实浏览器视觉验收未执行，不能把 TypeScript/Vite build 当作该项验收。

2026-10-17：新增12项测试通过，相关35项回归通过；最终完整前端43文件/332项 Vitest 通过，独立 node:test 5项通过，TypeScript/Vite build 通过。
原 CN 主体排除已审查的市场外壳、控件注入、编辑/股票弹窗可见性差异后逐字等价；敏感模式扫描、Preview runtime API/账户/存储/时钟/通知隔离检查及 diff check 通过。Lot 导入仅为类型，未引入运行时账户 API。
仅保留既有 React Router future flags 提示和 Vite 大 chunk 警告，无本阶段类型或构建错误。

**本阶段完成的是持仓提醒页面 HK/US Preview，不代表真实账户持仓、真实盈亏或真实提醒已经接入生产。**
