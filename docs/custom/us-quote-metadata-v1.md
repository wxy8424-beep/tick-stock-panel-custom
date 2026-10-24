# 美股报价来源与获取状态 V1

Agent A / MAINLINE，2026-10-24。
基线：main / `8076f75848969114c747500025c216cdeef22fd5`。

## 实现与契约

现有 GET `/api/dashboard/us` 加法新增 `focus_quote_metadata`，不新增端点、Provider
调用、重试或缓存策略。不改变 CN/HK 页面、报价数值映射或全市场统计。
这是 L3 最小服务/响应接线，不建立通用元数据框架。

字段：symbol（与 focus_symbol 相同，可为 null）、status（available/empty/error/unavailable）、
source、source_reason、acquired_at、acquired_at_reason、reason。
匹配报价成功时，从有限观察样本的 quote section 提取来源与 updated_at，缺失值保持
null 并提供原因；非成功状态没有借用其他证券、榜单或历史批次的来源及获取时间。
错误 reason 只使用既有 error_category 的固定分类，不返回异常原文。

元数据在 Universe 分支替换 quoted/rows 之前构造。focus_quote 本身的选择过程、
_read 缓存和失败行为不变。Universe 的 stale/ready、completed_at 与该报价元数据无关。
acquired_at 是该有限报价区段成功获取完成时间；缓存命中保留原值，不用当前响应时间
覆盖它。它既不是供应商报价时间，也不是逐证券接收时间、延迟等级、过期阈值或 finality。

前端响应类型以可选字段兼容旧响应和旧缓存。详情分别展示报价来源、区段获取时间、
报价时间、聚合响应时间；来源缺失/时间非法或缺少时区均明确说明。元数据证券身份或
状态不一致时拒绝使用；没有匹配报价时也不采用 available 元数据。
available 仅表示已取得匹配报价，不代表实时或生产就绪。延迟等级与新鲜度仍未知。
保留缓存 HTTP 刷新失败提示与后端获取状态的区别，不修改代码查询、URL、榜单、
焦点恢复或既有宿主持久化。不宣称整站零副作用。

## 修改范围

- backend/app/services/us_dashboard_service.py：构造与报价绑定的元数据。
- backend/tests/test_us_dashboard.py：新增固定时钟/FakeProvider 测试，扩充原 API 断言。
- frontend/src/lib/api.ts：可选响应字段及独立 US 类型。
- frontend/src/components/dashboard/UnitedStatesDashboard.tsx：传递匹配上下文的元数据。
- frontend/src/components/dashboard/USQuoteSnapshotDialog.tsx：只读状态、来源与时间展示。
- 两个对应组件测试文件：身份、旧响应、null 原因、时间、旧响应竞态和缓存错误。
- 本文档。

不修改 Longbridge Provider、锁文件、依赖声明、全局查询策略或 Agent B 工作树。

## 本轮实际前端验证

命令、准确参数、退出码及完整日志位于忽略目录
`frontend/.vite/us-quote-metadata-v1/verification-results.json` 和对应 log。

| 检查 | 结果 | 退出码 | 墙钟耗时 |
| --- | --- | --- | --- |
| US Dashboard / 详情 / Dashboard 路由定向 | 69 PASS / 3 文件 | 0 | 38.12s |
| HK Dashboard / 布局 / 市场切换相关回归 | 20 PASS / 4 文件 | 0 | 7.73s |
| 完整 Vitest | 656 PASS / 57 文件 | 0 | 22.53s |
| 原生 Node 测试 | 5 PASS | 0 | 0.56s |
| pnpm exec tsc -b | PASS | 0 | 26.86s |
| pnpm build | PASS | 0 | 55.32s |

Vitest 明确排除 `.vite` 历史 QA 副本；两个 node:test 文件交给原生 Node 运行，未遗漏
原始断言。原有 Router future flag 和 Vite 大 chunk 警告保留，不修改配置掩盖提示。
新增 12 个详情用例，原迟到响应断言增强为同时验证元数据没有串证券；原报价、代码输入、
错误重试、市场切换及 CN 隔离断言保留。全部为合成响应，不等同真实生产链路验证。

## 初次后端验证：BLOCKED（历史记录，续跑结果见下文）

Python AST 语法检查：两个修改的 Python 文件通过，退出码 0；这不是服务/API 回归。
新测试覆盖匹配报价、请求次数、缓存时间、TTL 到期失败、空/缺证券、供应商不可用、
静态名称/币种失败、Provider 更换和 Universe 与焦点状态不同。原测试未删除或放宽。

实际测试命令 `python -m pytest tests/test_us_dashboard.py tests/test_hk_dashboard.py -q`
因可用解释器缺少 pytest，退出码 1，断言未执行。不得宣称这些测试通过。

用户要求由 Agent 处理环境后，在 QA 目录使用 Python 3.11 和原锁文件建立独立环境：

1. `uv python list --only-installed` 在受限缓存目录反复出现拒绝访问，已中断，退出码 1。
2. `uv sync --frozen ... --link-mode copy` 在项目打包依赖安装阶段修改 Windows PE
   临时启动器被拒绝，退出码 1，9.57s；记录 backend-env-setup.log。
3. 使用官方 `--no-install-project --no-build` 仅安装锁定依赖，避免无关项目打包，
   不修改权限和锁文件。下载 duckdb==1.5.3 时哈希不匹配，退出码 1，41.27s；
   原始 backend-env-dependencies.log 保留。

