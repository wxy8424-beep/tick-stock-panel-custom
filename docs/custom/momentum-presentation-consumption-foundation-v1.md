# HK/US Momentum Presentation & Consumption Foundation v1

日期：2026-10-16。基线：main / `3246c85562a5af577a54d818bb3d80284af3c9dd`。

**Presentation Foundation READY 不等于 Production Momentum READY。Production Input / Execution 仍 BLOCKED。**

## 审计和最小接入

现有 `/limit-ladder` 是 `frontend/src/custom/limit-ladder/extension.tsx` 注册的前端扩展。A股页面消费既有 `api.limitLadder` / `QK.limitLadder`，包含日期、涨跌方向、概念/行业/板块筛选、首板/连板卡片及封单监控。市场控件已有 `MarketSwitcherBar`，不建立第二套切换样式或后端取数路径。

新增代码位于 `frontend/src/custom/damon/momentum-ladder/`，复用原路由。局部L3边界仅为原页面外壳：原A股主体改名为内部 `AshareLadder`，原导出组件包裹市场容器，三个重复的静态CN-only控件由外壳共用控件替代。已有插槽不能表达页面级市场分支；没有复制原页面或新增扩展框架。

A股查询、筛选/排序、计算、缓存key、API、日期与卡片逻辑保持原样。访问过的A股树在本路由内隐藏保留，以保存日期、方向、筛选及卡片状态；其既有查询观察器仍保留，不声称后台CN查询停止。隐藏期间不渲染A股股票/维度/配置弹窗，避免portal覆盖HK/US预览；返回A股恢复原状态。直接打开HK/US URL不挂载A股树/查询。

## 市场切换与展示

同一路由支持 `?market=CN|HK|US`，保留其他URL参数；无/不支持的market按原A股入口处理。刷新/直接访问HK/US只显示对应预览，两个市场fixture不混合。A股是原生产路径；HK/US标题显式 `Momentum Preview`，每张卡片标注“合成示例 · 非生产”。

HK六组：T1 龙头、T2 强势、T3 强势、突破、连续上涨、放量。leader/follower/qualified momentum仅为展示角色；follower不表示因果跟随，theme不替代role。没有主题来源，一律“主题：暂无可靠数据”。

US六组：Momentum Leader、Breakout、Gap Up、Volume Spike、Consecutive Up、T2 / T3 Momentum。同一symbol可有多个标签并出现在多个组，不强制互斥。标签与分组输入来自合成案例，不运行classification Engine。未评分/证据不完整的案例独立展示，不静默丢失。

## Consumption DTO

`contract.ts` 定义 `MomentumLadderViewModel`、`MomentumItem`、metric/evidence/quality、artifact identity及groups。当前唯一模式 `FIXTURE_PREVIEW`，固定要求 `fixture_only=true / production=false / synthetic=true`；adapter和页面入口均检查该边界，拒绝生产标志、混合市场和未知group成员。

DTO包含market、固定trading_date、Universe/Calculation/Profile identity、items、groups、overall_status、warnings。item包含symbol/name/market、已提供的rank/tier/strength_score、可重叠labels、metrics、evidence和quality。质量使用 READY/PARTIAL/UNAVAILABLE/BLOCKED；趋势独立使用EXPANDING/CONTRACTING/UNCHANGED，不改变既有volatility_status质量字段。

卡片展示close、change_pct、连续上涨、3D/5D/10D收益、VR20、突破、波动率趋势、score/rank/tier、Data/Evidence Status。百分比消费小数制，仅展示时乘100。null展示 `—` 和原因；显式false展示“未突破”，显式0不当缺失。量与价格缺证据不会自动补0、false或正常。缺少评分输入的合成案例score/rank/tier均null，不重分配权重或生成partial score。

只按输入rank排序，null置后，同rank用symbol稳定展示，不产生或改变rank。同组/跨组展示不进行score、percentile、tier或分类计算。

页面展示Trading Date、market、Universe/Calculation/Profile、exact hash（有则显示）、Source、generated_at、available_at、finality、PIT和overall status。evidence在卡片原生可展开区域内；未知available_at保持null并说明，不能以generated_at或浏览器当前时间代替。源证明与fixture READY明确分开，永远不升级生产状态。

