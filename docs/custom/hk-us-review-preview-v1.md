# HK/US 复盘 Preview v1

## 审计与范围

现有 `/review` 入口是 `frontend/src/custom/review/extension.tsx`，通过扩展注册。
A 股主体读取 overview market、历史报告、偏好与全局流式 review store；包含 AI 生成、自动归档、龙虎榜、定时与推送设置。
本次沿用已有 Index / Watchlist Preview 的 URL market 参数、按访问保留页面状态、共享 MarketSwitcher 与合成 provenance 模式。
不修改后端、provider、QuoteService、Snapshot Archive、数据库、Momentum 契约或生产任务。

## 页面和交互

- 缺省及未知 market 保持 CN，HK/US 分别进入独立 Preview。保留其他 URL 参数，浏览器返回恢复市场。
- A 股原页面主体保留，只有市场外壳和非当前市场弹窗隐藏控制。原始日期、百分比单位、查询、生成、归档、筛选及报告行为保持。
- 首次直接进入 HK/US 不挂载 CN，不读取生产报告、偏好或流式 store，也不发起网络请求。
- 已访问的 CN 保留挂载以保留关注点和原有流式生命周期；在 CN 手动开始的任务仍按原有机制继续。Preview 不启动、取消或重置该任务。
- HK/US 采用同一摘要、报告和历史样稿布局；复用 PageHeader、MarketSwitcherBar、MarkdownRenderer、StockDataTable、排序、EmptyState 和 ErrorState。
- 支持名称/代码搜索、指数/股票筛选、仅缺失字段、列排序；市场之间日期、筛选和排序状态独立。展示集合不代表完整市场或真实 Universe。
- Preview 无生成、定时、归档、删除或推送操作，无股票详情行情入口。

## Fixture 和状态契约

文件：`frontend/tests/fixtures/review_preview/index.ts`。HK/US 独立数据，每次载入返回独立对象。
日期固定为 2026-09-16、2026-09-15，不读取系统日期、不推断交易日。
报告为手写合成样稿，不是 AI 输出或供应商市场解释；样稿生成时间也固定，available_at 为 null。

每个 envelope / report / observation 均声明：

- status = PREVIEW
- source = synthetic-fixture
- data_mode = preview
- is_production = false
- is_investment_signal = false
- fixture_only = true；synthetic = true

HK 示例包括恒生、恒生科技、腾讯、阿里、美团；US 包括 S&P 500、Nasdaq Composite、Dow Jones、Apple、NVIDIA、Microsoft。
代码仅是展示标识，不作为 provider 请求身份。
涨跌幅采用 fraction，使用共享 fmtPct；不复用 CN overview 的百分数单位模型。
成交额附明确合成币种单位。缺失字段保留 null、显示原因与破折号，不补零；真实零值正常显示。
逐行 evidence_reference 以及报告来源、固定生成时间、未知历史可得时间可查看。
校验拒绝生产标识、混合市场、重复身份、非有限数值和缺少解释的空指标。

统一声明：**演示数据｜非生产行情｜不构成投资信号**。
仅用于界面验收，不代表真实行情、AI 分析、排名或投资建议。空数据、加载中及错误均不回退生产接口。

## 文件边界

- `frontend/src/custom/damon/review-preview/contract.ts`：前端 Preview 类型、校验，复用既有 provenance 类型。
- `frontend/src/custom/damon/review-preview/Presentation.tsx`：市场外壳、合成报告展示和列表。
- `frontend/src/custom/review/extension.tsx`：原页的最小市场外壳接入。
- `frontend/src/pages/ReviewPreview.test.tsx`：CN 回归、HK/US 隔离、日期、列表及状态测试。

## 生产边界与待办

本阶段不请求 Longbridge、不写生产数据、不创建 Momentum 或 Universe Producer。
Volume / VR20、split-only price basis、historical PIT/vintage 仍 BLOCKED；corporate actions UNKNOWN；Daily finality PARTIAL；正式 HK/US Universe 未建立。
主题/催化剂无可靠数据，不从名称和涨跌推断。供应商确认继续独立跟进，不影响前端 Preview 开发。

**复盘 Preview 完成不代表 HK/US 真实复盘数据已经接入生产。**

## 验收

2026-10-16：复盘新增 9 项测试通过，与自选相关回归共 20 项通过；完整 Vitest 39 个文件、284 项通过，独立 node:test 5 项通过；TypeScript 与 Vite build 通过。
保留既有 React Router future flags 提示与 Vite 大 chunk 警告，无本阶段构建错误。
另核验原 CN 主体在排除已审查的市场外壳/弹窗可见性改动后完全一致；敏感模式扫描与 diff check 通过。
未做真实行情、生产接口或浏览器截图验收；测试中的数据均为隔离 fixture / mock。
