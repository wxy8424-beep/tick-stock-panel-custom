# 美股已返回榜单完整查看 V1

Agent A / MAINLINE，2026-10-24。基线 main：22c09f1dcd0fc1f8492acb26ab90a51092086655。

## 选型与范围

源码核查：/screener 的 HK/US 分支仍为策略 synthetic Preview，CN 的 market-snapshot
读取 enriched 日线数据，不能作为真实 US 筛选数据使用。现有 /api/dashboard/us 的
涨幅、跌幅和成交额榜单最多返回20条，而共享卡片只展示前8条。
本阶段完成已返回记录的只读查看，不把它包装成全市场选股，不修改筛选器生产语义。

L3 最小 US Dashboard 接线：新增 USRankingPanel 及测试，修改 US Dashboard 及测试、
Dashboard 路由测试，并新增本文，共六文件。无新端点、API/DTO、Provider、后端、
共享表格、MarketSwitcher、Layout 或其他市场组件变更。无依赖声明/锁文件变更。

## 行为与数据语义

美股看板新增三个入口，分别查看涨幅榜、跌幅榜、成交额榜已返回记录。复用现有
US Query 的区段数据，没有第二个 Query observer 或数据加载器。打开面板、本地
代码/名称搜索、三态排序、关闭都不触发业务请求、存储或通知。

仅展示实际返回的数据：代码、名称、快照价、涨跌幅、成交额、币种、报价时间。
涨跌幅沿用小数乘100语义；null、NaN、Infinity、无效时间不当零，已知零保留。
币种缺失不补 USD；成交额是原币数值，排序不是统一币种流动性排名，不换汇或跨币种求和。
来源与区段获取/生成时间取自选中区段，不能当成逐证券来源、报价时间或实时性证明。
运行时使用现有API返回值；测试替身是合成响应，不宣称已验证真实生产覆盖。

仅做代码格式、市场一致性检查并保留首条重复证券，不证明真实上市身份；拒绝其他
市场和无效格式，显示原始/保留/排除数量。接口不可用或结构错误时数量未知，显示—，
不把缺数据当零条。真实空结果与搜索无匹配分别显示。HTTP失败保留缓存说明，
切换报价时的 placeholder 榜单明确标记为前次记录，不宣称它是新响应。

复用 StockDataTable/useTableSort 的排序语义与原生表头按钮；数字缺失值在升降序中
均排末尾。表格由一个可聚焦的横向滚动区域承载，760px表格最小宽度只作用于内部。
搜索框打开时获焦；关闭榜单回到入口按钮。Ctrl/Meta/Shift/Alt点击保留原生链接行为。

点击证券复用原quote_symbol URL及报价详情。上一只/下一只只使用当前搜索、排序后的
列表，不能凭空添加证券。关闭详情保留面板筛选，关闭面板或切换榜单重置本地状态；
离开US后不残留面板。面板状态不写URL/storage，刷新时关闭；原详情深链不变。
原13卡片布局、前8条展示、CN/HK页面与其他Preview行为保留。

## 本轮最终验证

准确命令/参数、退出码、墙钟耗时在 frontend/.vite/us-returned-rankings-v1/final/
verification-results.json，原始log同目录。下表全部是本轮最终版本实际运行。

| 检查 | 结果 | 退出码 | 墙钟秒 |
| --- | --- | --- | --- |
| targeted-vitest | 77 PASS / 4 files | 0 | 12.03 |
| related-vitest | 20 PASS / 4 files | 0 | 7.26 |
| full-vitest | 664 PASS / 58 files | 0 | 20.50 |
| native-node | 5 PASS | 0 | 0.53 |
| typescript | PASS | 0 | 23.43 |
| production-build | PASS | 0 | 46.09 |

完整Vitest排除忽略目录.vite下的历史QA副本；两个node:test文件单独交给原生Node，
没有删除测试或遗漏原生用例。Router future flag和Vite大chunk警告保留。

新用例覆盖实际20条完整展示、三态排序及aria-sort、null/非有限数、0值、搜索、
混合市场和重复记录、来源/时间、空/错/缓存/placeholder、真实QueryClient下搜索
零请求/零新增storage、详情跳转与关闭恢复、CN返回清除面板状态。
原报价元数据、迟到响应、代码输入、五榜单入口和CN兼容断言保留。面板纯展示测试
对fetch/Storage/Notification做spy；不把这等同于Layout或整站无副作用。

### 保留的失败/修正记录

1. 先红用例：44 PASS / 1 FAIL，新增入口尚不存在；red.log保留。
2. 实现后首次相关：57 PASS / 1 FAIL，新增测试误用“沪深”按钮文本，实际是“A股”。
   仅修正新测试定位，不改产品行为、不弱化断言；targeted-initial.log保留。
3. 第一轮完整离线通过后，静态检查补齐不可用数量不得当0，以及单一滚动宿主两项
   边界并增加断言。初轮verification-results.json及log保留；最终重跑结果位于final/。

## 真实Edge：NOT EXECUTED

使用现有严格进程归属启动器、本轮初版dist和固定20条合成API响应，尝试一次，
rankings-attempt1.json记录loopback discovery timeout，exit1。未进入页面，0页面
断言，无截图；browser closed=true，HTTP closed=true，sockets=0。
此尝试早于最终数量/滚动边界调整，但未产生任何版本的页面证据。未重试、放宽归属
或调整权限。桌面/390px、真实Tab/Space/Enter和视觉结果均NOT EXECUTED。
jsdom焦点/语义断言不能替代浏览器；历史Browser PARTIAL不升级为PASS。

## 交付与限制

不运行真实行情、模型、生产数据库、筛选策略或交易；后端测试本轮NOT RUN（未改后端）。
Production validation = NOT VERIFIED。Volume/VR20、split-only、finality、PIT/vintage、
正式Universe/membership等既有blocker不变，宿主SSE历史原因未确认。

本轮只保留六文件未暂存候选，不自动提交/推送，不扩展真正全市场筛选或其他页面。
下一步审阅本候选；浏览器补验需可靠的隔离Edge环境，不能用重复启动或构建替代。