## Fixture isolation

固定合成数据位于 `frontend/tests/fixtures/momentum_ladder/index.ts`，由本地adapter导入用于preview bundle和测试；不是从运行时DB导出的数据。

- 日期固定 `2026-09-16`；合成generated_at固定 `2026-09-17T00:00:00Z`，不用“今天”。
- HK包含0700.HK/9988.HK/3690.HK；额外0005.HK/1299.HK仅测试PARTIAL/BLOCKED缺失展示。
- US包含AAPL.US/NVDA.US/MSFT.US；额外AMZN.US/META.US同样仅用于缺失案例。
- 数字、rank、tier、标签均为固定展示输入，不是行情、Engine结果、投资结论或真实排名。完整案例仅synthetic READY，缺失案例不进入有效评分/tier。
- fixture Universe identity显式fixture namespace，content_hash=null，不冒充已冻结的正式Universe。Calculation/Profile引用既有v1.1/v1.2身份与hash，只说明展示目标，不声称fixture通过生产Gate或是实际计算产物。
- loader返回独立clone；无fetch、provider、Query Cache、localStorage写入、IndexedDB或SQLite连接。没有fixture API，不连接Momentum Store，不生成Snapshot或Gate receipt。

## 与冻结后端契约的边界

ViewModel是独立frontend展示DTO，不是Snapshot schema升级，也不是Longbridge响应parser。`period_return_3d/5d/10d` 对应未来展示的 `return_3d/5d/10d` 槽，`volume_ratio` 对应未来展示的 `volume_ratio_20`；本轮不实现生产映射。`breakout_status`是独立fixture展示输入，不擅自把四个backend breakout指标合并成新定义。未来真实consumer需要明确映射与版本约束，不能靠同名字段自动接受生产数据。

没有修改momentum-daily/v1、v1.1，momentum-technical/v1.1、v1.2，旧Snapshot、Universe、Gate、评分权重、公式或canonical hash。没有backend/API/producer/worker/startup变化，也没有真实历史、quote、Archive或生产数据库读写。

仍保留：Volume/VR20 BLOCKED、split-only BLOCKED、corporate actions UNKNOWN、Daily finality PARTIAL（严格生产不通过）、PIT/vintage BLOCKED、正式HK/US Universe BLOCKED。不能通过界面案例解除任何供应商blocker。

## 验证与限制

新增jsdom集成测试覆盖：实际A股组件与原querykey、方向、日期、筛选/卡片状态保持；直接HK/US不挂CN查询、不发fetch；市场与URL参数隔离；T1/T2/T3、已提供rank、多标签、重叠分组、null/false/zero、质量及证据时间、固定日期；CN空/失败/loading仍能切换；fixture标志、clone、无持久化、稳定展示排序。

测试中的A股接口与行情均mock，不把它当真实A股运行或HK/US生产验证。前端组件验收不代表供应商证据已闭合。仅前端修改，Ruff不适用于TS/TSX；不为满足名义检查去运行无关backend或修改历史Ruff基线。不设置Polars线程覆盖。

验收：新增13项集成/contract案例；affected targeted共22 PASS（包括MarketSwitcher及既有跨页切换回归）；full Vitest 36文件/252 PASS；独立node:test 5 PASS；`pnpm build`（TypeScript + Vite）PASS。既有React Router future提示和大chunk警告保留，无Polars设置或worker变化。

首次沙箱Vitest因现有依赖realpath EPERM在收集前停止，随后同命令获批宿主执行。初轮宿主测试发现测试错误地比较动画中的完整HTML；修正为日期/筛选/组件身份断言，并为jsdom补齐scrollTo测试替身后通过，不改生产动画。未新增依赖或改变权限配置。未执行真实浏览器视觉验收，DOM交互测试与构建不能冒充截图验收。

无新依赖，无需要的数据源/GitHub调研。下一步仍是归档Longbridge官方供应商答复并重评生产输入，未获证据前不接通生产Momentum。
