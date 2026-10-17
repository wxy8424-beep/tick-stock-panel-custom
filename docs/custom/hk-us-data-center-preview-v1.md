# HK/US 数据页面 Preview v1

## 范围与审计

基线 main / 746f9600bdc48ba9d77fb6e941e93d4676371747，开始时工作区及暂存区干净，独立核验 origin/main 与本地一致。

实际页面入口 `frontend/src/pages/Data.tsx`，CN 查询来自共享 hooks（capabilities/capability-matrix/settings/preferences/quote-status/quote-interval/data-status）、regime coverage、pipeline jobs/job、data sources 和 ext-data。DataStatus 是本地数据表/文件画像，不是供应商端点健康证明，也不是按 HK/US 证明的 Daily 完整性。

真实操作包括启动/取消管道、清除数据、更新定时计划、切换行情开关与间隔、调整指数批次/历史范围、手动获取指数、修正/补数、财务拉取与指标重算、扩展数据新增编辑删除。页面设置读取原有本地存储，并监听行情间隔及卡片可见性事件。上述业务函数、查询和设置组件未改动。

现有前端插槽没有 data 页面整页市场分流能力，L1 配置和 L2 已有插槽不能安全隔离真实同步路径；采用最小 L3 核心接线：Data 入口增加市场外壳，原函数主体移为 ChinaData 并接收市场控件，不复制核心页面。新专用模块放在 custom/damon/data-preview，复用 MarketSwitcherBar、PageHeader、StockDataTable、useTableSort、EmptyState 和 ErrorState；沿用 IndexPreviewProvenance 作为样稿 envelope，不改变后端/API/Query Cache 或冻结领域契约。上游合并复核点仅 Data.tsx 的 import、入口分流及 PageHeader 控件位置。

## 最新仓库证据

本次只读取项目源码和既有文档，不重新请求供应商，也不读取运行数据库来生成“最新覆盖”。材料优先级按较新已保存证据：

- [Longbridge Vendor Evidence Closure](longbridge-historical-vendor-evidence-closure-v1.md) 与 [Semantics Closure](longbridge-historical-semantics-closure-v1.md)：2026-10-15 的六只 HK/US 样本、两种调整模式各73根 Daily 读取成功。优先于旧 Provider Contract 中 US 尚未实测的结论。只证明当时有限读取与字段结构，不证明当前服务、全市场覆盖或生产集成。
- [Historical Provider Contract](hk-us-historical-provider-contract-v1.md) 和当前 `backend/app/data_providers/historical.py`：US yfinance 为显式 research factory；NoAdjust / ForwardAdjust 或 raw/auto-adjust 名称不能证明 split-only；旧 TLS/API 错误不是当前健康状态。工厂没有 Longbridge Momentum production adapter，本次不新增。
- [Immutable Calendar](immutable-trading-calendar-contract-v1.md) 与当前 market_calendar.py：HK/US 均有 2026-v1 的冻结 artifact；日历 READY 不证明数据存在、source finality 或某运行实例已安装。
- [Universe Foundation](momentum-universe-foundation-v1.md)：typed immutable Store/Foundation 已存在，但正式 HK/US production Universe 与历史 membership/vintage 未闭合。directory/watchlist/candidates/display set 不被升级。

静态质量矩阵保留：naive candle timestamp PARTIAL、OHLC 结构 PARTIAL、volume/VR20 BLOCKED、split-only BLOCKED、corporate actions UNKNOWN（以 BLOCKED + reason 表达）、Daily finality PARTIAL、历史 available_at 证据 UNAVAILABLE、strict PIT/vintage BLOCKED、正式 Universe/membership BLOCKED。日历 READY 仅限定静态 artifact。没有未知状态自动升级。

日历静态引用：

| market | identity / version | content hash |
| --- | --- | --- |
| HK | hk-cash-equity-official / 2026-v1 | 945fbd11e669fc27d1c76712969871a7151d854da1547f6c05fd71a4fa733b91 |
| US | us-cash-equity-official / 2026-v1 | cfb976ea41ff8037ab0dd5225f061dcb960976cd404bcd10eae2bb74a1084d76 |

这些是证据引用，不是第二套日历事实定义/运行 resolver，不参与计算或启动安装。文档或 canonical artifact 更新后需显式复核此静态展示。

## 数据模型、覆盖及时间

`DataPreviewData` 是固定的前端展示 envelope：PREVIEW / synthetic-fixture / preview / is_production=false / is_investment_signal=false / fixture_only / synthetic。它包含两种明确区分的行：

