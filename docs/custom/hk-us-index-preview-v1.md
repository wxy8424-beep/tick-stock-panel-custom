# HK/US Index Preview v1

日期：2026-10-16。开发基线：main / `3a5ac7db643e5ee7dfca0a8145db0bb5556e259c`。

本阶段完成HK/US指数页面Preview，不代表HK/US真实指数行情已经接入生产。

## 审计与边界

项目仍为shy3130/tick-stock-panel二次开发。实际入口为 `frontend/src/pages/Indices.tsx`，A股用 `api.indexQuotes`、`api.indexDaily`、`api.indexMinute` 和既有React Query键消费报价/日K/分钟K；固定核心四指数，支持指数选择、同步、日期范围及日K/分时联动。现有MarketSwitcherBar默认CN-only。

HK/US看板已有独立相关代码，但接通现有看板或复用其quote/index缓存会超出本轮生产边界。没有创建第二套provider，也没有从A股数据、`.SPX.US` anomaly/trace或盘中Archive取数冒充海外指数Daily。

沿用上一阶段Momentum Preview的damon命名空间、固定fixture、醒目合成/非生产声明与隔离测试风格；不把Momentum的READY/PARTIAL等质量状态改成行情模式。指数使用明确的PREVIEW模式，不另建通用状态框架。

这是小型L3页面外壳变更，已有扩展插槽不能注入指数页的市场主体分支。原 `Indices` 导出包裹 `IndexMarkets`；原A股主体只改为内部 `ChinaIndices`，原位置的静态市场控件改为注入的同款可切换控件。原A股所有取数、计算、转换、查询key、placeholder、分钟日期隔离、缓存、日期、卡片和交互逻辑保持原样，没有复制原页面。

## 文件与数据流

- `frontend/src/custom/damon/index-preview/contract.ts`：独立展示DTO、preview边界校验、非变异排序。
- `frontend/tests/fixtures/index_preview/index.ts`：固定HK/US合成fixture及返回独立clone的loader。
- `frontend/src/custom/damon/index-preview/Presentation.tsx`：复用MarketSwitcherBar、EmptyState、ErrorState、Activity图标及原指数列表/详情面板样式。
- `frontend/src/pages/Indices.tsx`：只接外壳和原位置控件。
- `frontend/src/pages/IndicesPreview.test.tsx`：新交互、contract与fixture隔离测试；已有Indices.test.tsx原样保留。

HK/US链路只有本地fixture → 独立DTO/校验 → 排序列表/详情卡片。没有API、fetch、真实行情请求、生产Store、数据库写入或provider选择。未来生产consumer须单独定义，不能切换布尔标志直接冒充生产。

## 市场、日期和状态

`/indices?market=CN|HK|US` 为市场状态来源。切换保留其他URL参数，前进/返回和重新挂载按URL恢复。无market时仍默认A股。新开无market的 `/indices` 仍按原默认行为显示A股，不使用全局watchlist/其他页面隐式市场推断。

访问过的市场panel在当前路由内隐藏保留，以保留各自指数选择/排序及A股日期/图表状态；直接HK/US地址不挂载A股查询。离开路由后再从历史记录返回，market按URL恢复。已访问A股后其原查询观察器仍在，本轮不修改其后台生产刷新行为；隐藏内容不是当前HK/US展示数据。

所有HK/US对象和每个index row均声明：

```text
status = PREVIEW
source = synthetic-fixture
data_mode = preview
is_production = false
is_investment_signal = false
fixture_only = true
synthetic = true
trading_date = 2026-09-16
```

日期固定，不读取浏览器当前日期，不推断真实交易session，不声明completed/final Daily或PIT。顶部与卡片标注Preview/合成/非生产；顶部明确“不构成投资信号”“仅用于界面验收，不代表真实行情”。每行合成数字不是原供应商响应或Engine计算结果。

HK：恒生指数HSI、恒生科技HSTECH、国企HSCEI。US：S&P 500 SPX、Nasdaq Composite IXIC、Dow Jones Industrial Average DJI、Russell 2000 RUT。这些是fixture展示代码，不是经本轮验证的provider instrument identity。

两市场独立fixture，显示名称/代码、最新值、涨跌、涨跌幅、开高低、昨收、fixture成交额与币种及状态。金额只代表示例金额；不认证真实指数成交额聚合合同。RUT故意不定义成交额，展示破折号与原因，不能补零。涨跌幅使用percentage points（1代表1%），匹配原指数显示习惯；不把其他模块小数制比例混入。

列表涨跌幅升降序、null置后、同值代码稳定展示，不修改原数组。选择列表项更新独立详情卡片；不展示伪造日K/分时图，不提供同步生产数据按钮。空/错误/loading状态沿用现有组件/文字风格，错误不降级到其他来源、不泄露异常或凭证。

## 验证

新增前端测试覆盖A股默认四指数/查询/同步/选中，HK/US直接进入和切换、字段和状态、固定日期、排序、null与zero、空/错误/loading、无网络/无CN查询、URL参数与前进/返回/离页回返、各市场选择排序隔离、A股panel/范围/图表保持，以及production/mixed/nonfinite fixture拒绝。原A股延迟乱序/缓存分钟日期测试原样执行。

仅前端修改，未运行无关backend测试；Ruff不适用于TS/TSX。本轮不安装依赖、不设置Polars线程环境、不修改现有native worker或任何配置。没有真实浏览器截图验收，DOM测试和构建不能代替视觉截图验收。

验收结果：新测试12 PASS；含原A股日期回归和MarketSwitcher的targeted共17 PASS；完整Vitest 37文件/264 PASS；独立node:test 5 PASS；TypeScript/Vite build PASS。既有React Router future提示与大chunk警告保留。原A股主体等价检查通过：移除导入/外壳/控件注入的有限差异后，与基线源码逐字一致。六个计划文件敏感扫描无发现，diff whitespace检查通过。

Longbridge volume/VR20、split-only、finality、PIT/vintage、正式HK/US Universe等生产blocker保持原样，未请求供应商/行情、未写生产数据库，也没有创建Momentum/Universe Producer。
