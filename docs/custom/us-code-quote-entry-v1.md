# 美股代码直达报价 V1

Agent A / MAINLINE。实施及验收：2026-10-21 至 2026-10-22。
基线 main：`d16d56bfc1a2809f1b9e8b2a9afb529092ee088b`。

## 实现范围

本轮为 L3 小范围前端接线：现有插槽不能控制 Dashboard 的 URL 与弹窗生命周期。
仅修改 UnitedStatesDashboard、其组件测试和 Dashboard 路由测试，并新增本文。
不修改 CN/HK 主体、公共 Modal、API/DTO、后端、Provider、依赖或全局 Query 设置。

在美股市场切换栏下增加原生 form，显示标签“美股证券代码”、按钮“查看报价”，明确
“按代码查询，不支持公司名称搜索”。支持 AAPL、AAPL.US、大小写及首尾空白；裸代码
补 .US 后使用现有美股格式规则校验。保留 BRK.B / BRK-B.US 等已有语法。
明确的 .HK/.SH/.SZ/.BJ 后缀、空输入、URL、多代码及非法字符只报本地错误。
格式校验不证明证券已上市，也不保证接口有该证券报价。

不联想、不按键请求、不自动提交、不新增本地存储或通知。原生 Enter 通过 form 提交；
输入关联可见 label、提示及 aria-invalid/aria-describedby 错误。输入变化清除本地错误。
提交前聚焦原生提交按钮，使现有 Modal 的关闭焦点恢复到该控件。
使用 flex-wrap 和 min-w-0 允许窄屏换行；实际几何和原生键盘仍需真实浏览器证据。

## URL 与调用链

form submit → 规范化/校验 → 现有 quote_symbol URL → QK.usDashboard(symbol)
→ api.usDashboard(symbol) → 既有 GET /api/dashboard/us?symbol=...。

只复用已有聚合接口，不声称它是独立报价接口；运行时可能包含该接口原有其他数据聚合。
开发和验收全程使用合成响应，没有发起真实 Provider、行情、模型或生产数据库请求。

提交 push 历史条目并保留其他查询参数。代码入口使用空的来源证券列表，不伪造榜单
上下文，上一只/下一只禁用。相同证券再次提交不新增历史条目或主动重取。
关闭使用已有返回逻辑；刷新、直接 URL、历史前进/返回和按证券 Query 缓存仍沿用
既有实现。榜单五个入口及其导航没有改动。旧响应不能成为当前另一证券的详情。

不修改报价字段映射或新鲜度推断规则。无报价仍显示“接口未返回”，不回退其他证券；
不补造币种、来源、时间、昨收、财务或技术指标。没有新增 CN 日线、AI、报告、策略、
回测或交易执行入口。宿主和既有 US 布局持久化仍存在，不宣称整站零副作用。

## 本轮离线验收

全部命令从 frontend 执行；准确 argv、退出码、墙钟耗时和完整日志保存在忽略目录
`.vite/us-code-entry-v1/verification-results.json` 及对应 log。

| 检查 | 实际结果 | 退出码 | 墙钟耗时 |
| --- | --- | --- | --- |
| 定向：US Dashboard / 报价弹窗 / Dashboard 路由 | 57 PASS / 3 文件 | 0 | 11.80s |
| HK Dashboard / 布局 / 市场切换回归 | 20 PASS / 4 文件 | 0 | 8.44s |
| 完整前端 Vitest | 644 PASS / 57 文件 | 0 | 22.84s |
| 原生 Node 测试 | 5 PASS | 0 | 0.52s |
| pnpm exec tsc -b | PASS | 0 | 27.94s |
| pnpm build（tsc -b && vite build） | PASS | 0 | 47.85s |

Vitest 命令显式 `--exclude '**/.vite/**'`，避免收集被忽略的历史 QA 源码副本。
完整 Vitest 的两个原生 node:test 文件单独交给 `node --test`，没有遗漏或删除其断言。
React Router future flag 和 Vite >500kB chunk 警告保留，没有修改配置消除提示。

新增 20 个用例，使用真实 QueryClient 与 MemoryRouter，仅 API 层合成替身，验证规范化、
输入不请求、非法值不导航、错误可访问性、URL 参数保留、独立入口无榜单导航、重复提交、
历史前进/返回、关闭焦点、无报价不回退以及路由级 CN 业务 API 隔离。
路由测试验证提交后无新增 Storage.setItem/window.alert；源码没有引入通知调用。
旧延迟响应、API 错误/重试、null/数据语义、五榜单入口、直接链接、CN/HK 切换断言保留。
jsdom 的 requestSubmit 证明表单提交逻辑，不等同真实浏览器原生 Enter/Tab 或视觉通过。

### 失败与范围纠正历史

- 先在旧实现运行新增测试：19 FAIL / 96 PASS（共六文件，含被误收集的 QA 副本）。
  新用例因表单不存在失败，保留 red-tests.log；没有削弱旧断言。
- 首次实现后命令同样误收集 QA 副本，151 PASS / 12 文件，保留 targeted.log 的原始
  执行记录于工具输出；该数字不作为正式源码覆盖率。
- 后续明确排除忽略的 QA 副本后取得上表正式结果，不修改产品断言或排除失败产品用例。
  red-tests.log、工具执行历史和当前 targeted/full 日志分别体现修复前与正式验收结果。

## 真实 Edge 验收：NOT EXECUTED

本轮使用本轮 production dist、隔离合成 API 服务和原 A29 严格进程归属启动器，
尝试一次，保留 `.vite/us-code-entry-v1/code-entry-attempt1.json`。
连接本地 CDP 时 `loopback discovery timeout`，退出码 1，未进入目标页，0 页面断言，
没有本轮截图。没有重试、放宽进程归属、修改权限或用单元测试冒充真实浏览器结果。

原始记录确认本轮浏览器 closed=true、HTTP server closed=true、剩余 sockets=0。
零页面请求/错误源于尚未进入页面，不能作为页面隔离通过证据。
桌面/390px、原生 Tab/Enter、真实刷新/返回及焦点恢复本轮均 NOT EXECUTED。
A29 历史总体 Browser PARTIAL（包含驱动超时）不被本轮结果覆盖或升级为 PASS。

## 限制与交付

Production validation：NOT VERIFIED。既有 Volume/VR20、split-only、finality、
PIT/vintage、正式 Universe/membership blocker 均未改变。宿主 SSE ERR_ABORTED
历史原因未确认，不属于本轮产品修补范围。

本轮仅四文件候选，全部保留未暂存。不提交、不推送，不修改 Agent B 工作树。
浏览器补验需要可正常连接且可验证归属的隔离 Edge 环境；本轮不反复诊断或绕过阻塞。