- STATIC_AUDIT：来源是带路径的仓库审计材料，不把结论宣称为合成供应商事实；其当前 coverage 全 null、updated_at/available_at null。历史成功样本数量仅出现在有限验证文字中，不写成生产覆盖数。
- SYNTHETIC_SAMPLE：独立手写覆盖元数据，source_id=synthetic-fixture、evidence=fixture:data:HK|US:coverage:v1，不包含或生成实际 OHLCV bars，不读取其他页面或 CN 统计。

每个数据源单独展示 SDK 能力、既有只读验证、生产集成与当前观测。health 和 production_observation 固定 null 并说明未观测，没有 HEALTHY/RUNNING 的动态健康结论。

HK 三个数据集（Longbridge、合成覆盖、Universe），US 四个（另含 yfinance 研究输入）。所有真实证券数、日期、交易日数量和字段比例未知，不用历史 archive 行数、旧报告的0行或 fixture 数量替代。生产覆盖卡始终显示“—（未测量）”。

覆盖样稿固定日期 2026-09-14..2026-09-16：HK 2只/2个合成覆盖日/1个缺日，US 3只/3个覆盖日/0个缺日。OHLC 字段比例均100%，volume 字段比例 HK75% / US100%；成交额比例 null。它们是独立预编写覆盖元数据，不是当前市场统计，也不证明量单位和复权语义。US 的已知缺日为0与真实未知 null 明确不同。样稿质量均 PARTIAL，因为调整方式、成交额比例和历史可得时间缺失。

trading_date 固定2026-09-16；覆盖样稿 updated_at 固定2026-09-17T06:00:00Z。页面 generated_at 固定2026-10-17T00:00:00Z，仅表示页面样稿编写时间。供应商静态报告 audit_date=2026-10-15；不虚构报告内单个字段的 publication/update timestamp。SDK5.2.0 candle 的宿主本地 naive datetime 不能直接当 UTC、available_at、source vintage 或发布时刻。每种缺失均附原因。

校验器拒绝混市场、重复身份、非有限/越界比例、非法时间形状、覆盖数异常、静态结果冒充当前覆盖/更新时间、虚构动态健康和错误 source/evidence 身份。它只校验前端展示契约，不新增 Provider 能力注册表、数据验证服务或生产 Input Gate。

## 交互与执行隔离

- URL market 控制 CN/HK/US，未知 market 回 CN 默认；保留无关 query 参数，刷新与浏览器返回可重现市场。
- HK/US 保留各自的搜索、数据类型/来源/质量筛选、列排序和详情，不共享过滤状态。支持数据集/字段/证券搜索，数字/范围未知值始终末尾。
- 筛选只作用数据集和详情，不隐藏或更改静态 blocker。无匹配、空样稿、Loading、Error 均保留显著声明；错误不回退生产状态接口。
- HK/US 的立即同步、修正/补数、清除、切换来源禁用，不连真实 API、存储、事件或通知。
- CN 内部查询、管道、统计、日期计算、筛选与操作不变。切离 CN 卸载 CN 树及副作用弹窗/事件监听器，返回时按原页面重新进入默认状态，不承诺保留未提交草稿/临时筛选。已经启动的后台 job 不被 Preview 自动取消/重启；原 history active_id 恢复逻辑保留。
- 无 backend/provider/QuoteService/Archive/Historical/DB/Momentum contracts/Producer/Input Gate/API/依赖变化；无新供应商请求。未等待、冒用或解除 Longbridge supplier blockers。

## 验收

新增12项测试覆盖 CN 原查询/同步/清除确认与跨市场退出；HK/US 独立 fixture、无生产 query/API/storage/notification；数据源能力/验证/集成/观测层次；静态质量状态与 exact calendar 证据；覆盖/null/reason；筛选/搜索/排序/详情；URL/浏览器返回隔离；固定时间/新对象；无效样稿拒绝；Loading/Error/空态。

验收结果：新增12项；相关 DataPreview / PaperPreview / RegimePreview 共35 PASS；最终完整 Vitest 45文件 / 355 PASS；node:test 5 PASS；TypeScript / Vite build PASS。仅既有 React Router future 与 chunk 大小提示。敏感扫描、CN 主体等价性、Preview 无生产 query/write 静态检查和 diff/staged review 作为提交前独立检查。未修改后端，不运行后端套件。

真实浏览器视觉验收未执行，build 不代表视觉验收通过。

**本阶段完成的是数据页面 HK/US Preview，不代表 HK/US 实时数据源健康、Daily OHLCV 覆盖或 Momentum 生产输入已经就绪。**
