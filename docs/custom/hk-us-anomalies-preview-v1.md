# HK/US 实时异动流显式离线 Preview v1

任务：T-2026-10-19-A12，Agent A / MAINLINE，2026-10-19。
基线：`main` / `965c42b8173209ee5a65da946b49f1026b1ba03e`；开始时工作区 clean，暂存区为空。

## 审计与改动边界

此页为 `/anomalies`（实时异动流），不是已有 synthetic Preview 的 `/abnormal`。原页面本就展示 ALL/CN/HK/US 后端事件；本阶段不能将真实港美事件读取替换成合成数据。

原调用链：扩展注册 → AnomalyMonitoring → useAnomalyDelivery → AnomalyDelivery → recent/incremental；挂载时立即查询、每 3 秒轮询，监听 focus/visibilitychange。页面另有 3 秒健康查询、历史/市场上下文批量查询、历史分页和本地注意提示计时器。Evidence 展开后查询单条历史、市场、episode 和 IntelligenceContext；StockPreviewDialog 也属于业务组件。IntelligenceContext 是结构化证据读取，不能仅凭名称将它描述为生成式 AI 调用。生产 API/交付实现未修改，原页面内没有新增保存、交易、通知执行路径。

只有入口需要 L3 小改：现有扩展槽无法阻止这些 hooks 挂载。原 AnomalyMonitoring 的完整业务主体改名 LiveAnomalyMonitoring；export 入口返回模式边界。React 元素创建不执行其组件函数，只有未指定 data_mode 时才渲染原主体。未改后端、事件 schema、检测器、交付算法、QueryClient、Layout、共享组件、其他页面或 Agent B 工作树。

六文件范围：页面入口、独立 contract、Presentation、固定 fixture、新测试、本文档。不建立 Preview controller framework、validator factory、Provider 或 loader。复用现有纯 UI：PreviewNotice、PreviewDisabledAction、MarketSwitcherBar、StockDataTable/useTableSort、EmptyState/ErrorState。

## URL 规则及兼容性

- `/anomalies?data_mode=preview&market=HK` 和 US 是唯一有效 Preview 模式。
- 没有 data_mode 参数时，保留原页面及默认 ALL 过滤行为，即便 URL 有 market=HK/US、run 或事件 ID。原先 market 是页面内 state，不能借此更改其语义。
- 只要显式出现 data_mode，就必须唯一且精确等于 preview；market 也必须唯一且精确为 HK 或 US。缺失、空值、大小写错误、重复（包括同值重复）、冲突或其他模式均错误，不能回退真实查询。
- Preview 的市场栏只启用 HK/US，保留 data_mode 及其他 URL 参数。没有借用 CN 按钮跳转真实业务，也没有自动读取生产 event_id。key=market 重建本地搜索、筛选、排序和详情状态；刷新及历史前进/返回按 URL 重建。
- 原页面可在非 Router 环境直接挂载，既有测试即如此。模式边界用 useInRouterContext 选择路由读取或 window.location.search 的只读解析；无 Router 的显式错误 URL 同样拒绝，不用测试环境绕过隔离。

原默认页面的全部既有断言保留。其未指定模式时仍包含交付、查询、分页、市场/严重程度/类型过滤、注意提示、证据展开与证券详情。页面模块仍导入旧业务代码，但 Preview 不挂载其 hooks，不订阅交付、不轮询、不监听业务 focus、不打开 Evidence、IntelligenceContext 或证券详情组件。

## 独立 synthetic DTO

每个 envelope 和样本声明 PREVIEW、synthetic-fixture、preview、is_production=false、is_investment_signal=false、fixture_only=true、synthetic=true。sample_id 为 `fixture-anomaly-{HK|US}-{A|B}`，证券为 `SYNTH-{A|B}.{HK|US}`，evidence 与市场和身份严格匹配。HK/US 各有独立固定 envelope、时间、方向及演示变化值，返回深拷贝，不读取生产对象。

仅展示已有类别 rapid_price_move / intraday_breakout 的固定元数据，不运行检测或比较。sample_state 为 SYNTHETIC_SAMPLE，execution_status 恒 BLOCKED。演示严重程度不发出提醒，固定 event_time 不是实际事件发生证据。所有日期固定：2026-09-16；UTC 时间及 generated_at 均为编写值，不能冒充真实读取、交付或 Worker 健康。

