# HK/US 策略页面 Preview v1

## 基线与审计

基线 main / bc6aaf2cbc77af83b3ecc189df3aef3d6f97e75d，开始时工作区干净、暂存区为空。origin/main 首次独立读取遇普通 schannel TLS 错误，相同命令重试一次后 SHA 与本地一致；未修改网络配置。

实际页面为 `frontend/src/pages/Screener.tsx`，路由 `/screener`，标题“策略”。原 CN 页面：

- 查询 `screenerStrategies`、缓存摘要与单/全策略结果、data status、preferences、capabilities、quote status、watchlist、monitor rules，并按需查询 K 线或分钟增量。
- `useStrategyPool` 管理本地统一策略池并迁移旧分钟池；列配置、过滤和卡片偏好有原存储路径。默认日期跟随 enriched 最新日；自动计算由原 preferences 和策略池决定，日线/分钟分别路由。
- 单/批计算调用 screenerRunPreset / screenerRunAll；重载调用 strategyReload。设置弹窗通过 strategyGet / strategySaveConfig / ResetConfig / Delete 等读取、保存、重置、删除，保存后可重算；创建器可 AI 构建、验证和保存代码，另有叠加策略及默认参数设置。
- 监控按钮会保存/删除真实 MonitorRule；结果可加入自选。因子页可以生成策略/信号；策略回测页消费定义、因子、入退场和成本参数；模拟盘通过策略或规则跟单。不能把这些真实执行组件直接用于 Preview。
- `StrategyDetail` 定义 version、params/params_defaults、basic_filter、overlay_filter、scoring、entry/exit signal IDs、stop_loss/take_profit/trailing/max_hold_days 等。`StrategyParamDef` 有类型/默认值及可选范围；`CustomSignalCondition` 为 left/op/right 与相对日偏移。basic_filter.enabled 是基础过滤开关，监控规则 enabled 是监控开关，都不是“策略实时运行健康”证明。
- 没有从当前模型建立 HK/US 已执行的仓位比例上限、日风险预算、最大回撤强制约束或交易频率契约。回测/模拟盘成本不是策略详情已强制生效的成本或风控。

现有插槽没有整页市场隔离能力，L1 配置或 L2 局部插槽不能阻止 CN hooks、策略池存储与自动计算挂载。因此采用最小 L3 接线：Screener 入口包市场外壳，原主体 ChinaScreener 接收控件，PageHeader 放置原风格 MarketSwitcherBar。没有复制 CN 页面或修改原查询、计算、过滤、保存/执行算法。上游同步仅复核入口/import/Header 接线。

## 模型与固定样稿

专用 `custom/damon/strategy-preview`，复用 IndexPreviewProvenance、PageHeader、StockDataTable、useTableSort、EmptyState、ErrorState；仅 type-only 复用 StrategyParamDef / CustomSignalCondition 形状，不创建 StrategyDetail 或注册生产引擎。

HK/US 各四项独立手写样稿：趋势、过滤、待定义、量能规则阻塞；不是 CN 策略复制后换代码。ID 为 fixture-strategy-HK|US-N，版本 preview-v1 / preview-v2；参数版本 preview-params-v1；配置和 evidence 使用 fixture:strategy:... 身份。这些是展示标识，不是生产注册版本或冻结计算契约 hash。

固定交易日2026-09-16，generated_at=2026-09-17T08:00:00Z。HK 范围只展示0700.HK/9988.HK，US只展示AAPL.US/MSFT.US；范围是样稿证券集合，不是 production Universe，instrument_type、universe_identity、input_contract_identity 均 null。

每行和 envelope 保留 PREVIEW、synthetic-fixture、preview、is_production=false、is_investment_signal=false、fixture_only/synthetic 身份。页面声明始终在 Loading/Error/空态之外：

**演示策略｜非生产策略配置｜不产生真实交易信号｜不构成投资建议**

## 状态分层

- display_state 使用 DEFINED_SAMPLE / INCOMPLETE_SAMPLE / NO_RULE_SAMPLE / BLOCKED_SAMPLE，中文明确为“样稿”；不用 ENABLED/RUNNING 冒充生产实例。
- definition_status 分别 READY / PARTIAL / UNAVAILABLE / BLOCKED，仅说明样稿结构是否有定义，不是数据或执行就绪。
- validation_status 全部 BLOCKED；runtime_status、last_run_at、signal_count 全 null。未知信号数不填0，generated_at 不冒充运行记录。
- 统计卡只计四项样稿的结构状态，不是生产运行策略数量，不混合市场或排名。