锁文件期望：`f4eff89c12c3a362efa012262e57b7b4ab904a7f79bad9178fe365510077abe8`。
实际下载：`0697b8f8209ffcaaa2b202575b8a2e243b8587e1393b4add94500dc29d32df43`。
原因尚未查明；没有跳过哈希、改锁、降版本或使用不匹配包，没有再次安装重试。
初次任务结束时，未执行后端集成及相关回归、完整后端、Ruff，不能声称后端验收完成。
恢复条件是可信、符合原锁文件的独立测试环境，不是放宽测试断言或依赖校验。

## 2026-10-24 续跑：测试环境恢复与后端离线验收

本轮产品源码与测试七文件 SHA-256 均与原候选清单相同，只追加本文验收记录。
没有通过改产品、改断言、改锁文件、降版本或关闭完整性校验解决环境问题。

1. 读取 PyPI 官方 JSON 元数据，duckdb Windows/Python 3.11 wheel 的哈希与原锁文件
   完全一致。一次普通下载声明 Content-Length=13,101,423，但只得到 5,816,320 字节，
   SHA-256 不匹配，退出码 1；该文件未安装。确认的是本次传输不完整，不把此观察
   当成此前全部 uv 故障的唯一根因。
2. 使用标准 HTTP Range 下载，每段严格要求 HTTP 206、准确 Content-Range 和长度，
   最后整包哈希/总长度必须符合原锁文件。DuckDB 的 13 段重组后完全匹配。
   其余五个大 wheel 也通过同样校验，保留每段和整包审计 JSON。
3. 从原锁文件 `uv export --frozen --extra dev --no-emit-project` 导出带哈希清单，
   用标准 Python 平台 tag 和 PEP 508 marker 选出当前环境的 66 个 wheel；全部下载后
   与锁文件校验一致。没有请求真实 Longbridge 服务，安装 SDK 不等于调用行情。
4. uv 默认安装仍优先访问原下载地址；完整本地 wheel 目录上的 uv 离线安装又在
   生成 pytesseract Windows 启动器时遇到 PE 资源拒绝访问，退出码 2，原始记录保留。
   不改权限，改用已有标准 pip，显式指定 QA 虚拟环境、`--isolated --no-index
   --find-links ... --require-hashes --only-binary=:all:` 离线安装，退出码 0，148.75s。
   隔离目录以外的 Python、配置、ACL 和 Agent B 工作树均不修改。
5. `pip check` 退出码 0：No broken requirements found。

新增实际验证（不是初次任务的历史结果）：

| 检查 | 实际命令（QA 环境 python） | 结果 | 退出码 | 墙钟耗时 |
| --- | --- | --- | --- | --- |
| 后端定向 | `-m pytest tests/test_us_dashboard.py -q --basetemp <QA>/pytest-targeted` | 31 PASS | 0 | 4.65s |
| 后端相关 | `-m pytest tests/test_hk_dashboard.py tests/test_market_session.py tests/test_quote_market_boundary.py -q --basetemp <QA>/pytest-related` | 96 PASS | 0 | 7.49s |
| 依赖一致性 | `pip --isolated --python <QA环境> check` | 无损坏依赖 | 0 | 见工具记录 |
| Ruff 两个修改文件 | `-m ruff check app/services/us_dashboard_service.py tests/test_us_dashboard.py --output-format json` | 4 项既有 BLE001 | 1 | 见工具记录 |
| Ruff 基线对照 | 相同配置对 Git HEAD 原文与当前文件逐项比较 | 基线 4、当前 4、新增 0 | 0 | 见工具记录 |

DATA_DIR 和两个 pytest basetemp 均为本轮 QA 专用目录。使用固定时钟、FakeProvider、
隔离数据库及本地 TestClient，不访问生产数据库、行情或模型；线程默认配置未调整。
Ruff 首次基线比较因 Windows 默认 stdin 编码不是 UTF-8 而失败，显式 UTF-8 后对照
通过；这是审计调用修正，不是产品或规则修改，原始失败留在工具记录中。

127 项后端测试全部通过，没有产品测试失败。完整后端套件本轮 NOT RUN。
原前端 69/20/656、Node、TypeScript 和构建结果沿用源码哈希一致的前次记录，
本次没有重跑，不把它们表述成本次新执行。浏览器也没有重试。
原始日志和下载校验结果仍位于同一 QA 目录，原环境失败没有被删除或覆盖。

## 真实 Edge：NOT EXECUTED

使用本轮 production dist、固定合成响应和原 A29 严格进程归属检查，尝试一次。
metadata-attempt1.json 保存 `loopback discovery timeout`，退出码 1。
CDP 连接阶段失败，未进入目标页，0 页面断言、无截图；桌面与 390px 尚未验证。
本轮浏览器 closed=true，HTTP 服务 closed=true，sockets=0。没有重试或放宽归属检查。
零页面请求/错误不是隔离通过证据；A29 历史总体 Browser PARTIAL 不被改写。

## 交付限制

后端离线验收门槛已解除；整体仍因真实浏览器未执行而为 PARTIAL。
不自动暂存、提交或推送，不继续第二项功能。
生产验证 Production validation = NOT VERIFIED。没有请求真实行情、模型或生产数据库。
Volume/VR20、split-only、finality、PIT/vintage、Universe/membership 等 blocker 保持。
宿主 SSE ERR_ABORTED 的历史原因仍未确认。本轮文档保留全部环境和浏览器原始失败。