生产 event_id、episode_id、rule_version、health_state、delivery_sequence、last_success_at、intelligence 全部 null，并有分别说明的缺失原因。B 样本的 change_pct 和 window_minutes 为 null，不填零、不推导。变化值单位是小数比例，显示时乘 100；任何显示四舍五入仅格式化演示数值，不执行检测。表格 null-last 三态排序是展示排序，不是市场排名。严重程度列按元数据文本排序，不表示风险定量模型。

运行时校验严格限定键、合成身份、市场/代码/evidence 一致性、固定数据性质、事件时间的有效 UTC 格式及交易日一致、有限数值、安全正整数窗口和 null 原因。拒绝生产身份、READY、非合成 source、市场混入、重复 ID、NaN/Infinity、数字字符串、额外动作字段及生产水位伪零。失败显示错误，不查询生产数据补齐。

页面始终显示「演示数据｜非生产行情｜不构成真实异动事件或投资信号」。搜索、类型/严重程度筛选、详情和排序仅更新本地 React state。唯一真实交付入口以原生 disabled button 明确不可执行；没有假成功回调。

## 本轮自动化验收及原始失败记录

以下为 A12 实际执行，不引用历史结果冒充重跑。命令工作目录为 frontend，使用已安装运行器。完整 Vitest 按源码识别 node:test 文件后分开执行，未排除任何失败用例。

| 检查 | 结果 | 退出码 | 命令墙钟秒 |
| --- | --- | --- | --- |
| 首次：`node node_modules/vitest/vitest.mjs run src/pages/AnomalyMonitoringPreview.test.tsx src/pages/AnomalyMonitoring.test.tsx` | **50 PASS / 4 FAIL**；原页面 10/10 通过 | 1 | 5.97 |
| 修正后同一 Preview 的相关联合回归，共 9 文件 | 90 PASS（新增 44 + 原页面 10 等） | 0 | 5.79 |
| 完整 Vitest，54 文件 | 538 PASS，一次完整运行无失败 | 0 | 11.30 |
| `node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts` | 5 PASS | 0 | 0.50 |
| `node node_modules/typescript/bin/tsc -b` | PASS | 0 | 20.34 |
| `node node_modules/vite/bin/vite.js build` | PASS | 0 | 15.28 |

首次 4 FAIL 的实际原因：新增测试把 `queryFn: api.anomalyHealth` 的调用错误预期为无参数，实际 TanStack 传入 `{client, queryKey, signal, meta}`。仅修改新增测试，使其严格核对实际 QueryClient 和 QK.anomalyHealth；没有删除断言、改旧测试、扩大 mock 或修改产品代码来消除该失败。相关回归是有明确测试修正后的新运行，不以重试覆盖首次失败。

原始失败摘要保留：`expected "spy" to be called with arguments: [ 'anomalyHealth' ]`；实际为 `['anomalyHealth', { client: QueryClient, meta: undefined, queryKey: ['anomaly-health'], signal: AbortSignal }]`。四个失败均位于新增 absent-data_mode 参数化用例，原有业务测试 10 PASS；首次总退出码为 1。

相关命令为同一 Vitest runner，加：AnomalyMonitoringPreview、AnomalyMonitoring、lib/anomalyDelivery、components/anomalies/HistoricalContext、MarketContext、IntelligenceContext、components/MarketSwitcher、pages/MarketSwitcher.integration、components/stock-table/StockDataTable 的对应测试文件。新增测试只在本文件内 mock 可观测业务入口，以证明 Preview 不挂载它们；旧页面测试保持原来真实交付 hook 与固定 API 响应的验证方式。新增分页用例校验原 cursor 查询；原有测试继续验证注意提示和证据展开。

保留现有 React Router future-flag 和 Vite 大 chunk 警告。浏览器脚本准备阶段 Python/uv launcher 曾权限失败，未启动服务；随后用 PowerShell 生成同一范围的本地 QA 脚本，未更改 Python、系统或 Git 配置。此环境错误不是产品测试通过证据。

## 浏览器与证据边界

Browser acceptance = **PARTIAL**。两次均为本轮真实 Edge headless/CDP，仅使用合成响应，不以 jsdom 或构建代替。