## 规则、参数和风险

完整样稿提供合成 entry AND(close > field:ma20, change_pct > 0) 与 exit OR(close < field:ma20)，明确左右字段、比较符、日偏移及小数制阈值，按已有条件形状只读展示。没有条件求值、指标计算、调度或历史数据。其他样稿的缺失 entry/exit 保留 null + reason；量能规则不因公式可写就绕过 quantity blocker，也不补造真实交易逻辑。

参数展示 window=20 和 max_hold_days=10 的独立数值示例，包含字段来源、单位、样稿版本、evidence、展示校验状态。正式默认值与 min/max 未取得本样稿可用契约，因此均 null；不能继承 CN 某策略的范围。缺失参数保持 UNAVAILABLE，不自动补0或默认值。持仓天数只复用字段形状，不声称 HK/US session 执行映射已成立。

风险区域 stop_loss=.08 / take_profit=.15 以 fraction 标明8%/15%，有值只代表样稿字段，不代表引擎实施。单标的/总仓位比例、最大回撤、单日风险预算、交易频率和成本均 null / UNAVAILABLE + reason，不能借用 backtest/paper 的配置宣称策略风控生效；所有 enforced=false。最长持仓字段在参数区只读展示。

依赖区域保留历史价格/split-only、Volume/VR20、PIT/vintage、正式 Universe 和执行 BLOCKED，finality PARTIAL、corporate actions UNKNOWN；Factor 未选择，回测结果不存在，不伪造胜率或收益。证据引用已有 vendor closure 和 Universe 文档；它们不是当前动态健康检查，未发送新供应商请求。

## 交互与隔离

- URL market 控制 CN/HK/US，未知值回 CN；保留其他参数，直接刷新/浏览器返回可恢复市场。
- 跨市场卸载旧页面树，清除选中策略、搜索、类型/定义状态/版本筛选、排序和详情。回 CN 等同重新进入原页，不承诺保留未保存草稿；既有后台任务不被 Preview 自动取消或重发。
- 只提供列表搜索（名称/ID/描述）、类型/状态/版本过滤、名称/版本/状态排序、规则/参数/风险/依赖详情。无参数编辑模式，不保存“演示修改”。
- Preview 创建/运行/保存/加入监控明确禁用，不连接生产执行器、回测、Worker、信号、账户、订单或通知。没有真实策略/信号/回测 API、Query、存储或当前时钟路径。
- 直接 HK/US 不挂载 CN useStrategyPool、列配置载入、生产查询或操作弹窗。已有 CN 查询/启停监控/参数保存/计算/自选行为不变。
- 没有 backend、provider、QuoteService、Archive、Historical、DB、真实配置/风险或 Momentum Engine/Producer/Calculation/Profile/Universe/Input Gate 变更；不解除供应商 blocker。

## 验收

新增12项：CN查询/重载/资产切换，HK/US隔离与禁用操作，搜索/类型/状态/版本过滤，排序，状态分层，结构化规则，参数/范围与风险原因，依赖 blocker，URL/返回重置，固定日期和无效数据拒绝，Loading/Error/空态。相关现有 StrategyCard / StrategySettingsDialog / StrategyPoolDialog / DefaultStrategyParamsDialog 测试一同通过，共39 PASS。

完整前端47文件 / 379 Vitest PASS；node:test 5 PASS。首次构建发现测试替身参数类型声明不匹配，仅修正签名、未减少断言，新增12项再次PASS，最终 TypeScript / Vite build PASS。CN主体排除已审查市场接线后逐字等价，Preview无API/query/storage/当前时间/条件执行静态检查PASS。六个计划文件敏感扫描、diff/范围审查通过，逐文件暂存并复核内容，不夹带运行数据。仅既有 Router future / chunk 大小提示；仅前端变化，不运行后端套件。

真实浏览器视觉验收 NOT RUN；构建成功不等于真实视觉验收通过。

**本阶段完成的是策略页面 HK/US Preview，不代表 HK/US 真实策略计算、生产信号生成或交易执行已经接入。**
