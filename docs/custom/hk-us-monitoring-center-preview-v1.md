# HK/US Monitoring Center Preview v1

## 审计和最小边界

基线 main / dc3071472b69194a5a544682289b74a6b4b1f6d8，起始 clean，独立读取 origin/main SHA 一致。
监控中心由 `frontend/src/custom/monitor/extension.tsx` 注册 `/monitor`。
原 CN 读取 `monitorRulesList`、`alertsList`（7日/500条、source过滤和 ext 标签）、preferences、quoteStatus；规则分组/名称/自定义信号使用既有共享查询。
QuoteService 状态用于实时行情不可用提示，并控制告警轮询间隔；本页没有独立的 Worker 健康接口或卡片，不能据此宣称 Worker HEALTHY。
触发记录有来源过滤、详情、删除/清空；规则有新建、编辑、启停、删除/全清；配置弹窗可写 monitor_ext_fields。进入 CN 页调用 markSeen，离开调用 leaveMonitorPage。

采用最小 L3 接线：已有注册能力不能替换 `/monitor` 内部市场主体。原扩展仅增加市场外壳、可见性参数和弹窗/深链/已读生命周期边界，所有新增样稿放入 `custom/damon/monitor-preview`。
不复制原页，不更改监控规则、API、Worker、后端告警处理或 monitorBadge store 实现。
上游合并时需复核该扩展的外壳及可见性接线。

## 复用与独立 fixture

沿用 Index/Watchlist/Review/Environment 的 URL market、访问后保留页面树、Preview provenance 模式。
复用 MarketSwitcherBar、PageHeader、StockDataTable/useTableSort、EmptyState/ErrorState 和原监控中心的双栏/卡片视觉。
Dashboard 有自己的服务/数据契约，不作为本页真实 Worker 或告警数据来源。
独立文件 `frontend/tests/fixtures/monitor_preview/index.ts` 不导入其他页面 fixture，不读取 CN 数据，不创建 MonitorRule 或 AlertEvent，不进入生产 store。

- 固定交易日：2026-09-16；generated_at：2026-09-17T02:00:00Z。
- 固定任务检查时间：2026-09-17T01:50:00Z；缺失者 null。
- HK 更新时间样稿：2026-09-17T01:55:00Z；US 未提供更新时间，保持 null + reason。
- HK/US 各4个任务样例，HK2/US3个告警样本；市场身份和证券分别维护，不混合统计。
- 统计为固定 fixture 字段，校验与样稿任务状态数量一致；已知零与未知 null 区分，不把缺失计为零。
- 条件仅预编写说明，不执行阈值、真实价格比较、数量计算或触发规则。

## 状态与证据

envelope / task / alert 均标识：status PREVIEW、source synthetic-fixture、data_mode preview、is_production false、is_investment_signal false、fixture_only true、synthetic true。
任务使用 sample_state NORMAL/WARNING/ERROR/UNAVAILABLE，显示“正常样例”等，绝不表示进程 RUNNING 或服务 HEALTHY。
合成告警 OPEN_SAMPLE / ACKNOWLEDGED_SAMPLE 分别显示“未确认样例（非真实待处理告警）”“已确认样例（未执行真实确认）”；未知状态保持 null + reason。
真实 Worker/服务健康均显示未观测；样稿完整性 SAMPLE_COMPLETE 仅代表样稿字段，不能宣称生产输入 READY。
任务详情显示条件、样稿时间、缺失字段、reason、source/evidence、blockers/warnings。告警详情原生展开，显示类别、固定时间、说明及证据，不跳真实证券行情。
校验拒绝混合市场、重复样本 ID、生产标识、不合法状态、非有限/负数/不一致计数、无时区时间、未说明的空字段。

统一声明：**演示数据｜非生产状态｜不构成真实告警或投资信号**。
所有时间均明确标为固定样稿 UTC，不随系统时间变化，不使用相对“刚刚/最近”格式。

## 交互与副作用隔离

默认 CN；HK/US 由 URL market 精确选择，保留其他参数、浏览器返回和直接刷新行为。未知 market 为 CN。
直接 HK/US 不挂载 CN，不调用真实 API、QuoteService/prefs/alert/rule 查询或 markSeen，不写 localStorage。
搜索证券/任务/告警、严重程度筛选同时作用于任务及告警；任务状态筛选仅作用于任务。任务列排序、选中详情与告警详情展开均本地执行。
市场间搜索、筛选、排序、选中项独立；空/加载/错误不回退生产数据。
新建规则、启停和编辑采用 disabled，说明“Preview 模式不可执行”，无生产 handler；不额外制造发送通知/确认真实告警/订单/持仓按钮。

CN active=true 时原查询、筛选、编辑、启停、删除和清空 handler 不变。已访问 CN 保留树/状态及既有查询观察器；Preview 不启动真实任务或取消既有请求。
必须补充的 UI 可见性边界：

1. 切到 HK/US 时清理 CN 进入页的已读同步生命周期，返回 CN 才重新 markSeen，避免把未展示的真实告警视为已读；store 算法与告警处理不变。
2. CN 隐藏时不处理 `new=abnormal` 深链，避免其清空 HK/US market 参数；CN 原深链仍按原方式消费。
3. 编辑/全清/配置/股票/成分详情弹窗隐藏，返回 CN 恢复本地状态，不能浮到 Preview 之上。

## 生产边界

无 backend、Provider、QuoteService、Snapshot Archive、Historical Provider、Worker 生命周期或生产数据库变更；无新 API、依赖、真实监控任务、Universe 或 Momentum Producer。
不修改 Momentum Calculation/Profile/Snapshot/Universe/Input Gate，既有冻结 hash 不变。
Longbridge volume/VR20、split-only、historical PIT/vintage 继续 BLOCKED，finality PARTIAL，corporate actions UNKNOWN，供应商回复继续独立等待，不阻塞前端工作。

## 验收范围

测试使用隔离 fixture/mock，覆盖 CN 查询/来源筛选/规则编辑权限/深链、市场切换和 badge 生命周期、HK/US 独立样本、统计、搜索/状态/严重程度/排序、详情/null原因、固定时间、禁用操作、无真实 API/存储/已读副作用、空错加载态及契约校验。
真实浏览器视觉验收尚未执行，不能把 jsdom 或 build 当作视觉验收。

2026-10-17：新增12项测试、相关34项通过，完整前端41文件/308项 Vitest 通过，独立 node:test 5项通过，TypeScript/Vite build 通过。仅保留既有 Router future flags 和大 chunk 提示。
原CN主体排除已审查的市场外壳、弹窗可见性、深链与进入/离开页控制后逐字等价；敏感模式扫描、Preview API/存储/badge import 隔离检查及 diff check 通过。

**本阶段完成的是监控中心 HK/US Preview，不代表 HK/US 真实监控、真实 Worker 状态或真实告警已经接入生产。**
