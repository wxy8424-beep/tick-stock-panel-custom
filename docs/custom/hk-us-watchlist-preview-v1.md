# HK/US Watchlist Preview v1

日期：2026-10-16。基线main / `b1cc59275974f86b8e5ee32267824c98a921be15`。项目仅为shy3130/tick-stock-panel二次开发，不涉及其他历史项目。

## 审计与最小实现

实际入口 `frontend/src/pages/Watchlist.tsx` 原有CN清单/分组/enriched/日K/分钟K查询、搜索、筛选、三态排序、卡片/表格、列配置、增删/分组/导入等逻辑。已有MarketSwitcher默认CN-only，不能直接用HK/US Dashboard的实际provider数据充当Preview。已有Momentum/指数Preview采用damon命名空间、固定fixture、URL市场和醒目非生产声明。

新文件位于 `frontend/src/custom/damon/watchlist-preview/`，独立固定fixture位于 `frontend/tests/fixtures/watchlist_preview/`。复用PageHeader、MarketSwitcherBar、StockDataTable、useTableSort、数字/百分比格式化与EmptyState/ErrorState；复用指数Preview的provenance类型，不引入通用框架、API、依赖或第二套数据接入。

局部L3仅为原页面外壳：原主体改名ChinaWatchlist，导出Watchlist包裹市场分支；原静态市场条改为原位置注入同款三市场条。现有toolbar插槽不能表达页面主体市场分支，不复制原CN页面。生产API/query key、计算、日期、筛选、排序、卡片及列配置等逻辑均保持原样。

访问过的市场panel在路由内隐藏保留，保存各自搜索/视图/排序及CN原状态；不改变原CN后台查询观察器。隐藏CN时其列配置/导入/股票/维度弹窗暂不显示，以免portal遮盖HK/US；回CN恢复原状态。直接HK/US地址不挂CN树和查询。

## Preview消费契约与交互

URL `/watchlist?market=CN|HK|US` 是市场状态来源，保留已有group和其他参数，浏览器返回按URL恢复；无market仍默认CN。HK/US不共享搜索、排序和视图状态，不混合排名，也不计算rank或score。

每份数据及每行沿用 PREVIEW、synthetic-fixture、data_mode=preview、is_production=false、is_investment_signal=false、fixture_only=true、synthetic=true。独立DTO保留symbol/name/market、price、fraction change_pct、volume/turnover的value/unit/reason、自选状态、缺失原因与evidence reference/generated_at/available_at。边界拒绝production标志、跨市场、非finite和无原因的缺失输入。

数据为固定synthetic fixture：HK 0700.HK/9988.HK/3690.HK；US AAPL.US/NVDA.US/MSFT.US。交易日固定2026-09-16，生成时间固定2026-09-17T00:00:00Z，available_at=null；不拿浏览器当前时间、SDK naive时间或生成时间推断历史可得性。

所有价格/涨跌/数量/金额仅为演示。成交量单位明确“合成数量单位（非供应商口径）”，不认证Longbridge数量合同；金额币种标合成。每市场第三只缺price/change/quantity/自选状态，显示破折号与明确原因，不能补零、false、空串或“正常”。显式0和false不是null，自选false表示“未自选（演示）”，null表示状态未知。百分比复用自选小数制，例如0.025显示+2.50%，不复用指数percentage-points口径。

页面始终标注“演示数据｜非生产行情｜不构成投资信号”，说明不代表用户真实自选。搜索仅筛当前fixture，表头复用原三态排序，null置后；支持表格/卡片切换。来源展开显示仅演示的证据引用、生成时间、未知availability和缺失原因。

添加/删除入口只读禁用并有说明；没有接到CN的mutation或真实搜索，不能添加、移除、导入真实自选，也不把预览状态写localStorage或数据库。fixture loader返回独立对象，不混合生产Query Cache。没有HK/US股票图表/详情生产请求。

## 生产边界

没有后端、Longbridge、QuoteService、Historical Provider、Archive或生产DB变更；没有Momentum Producer、生产Universe、真实信号或冻结Calculation/Profile/Universe/Gate/hash变更。Volume/VR20、split-only、PIT/vintage与正式Universe等blocker保持不变，finality仍PARTIAL，不因演示数字解除。继续前端开发不依赖供应商回复。

既有MarketSwitcher.integration.test仅更新“HK/US按钮禁用”的过时断言，保留原CN默认清单/标题断言并增加切换后CN树保持；Dashboard/Settings和其他原测试未改业务预期。

## 验证

新用例覆盖HK/US fixture、三市场切换、原CN query/filter保持、搜索/视图/排序隔离、缺失原因、声明与证据、固定时钟无关日期、独立对象、禁用mutation、无fetch/查询/Storage写入、空/错误/loading，以及URL返回。全部为隔离fixture/DOM验收，不是生产数据证据。

本轮验收：新用例11 PASS；相关前端20 PASS；完整Vitest 38文件/275 PASS；独立node:test 5 PASS；TypeScript/Vite build PASS。仅保留既有React Router future提示及大chunk警告。A股主体移除外壳/控件和隐藏弹窗的有限差异后，与基线逐字等价；七个计划文件敏感扫描无发现、whitespace检查通过。

本轮仅前端，Ruff不适用；不运行无关backend、不使用Polars覆盖。未执行真实浏览器截图验收，DOM/构建通过不冒充视觉或生产行情验收。
