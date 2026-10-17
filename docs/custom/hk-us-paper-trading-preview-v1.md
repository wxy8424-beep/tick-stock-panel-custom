# HK/US 模拟盘 Preview v1

## 审计与边界

基线：main / e5aeedc2d5f1e4c3f38cdcd41c4cae52b8450597。

实际入口为 `frontend/src/custom/paper/extension.tsx` 的 `/paper`。CN 默认是多账户对比页，通过 `paperCompare` 与 `useQuoteStatus` 查询；展开账户查询 overview/orders/trades/nav/stats/rounds。原页面包含创建、冻结、删除、下单、撤单、跟单规则和费用设置；证券搜索使用 portal，存在离开页面后浮层残留风险。

后端 `backend/app/api/paper.py` 将订单/撤单交给 `backend/app/strategy/paper.py`。后者通过 fills.jsonl 台账重放现金、持仓与净值，盘中或日终撮合，并在 data/paper/accounts 下持久化账户状态。本次没有修改这些文件、路径、执行规则或运行数据，也不执行其接口验证。

现有 HK/US lots/watchlist/index 等 Preview 已采用独立 fixture、provenance、URL market 和只读 presentation。本次沿用该模式、MarketSwitcherBar、PageHeader、StockDataTable、useTableSort、EmptyState 和 ErrorState。只复用 PaperOrder 的类型联合，不把样稿 DTO 当作生产 PaperOrder、PaperFill 或 PaperHolding。

## 页面与隔离

- `/paper` 默认 CN；`?market=HK` 与 `?market=US` 直接进入独立样稿，不挂载 CN 查询、账户面板或交易表单。市场写入 URL，保留其他参数，支持刷新与浏览器返回。
- HK/US 各自保留搜索、订单状态筛选、排序和详情选择，不混合账户、币种或排名。
- 离开 CN 时卸载 CN 页面树，关闭创建弹窗、交易表单和 portal 搜索下拉；返回 CN 等同原页面重新进入，按原默认状态初始化，不承诺保留未提交草稿或临时筛选。仍在 CN 时，账户查询、计算、排序、日期、费用、冻结、创建/删除、下单/撤单等原业务代码保持原样。
- Preview 买入、卖出、撤单、清仓、重置和创建账户均为禁用状态，说明“Preview 模式不可执行”。没有新 API、通知、账户存储、订单提交或撮合路径。CN 已提交在途请求不被重新解释为 Preview 操作。
- 宣明显著显示：**演示账户｜合成订单与成交｜非真实交易记录｜不构成投资建议**。每条持仓、订单、成交均带 PREVIEW / synthetic-fixture / preview / is_production=false / is_investment_signal=false / fixture_only / synthetic 身份与独立 evidence。

## 固定样稿及账务口径

专用 `frontend/tests/fixtures/paper_preview/index.ts` 每次构造全新的 HK/US 样稿，未读取 CN 账户、券商账户或其他页面 fixture。交易日固定 2026-09-16，generated_at 固定 2026-09-17T05:00:00Z；提交、成交与历史日期均预先编写，不依赖系统日期或真实市场日历推断。

| 字段 | HK / HKD | US / USD |
| --- | ---: | ---: |
| 初始资金 | 100000 | 10000 |
| 现金 | 65980 | 7598 |
| 持仓市值 | 35300 | 2460 |
| 总资产 | 101280 | 10058 |
| 已实现毛盈亏 | 0 | 0 |
| 未实现毛盈亏 | 1300 | 60 |
| 费用 | 20 | 2 |
| 累计净盈亏 | 1280 | 58 |
| 净收益率 | 1.28% | 0.58% |

样稿无外部出入金。成本价为不含费用的买入成交价；现金 = 初始资金 - 买入成交金额 - 费用，市值 = 合成数量 × 固定参考价，总资产 = 现金 + 市值；累计净盈亏 = 总资产 - 初始资金 = 已实现毛盈亏 + 未实现毛盈亏 - 费用。费用仅扣一次，持仓纯价格收益不冒充费后回报。已实现为 0 的原因是无卖出成交，并非未知值填零。

各市场两个合成持仓、三个订单、两个对应成交；第三个订单待成交，无关联成交、费用、持仓或盈亏，不预扣现金。这只是固定样稿口径，不宣称真实账户的冻结资金规则。委托参考价刻意不同于成交价，提交时间不同于成交时间，不能拿最新参考价或提交时间充当成交证据。

可卖数量 null：HK/US 可卖/结算契约未冻结，不套用 CN T+1。待成交委托参考价 null，明确未提供；无已平仓回合，胜率 null，不能填零。合成股数和费用不代表实际 board lot、市场收费或税务规则。

资产历史使用固定日期表格展示现金、市值、资产、相对初始资金收益。没有复用包含 CN 沪深300 比较口径的原净值图，不创建虚假 HK/US benchmark，不将样稿当回测或真实业绩。订单支持状态、证券搜索与列排序，未知参考价始终末尾；证券搜索同时过滤持仓、订单与成交，状态筛选仅作用订单。

## 校验与质量

`paper-preview/contract.ts` 校验 Preview 身份、市场/币种隔离、唯一 sample_id、evidence、UTC 固定时间形状、有限数值、价格/数量、资产与盈亏恒等式、持仓合计和费用、成交与已成交订单关联及数量一致性、历史资产/收益口径和缺失原因。金额比较按分，收益比例的浮点表示误差只用于样稿一致性检查，不改变任何冻结指标定义。此校验器不是通用账户回放或撮合器。

无真实 backend/provider/QuoteService/Archive/Historical/数据库/执行器变更。无 Momentum producer、真实 Universe、真实投资信号或冻结契约修改。Longbridge volume/VR20、split-only、historical PIT/vintage、正式 Universe 仍 BLOCKED，finality PARTIAL、corporate actions UNKNOWN；供应商确认继续等待，本阶段不解除任何 blocker。

## 验收

新增 PaperPreview 测试覆盖 CN 默认查询/刷新/创建与跨市场弹窗退出；HK/US 独立渲染、只读禁用、无 API/query/storage/notification；现金/资产/费用/毛净盈亏一致；持仓、订单及成交 evidence；搜索、筛选、排序与详情；null 原因；固定日期和独立 fixture；URL/浏览器返回与市场隔离；无效样稿拒绝；loading/error 不回退。

验收：新增 11 项测试，连同 LotsPreview / MonitorPreview 的 targeted 共 35 PASS；完整 Vitest 44 文件 / 343 PASS；node:test 5 PASS；TypeScript / Vite build PASS。过程中修正新校验器多余括号及测试 DOM 元素类型标注，最终无失败。仅既有 React Router future / 构建 chunk 大小提示。后端、数据库与运行行情不在本阶段测试范围。

真实浏览器截图/视觉验收未执行；单元测试与构建通过不等同视觉验收通过。

**本阶段完成的是模拟盘 HK/US Preview，不代表真实 HK/US 模拟交易、券商账户或订单撮合已经接入生产。**