- 首次 `node .vite/anomalies-A12-20261019/browser.mjs`：27 项检查 PASS、0 项检查 FAIL，但脚本在错误页等待条件返回 DOM 对象时收到驱动错误 `Object reference chain is too long`，未完成，**退出码 1，39.73 秒**。该等待表达式配合 CDP returnByValue 请求序列化 DOM 对象，不能把它当页面业务失败或完整验收通过。原 `results.json` 和脚本原样保留。
- 针对遗漏部分的独立补查 `node .vite/anomalies-A12-20261019/focused.mjs`：只将 QA 等待条件改为布尔值、使用独立 profile / `focused-results.json`，产品源码未改变。7 项检查 PASS、0 FAIL，退出码 0，31.00 秒；同时保留两次 `/api/intraday/stream` 的 `Invalid InterceptionId` 协议错误，分别发生在错误页和默认页阶段。因此最终不能改写为完整 Browser PASS。
- 首次覆盖 HK/US 直接入口、固定身份、原生禁用按钮、null reason、键盘 Enter/Space 各排序一次、Tab 到下一表头、搜索空状态、详情、1440px/390px、刷新和市场切换及前进/返回。实际 React fiber 检查未发现 LiveAnomalyMonitoring、Evidence、IntelligenceContext 或证券详情组件挂载。
- 补查覆盖重复市场参数 fail-closed、未指定模式时原默认 ALL、旧页空状态及 recent/incremental/health 合成 GET 确实发生。Preview/错误页无 anomaly 业务请求；默认页的真实查询代码仅对合成端点运行。
- 两份记录均无页面异常或 console error，没有非 GET 业务尝试。HK/US 桌面及 390 截图、错误页截图已生成；前四张存在性已核验，HK 390 与 US desktop 已实际打开检查，标题未被菜单遮挡、无新增整页横向溢出；表格内部允许横向滚动。

浏览器使用专属临时 profile、无生产后端代理的 Vite loopback 服务、固定合成 HTTP 响应，外部页面请求阻断、非 GET 请求拒绝。对照无 data_mode 的旧页面也只读取合成响应。QA 日志、截图、脚本仅放在被忽略的 `frontend/.vite/anomalies-A12-20261019/`，不进入六文件候选。

必须区分：Preview 自身业务请求/存储/通知为零，由离线 spies 和源码证明；Layout、告警、Query 持久化等宿主仍可有自己的请求和存储行为。不能声称整个 HK/US 页面零副作用。未验证生产服务、真实供应商故障恢复、长期缓存、每一种并发时序或真实模型能力。

浏览器原始网络日志仍有宿主 `/api/custom-signals`、alerts、settings、pipeline、intraday status/stream 等合成 GET；没有将其隐藏或称为零请求。本轮浏览器未单独测量宿主全部 storage 写入。独立 Preview 零写入断言覆盖 Storage.getItem/setItem/removeItem/clear、fetch、EventSource、Notification 与业务 hooks/组件调用；这不是整个站点的零副作用断言。

## 最终静态审查

原页面反向比较 PASS：只逆转新增 import、wrapper 和函数改名后，与 HEAD 版本逐字一致。旧 AnomalyMonitoring.test.tsx 及其他测试没有修改。新增展示及 fixture 不导入 api、交付 hook、Query、业务详情、storage 或通知模块，不启动 timer/effect。

六文件源码/diff review、候选范围、git diff --check 与覆盖未跟踪文件的尾部空白扫描 PASS。高置信私钥、Token 及凭证赋值模式扫描为零匹配（有界扫描不等于保证所有秘密形式均不存在）。没有修改共享宿主或后端，无须扩大范围，未发现新增产品 P1/P2。浏览器驱动限制继续记录为未完全闭合事项。

## 生产限制与交付

Production validation = **NOT VERIFIED**。没有请求真实行情、真实事件、健康、生产 Intelligence 或生产数据库。未启动/停止生产 Worker，未执行真实提醒或通知。Volume/VR20、split-only、finality、历史 PIT/vintage、正式 Universe 及其他既有 production blocker 全部保持原状。历史和因子证据缺失不能用合成信息变为 READY。

本任务不 add、commit、push 或同步 Git；六候选保留未暂存。下一步仅建议人工审查本六文件及原始失败/浏览器证据，再决定是否独立 Git 闭环，不扩展其他页面。
