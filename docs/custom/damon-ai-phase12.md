# Damon AI Phase 1.2：真实模型文字对话候选

开发基线为 `d2e62cbd4d7c0e06a896c5ef877ff62981f3dc35`，分支为 `feat/damon-ai-phase1`。不迁移首页，不接入语音、研究工具或生产行情。页面默认显式离线 Mock；切换“真实模型文字”才加载 Profile，发送文字才调用模型。此处真实表示调用路径，绝不表示连接已经验收。

## 审计与复用

- `ai_provider.py` 原入口支持 OpenAI-compatible Chat Completions、Responses、Codex CLI；原有全局读取和旧助手工具循环不用于 Damon。新增显式参数入口复用客户端工厂、URL 规范化及两种正文解析器，不修改旧助手的默认参数、重试和全局配置行为。Damon 要求明确成功终态，拒绝空流、截断、仅推理、非成功 EOF。
- `secrets_store` 为现有 `data/user_data/secrets.json` 明文存储，声明 mode 0600，原子写入，进程内 RLock 保护合并写入，mtime/size 缓存和深拷贝；优先于 Settings/.env。它不是加密保险库，不保证跨进程写锁或 Windows ACL。Damon 不增设凭证库，不回传遮罩片段/秘密引用。
- Profile 解析一次读取深拷贝，冻结模型、协议、地址、Key、UA 和输出/上下文预算；后续配置或选择变化不影响在途轮次。无需将整个旧 Provider 改成全局可切换上下文。
- 复用 FastAPI Damon 扩展注册和原 `/api/` 认证中间件。成本端点额外核验现有密码会话；无密码时仅沿现有本机/内网主人模式放行。Bearer Token 尚无 Damon 成本权限，明确拒绝。会话主体为验证后的 cookie 哈希，或无密码模式的共享 local-owner；不保存 cookie/请求头。
- 前端继续使用现有 QueryClient、`QK.damonProfiles` 和 `lib/api.ts`。Query 缓存只放安全 Profile 元数据；消息仅组件内存，不落盘。输出按纯文本渲染。

## 最小服务端 Profile 配置

管理员通过已有服务端配置维护 `secrets_store` 中的 `damon_profiles` 数组（最多 16 项）；本阶段不增加 Profile 编辑/连接测试 HTTP 接口，不自动探测服务。以下仅为无凭证结构示例，模型名称须换成该服务实际支持的标识：

```json
{
  "damon_profiles": [
    {"profile_id": "damon.fast", "display_name": "快速模型", "model": "configured-fast-model", "protocol": "chat_completions", "config_ref": "existing_ai", "credential_ref": "ai_api_key", "enabled": true, "text_stream": true},
    {"profile_id": "damon.research", "display_name": "另一模型", "model": "configured-second-model", "protocol": "responses", "config_ref": "existing_ai", "credential_ref": "ai_api_key", "enabled": true, "text_stream": true}
  ]
}
```

这些 Profile **共享现有 AI 服务地址和凭证**，不能在各 Profile 自定义 endpoint 或秘密引用。不同服务/不同 Key 的 Profile、管理界面、加密存储属于后续工作，不能把本结构说成已支持。缺少该数组时生成 `damon.default`，复用旧配置；Codex CLI 默认 Profile 禁用，不执行任何子进程。不改变旧助手使用的模型。

`GET /api/custom/damon/ai/profiles` 只返回 ID、展示名、模型、协议、enabled、text_stream 和 configured；configured 仅表示凭证配置存在，不代表连通性。服务地址仅允许 HTTPS，无 userinfo/query/fragment；模型 HTTP 客户端禁用重定向和 SDK 自动重试，禁止转发凭证到跳转目标。已有 HTTP 本地网关本阶段会被 Damon 拒绝，旧助手不受影响。

## 流与取消

`POST /api/custom/damon/ai/chat` 仅接受 profile_id、可选 conversation_id 和 user/assistant messages。禁止附加 endpoint、Key、credential_ref、system 或工具消息。手动有界解析 JSON，拒绝时不回显 Pydantic input；所有错误为固定分类和随机 request_id。

服务器分配 conversation_id、turn_id、request_id。NDJSON 事件包含三个 ID 和递增 sequence：start、delta、ping、done、error、cancelled。start 还带本轮 profile_id，done 必须 code=completed。没有成功终态不能视为成功；失败/停止的半截回复不进入后续历史。前端按本地请求代次及服务器 ID/序号拒绝重复、倒序、迟到事件，完整累积正文。

- JSON 请求体最多 64000 字节，读取期限 5 秒；最多 24 条消息，用户单条 8000 字符、助手单条 16000 字符、合计 20000 字符，必须 user/assistant 交替并以 user 结束；估算 token 与快照上下文预算再次校验。UI 单条输入 2000 字符。
- 输出最多 16000 字符、模型输出预留复用现有配置并钳制到 1–4096 tokens；队列最多 8 片，前端总传输最多 8000000 字节、单帧最多 20000 字符（允许一个网络 chunk 包含多帧）。当前 Key 和完整服务地址在跨片缓冲中替换；包含本轮 Key 的输入拒绝。此保护不代表任意敏感信息 DLP，也不应向模型提供其他凭证。
- 默认单轮 60 秒，包括等待上游；心跳 10 秒，浏览器传输 70 秒兜底。cleanup 另有 0.2 秒等待额度。取消、超时、断开都会取消上游 task，SDK stream/client 在 finally/context manager 释放。
- `POST /api/custom/damon/ai/cancel` 接受同主体的 conversation_id/turn_id，幂等取消请求不反复打断 cleanup；结果只声明 cancel_requested 和 finished/still_running。请求已不存在时安全拒绝。取消确认与断开有竞态时 UI 明示退出状态未确认，不宣称强杀。
- 协程无法通用强杀。忽略取消或 cleanup 不退出的 task 保留活动准入，不能在同会话继续调用；全局最多 8 个、同主体最多 2 个。task 实际退出后才释放。
- 每会话最多 20 次派发，每主体每小时最多 60 次，失败/取消不退款，换 conversation 不重置主体预算；最多 256 会话及主体预算项，空闲会话 30 分钟过期，满额拒绝。

## 限制与部署前置条件

会话归属、准入和预算是**单进程内存状态**。当前单 worker 使用；重启会丢失历史计数。多个 worker、多个实例、持久配额、重放幂等和跨设备会话恢复需要共享权威存储，当前没有提供，不应直接扩展为多 worker 成本服务。无密码内网模式沿用项目原安全边界，多人使用前应初始化密码。

仅转发用户文字和成功对话历史，不查询或向模型注入 CN/HK/US 数据。Preview fixture 不构成证据；输出没有已验证研究报告/行情资格。现有只读策略默认工具注册表保持空，不使用旧 dispatcher，不执行交易、回测、同步、命令、文件或任意 HTTP 工具。

真实 STT/TTS、Realtime、真实服务连通性、延迟/费用、浏览器人工视觉验收均未验证。统一语音接口保留在 `voice.ts`，本阶段文字协议和 Mock 语音事件分开；后续语音适配必须显式关联真实会话/轮次和取消，不能直接把 Mock 音频事件开放。

取消的 finished 仅表示本地上游请求及清理任务已退出，不保证远端服务已停止计算或计费。认证主体当前对应登录会话（无密码时共享 local-owner），不是跨登录的账户成本配额。

测试使用假模型/假 SDK、隔离 Settings DATA_DIR 和临时存储；不得依赖真实 Key。真实服务操作是部署后的显式用户动作，本轮开发验收没有发起。

## 原候选本地验收记录（2026-10-18，以下 P2 修复前）

本次最终后端相关回归 **244 passed, 0 failed**；最终前端 Vitest **53 文件、406 passed, 0 failed**；`pnpm build`（含 `tsc -b`）通过，有大 chunk 警告。Damon 定向 Ruff 通过；共享 `ai_provider.py` 相对 HEAD 的 Ruff 为基线 1 项、候选 1 项，诊断内容无新增，未清理该历史问题。

后端运行前将 `TICKFLOW_ENV_FILE` 指向不存在的临时路径、`DATA_DIR` 指向唯一临时目录，并清空进程内 `AI_API_KEY`、`TICKFLOW_API_KEY`；没有读取生产 secrets 或运行应用 lifespan。实际验证命令：

```powershell
# backend/
uv run --frozen --no-sync --offline pytest tests/test_damon_chat.py tests/test_damon_ai.py tests/test_ai_provider.py tests/test_ai_responses.py tests/test_secrets_external_edit.py tests/test_custom_assistant.py tests/test_custom_assistant_sessions.py tests/test_extensions.py tests/test_quote_market_boundary.py tests/test_market_provider_contracts.py tests/test_anomaly_intelligence.py -q
uv run --frozen --no-sync --offline ruff check app/services/damon_ai app/api/damon_ai.py tests/test_damon_ai.py tests/test_damon_chat.py
# frontend/
$testFiles = @(rg -l 'from .*vitest' src -g '*.test.ts' -g '*.test.tsx')
pnpm exec vitest run --maxWorkers=2 @testFiles
pnpm build
```

测试包括 Profile 不存在/禁用/能力或协议不支持、输入与秘密拒绝、地址安全、显式 SDK 无重定向/重试、跨片脱敏、不同模型并发与快照、异常终态/EOF、超时、断连、取消不配合、活动准入和预算、长助手历史、重复/迟到事件、无效取消回执、较大网络 chunk 的多帧解析、卸载与模式切换。旧助手、扩展、CN 隔离和 HK/US Preview 测试均为上述离线回归的一部分。

**NOT RUN**：全后端测试套件、node:test 套件、全仓 Ruff、真实模型/语音/行情连通性、生产数据库及浏览器人工验收。早前自动审批服务因用量额度未执行的批次没有计入通过数；正常审批恢复后已执行上述最终验证。

## 本轮文件清单

修改：

- `backend/app/api/damon_ai.py`
- `backend/app/services/ai_provider.py`
- `backend/tests/test_damon_ai.py`
- `docs/custom/damon-ai-phase1.md`
- `frontend/src/custom/damon/ai/DamonAIPage.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/queryKeys.ts`

新增：

- `backend/app/services/damon_ai/chat.py`
- `backend/app/services/damon_ai/profiles.py`
- `backend/tests/test_damon_chat.py`
- `docs/custom/damon-ai-phase12.md`
- `frontend/src/custom/damon/ai/TextChatPanel.tsx`
- `frontend/src/custom/damon/ai/TextChatPanel.test.tsx`
- `frontend/src/custom/damon/ai/text.ts`
- `frontend/src/custom/damon/ai/text.test.ts`
- `frontend/src/custom/damon/ai/transport.test.ts`

## 两项 P2 最小修复与离线验收（2026-10-18）

本节对应 `feat/damon-ai-phase1`、起始 HEAD `d2e62cbd4d7c0e06a896c5ef877ff62981f3dc35` 上的后续修复。起始 7 个修改和 9 个新增候选全部保留；不提交、不推送，不改 main、路由、旧助手 dispatcher、QuoteService、市场 Provider 或 HK/US Preview。

### SDK 日志安全

实际审查安装版本为 OpenAI 2.38.0、HTTPX 0.28.1、httpcore 1.0.9。HTTPX 的 `httpx` logger 在 INFO 记录完整请求 URL；`openai._base_client` 在 DEBUG 记录请求选项、URL、响应头及异常；httpcore 的 `connection/http11/http2/proxy/socks` logger 在 DEBUG 通过 Trace 格式化请求、响应头及异常。

新增 `app/services/ai_sdk_logging.py`，对这些 SDK 的具体 logger 安装拒绝记录的 filter；不能只过滤父 logger，因为 Python logger filter 不向子 logger 传播。适配器导入时预装当前版本具体 logger，并在客户端创建时补充已创建的同 namespace 子 logger。filter 不依赖日志级别，即使根日志或 SDK logger 设为 DEBUG，也在任何 handler 接收之前拒绝 SDK 记录。主应用日志初始化、业务 logger、模型请求参数及旧助手默认设置保持不变。

取舍：上述三个 SDK namespace 的底层日志在进程内被抑制，包含其他调用方的同 namespace 诊断；应用业务日志继续可用。不是全局关闭 logging，也不是原始日志落盘后再替换敏感字符串。SDK 升级必须重新核对具体 logger 名称和离线传输测试，不能对未来未知 logger 作无条件安全承诺。

`tests/test_ai_sdk_logging.py` 使用真实已安装的 SDK 和实际 `stream_snapshot_text` 入口，两种协议共用 `_openai_client`。仅注入 HTTPX MockTransport，分别覆盖 INFO/DEBUG、成功/400 错误，共 8 个请求用例；额外 1 个用例覆盖具体 logger 的 CRITICAL 记录及真实 httpcore Trace 的头部/异常格式化。MockTransport 不经过 httpcore 网络 I/O，因此 Trace 单独离线验证，不能冒充真实网络链路验收。

测试观察并断言过滤器确实收到 HTTPX INFO/OpenAI DEBUG 记录，同时用 caplog 检查放行日志不含假 Key、Bearer 内容、敏感 URL 标记、请求/响应正文。业务日志正向断言仍通过。socket、事件循环连接、生产数据库、子进程和 secrets_store 读取在日志测试中被禁止；全部请求到假 Transport，不使用真实 Key。

### 正文计量与失败终态

正文上限固定为 **16000 Unicode 码点**，与 Python `len(str)`、前端 `Array.from(text).length` 对齐；不是 UTF-16 单元、UTF-8 字节或用户可见字素数量。后端契约显式声明常量，同时限制 Provider 原始正文及脱敏后入队正文，避免短字符串替换扩大输出后越界。超限返回 `error/output_limit`，不得发送 `done`。

前端在通过当前轮次 ID/序号检查后，将超限轮次设为 `terminal=true/error=output_limit`，保留此前正文作失败展示但不加入成功历史。页面立即 Abort 传输并抛出固定错误，使 API reader 进入取消和释放路径。退休轮次的重复、迟到 delta/done 不再处理；重试只提交成功历史。文本格式非法也明确失败，不静默跳过后接受成功。

Damon NDJSON 帧的既有 20000 限制同步采用码点语义，以允许合法的 16000 emoji 单帧；正文上限未增大，总传输 8000000 字节上限不变。测试覆盖中文、emoji 的 15999/16000/16001 边界、跨 delta 超限、超限后 done/重复/迟到事件、真实 reader 取消、页面 Abort 与重试历史隔离，以及脱敏扩大输出的服务器拒绝。

### 本轮实际验证

所有后端命令均设置 `TICKFLOW_ENV_FILE` 为不存在的临时路径、唯一临时 `DATA_DIR`，并将当前进程的 `AI_API_KEY/TICKFLOW_API_KEY` 置空，不读取生产配置文件，不安装依赖。命令工作目录分别为 backend、frontend：

```powershell
# backend: 最终代码回归，260 passed, 0 failed（其中日志安全 9 个，新增 Unicode/输出边界 7 个）
uv run --frozen --no-sync --offline pytest tests/test_ai_sdk_logging.py tests/test_damon_chat.py tests/test_damon_ai.py tests/test_ai_provider.py tests/test_ai_responses.py tests/test_secrets_external_edit.py tests/test_custom_assistant.py tests/test_custom_assistant_sessions.py tests/test_extensions.py tests/test_quote_market_boundary.py tests/test_market_provider_contracts.py tests/test_anomaly_intelligence.py -q --tb=short

# frontend: 6 文件、33 passed, 0 failed；随后构建包含 tsc -b，通过
pnpm exec vitest run src/custom/damon/ai src/extensions/ExtensionRouteRecovery.test.tsx --maxWorkers=2
pnpm build

# backend: 下列 5 个文件 Ruff 全通过
uv run --frozen --no-sync --offline ruff check app/services/ai_sdk_logging.py app/services/damon_ai/chat.py app/services/damon_ai/contracts.py tests/test_ai_sdk_logging.py tests/test_damon_chat.py
# 共享 Provider：HEAD 基线与当前候选各 1 条既有 BLE001，分别在 910/966 行，未修改
git show HEAD:backend/app/services/ai_provider.py | uv run --frozen --no-sync --offline ruff check --stdin-filename app/services/ai_provider.py -
uv run --frozen --no-sync --offline ruff check app/services/ai_provider.py

# repository
git diff --check
```

修复前新增日志测试 8/8 复现泄漏；前端状态复现 4 failed/1 passed。首次沙箱命令遇到 Python Access Denied 和 Vitest EPERM，没有计为通过；批准的沙箱外运行才形成复现和验收结果。中途回归 133 passed/6 failed：6 个新增测试在 task 完成回调执行前检查准入释放；补充一个事件循环调度点，并保留 task 已结束、准入已释放的断言。后续 259 passed；补充脱敏膨胀边界后最终 260 passed。

构建保留大 chunk 警告，路由测试保留 React Router v7 future flag 提示；无本轮新增 Ruff 诊断。候选文件高置信秘密模式扫描 19 文件、0 命中（扫描不是完整 DLP），完整修改范围和未跟踪文件已审查。`git diff --check` 通过；未暂存。

本轮新增文件：`app/services/ai_sdk_logging.py`、`tests/test_ai_sdk_logging.py`。本轮继续修改既有候选：`app/services/ai_provider.py`、`app/services/damon_ai/chat.py`、`tests/test_damon_chat.py`、前端 `text.ts/text.test.ts/TextChatPanel.tsx/TextChatPanel.test.tsx/transport.test.ts`、`frontend/src/lib/api.ts` 和本文档；另在既有 `app/services/damon_ai/contracts.py` 中声明正文常量。上述后端路径相对 backend，前端 Damon 文件相对 `frontend/src/custom/damon/ai/`。

**NOT RUN**：全后端、全前端 Vitest、node:test、全仓 Ruff/ESLint、人工浏览器验收及任何真实模型/语音/行情请求。不访问生产业务数据库；无真实网络、无真实凭证读取。未解决的原边界仍包括明文秘密存储、单 worker 内存配额、远端计费不可由本地取消保证；本轮未扩大这些能力。

待人工审阅后，才决定是否授权真实模型冒烟；本轮没有执行连接。结束时分支和 HEAD 不变，工作区为 8 个已修改、11 个未跟踪文件，共 19 个候选，暂存区为空。按本轮最小修改范围要求，持久状态和待办记录于本文，不更新项目外记忆文件。

## 浏览器本地超时分类与扩大离线验收（2026-10-18）

本节是后续一轮实际运行记录，不沿用上节通过数。分支和 HEAD、19 个候选均核验无误。本轮只修改 `frontend/src/custom/damon/ai/TextChatPanel.tsx`、其 `TextChatPanel.test.tsx` 和本文档，不新增仓库文件。

### 终态语义

- 浏览器兜底保持 70000ms，分类为 `local_timeout`，提示“浏览器本地超时（70 秒）”。先递增请求代次、将轮次设为失败 terminal、更新 UI 和清理定时器，再 Abort。即使 Abort 同步触发旧 done 或网络异常，旧请求也不能覆盖该终态。
- 服务端 `timeout` 提示“服务端超时”，`upstream_error` 提示“上游服务错误”；收到服务端终态立即清理本地定时器，保留服务器分类。
- 主动停止先退休请求和轮次、清除定时器，再 Abort；仍区分本地停止与上游 finished/still_running/未确认。停止与本地超时先到者生效，另一方不再取消或重复报错。
- 传输拒绝且尚无终态时，安全的 `request_failed_<HTTP状态码>` 标记为 `request_error`，网络失败标记为 `connection_error`，并退休轮次，不回显原始异常。未完成正文不写成功历史；重试不会携带失败正文。finally 和卸载继续释放本地资源。

新增 8 个用例（面板合计 14 个）：69999/70000ms 边界、Abort 同步旧 done、超时后正文/done、失败历史与重试、服务端 timeout/upstream_error 不被覆盖、停止/超时两种先后顺序、网络/HTTP 拒绝及迟到事件、实际 NDJSON reader cancel/releaseLock。测试使用假时钟和假 fetch；reader 用例调用实际 API 流解析器与 Web Streams，在 Abort 时让假响应流失败，验证真实 reader 的 finally 清理。

首轮 Damon/路由定向 39 passed、1 failed：新测试夹具先锁定 body 再构造 Response，导致构造阶段连接失败；调整为先构造 Response 再取得 reader，并保留全部原断言。随后完整 Vitest 包含上述定向用例全部通过。

### 本轮已完成验证

```powershell
# frontend：依据实际导入区分 Vitest 与 node:test，最终完整 Vitest 53 文件 / 420 passed / 0 failed
$testFiles = @(rg -l 'from .*vitest' src -g '*.test.ts' -g '*.test.tsx')
pnpm exec vitest run --maxWorkers=2 @testFiles
# node:test：5 passed / 0 failed
node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts
# TypeScript tsc -b + Vite：通过，仍有大 chunk 提示
pnpm build

# backend：唯一临时 DATA_DIR、不存在的 TICKFLOW_ENV_FILE、AI_API_KEY/TICKFLOW_API_KEY 置空
# 本轮重新执行，260 passed / 0 failed，含日志安全 9 项
uv run --frozen --no-sync --offline pytest tests/test_ai_sdk_logging.py tests/test_damon_chat.py tests/test_damon_ai.py tests/test_ai_provider.py tests/test_ai_responses.py tests/test_secrets_external_edit.py tests/test_custom_assistant.py tests/test_custom_assistant_sessions.py tests/test_extensions.py tests/test_quote_market_boundary.py tests/test_market_provider_contracts.py tests/test_anomaly_intelligence.py -q --tb=short
# 本轮无 Python 修改；额外复核现有候选的五个文件，全部通过
uv run --frozen --no-sync --offline ruff check app/services/ai_sdk_logging.py app/services/damon_ai/chat.py app/services/damon_ai/contracts.py tests/test_ai_sdk_logging.py tests/test_damon_chat.py
# 共享 Provider 仍为既有 BLE001 1 条（966 行），未修改、未自动修复
uv run --frozen --no-sync --offline ruff check app/services/ai_provider.py
```

完整前端包含 Damon/路由 6 文件、41 个测试、CN Dashboard、HK/US Preview 和旧助手相关断言。此前一轮全前端为 419 passed；补充 HTTP 拒绝与网络失败区别后，最终完整重跑为 420 passed，构建再次通过。React Router future flag 提示仍存在，不代表浏览器人工验收。源码范围复核未发现主线业务、路由、依赖或后端改动。

SDK 日志修复本轮保持不变：OpenAI、HTTPX、httpcore 具体 logger 在进程内抑制，包括其他调用方同 namespace 的底层诊断；应用业务 logger 不受此策略影响。OpenAI 2.38.0 / HTTPX 0.28.1 / httpcore 1.0.9 的当前清单和实际文字协议已被既有代码及本轮离线测试覆盖。SDK 升级须再次搜索 logger、复核新建子 logger 及真实 SDK + MockTransport 日志捕获测试；不能把当前清单当作未来所有 SDK 路径的保证。

### 完整后端结果与受控诊断

本轮尝试完整后端：**4250 passed、2 failed、6 skipped、1 xfailed、214 warnings，328.65s**，退出码 1，不得报告全量通过。本次没有 mining worker 原生退出失败；这不证明此前记录的原生退出风险已消失。

使用 `uv run --frozen --no-sync --offline python -c <内存脚本>`，脚本先包装 `socket.socket.connect/connect_ex`：tuple 地址仅允许 `127.0.0.1/::1`，外部连接直接抛出固定 AssertionError，随后调用 `pytest.main(["tests", "-q", "--tb=short"])`。环回用于事件循环/测试自身；子进程不自动继承 Python 内存补丁。全量使用唯一临时 DATA_DIR、不存在的环境文件、空 AI/TickFlow Key，本轮未额外设置 Polars 线程参数，未启动真实服务。外联闸门是测试保护，不能冒充生产网络隔离实现。

两个失败分别为：

1. `test_auth_env_bootstrap.py::test_bootstrap_recovers_compose_interpolated_password_from_raw_env`：进程 DATA_DIR 优先于该测试自己的临时 `.env`，导致 auth 文件位于运行器临时目录而非测试期望目录。与 [CN 隔离审计](cn-hk-us-quote-processing-isolation-audit-v1.md) 已记录的环境问题一致，不涉及生产 auth 文件。
2. `test_damon_chat.py::test_unconfigured_and_sensitive_profile_metadata_fail_closed`：本轮扩大验收新发现的测试顺序依赖，不能简单归为既有历史通过。`test_ai_provider.py::test_save_ai_settings_persists_token_sizes` 经保存接口修改 Settings 中的假 Key，但 finally 只恢复输出/上下文配置；Damon 的“未配置”测试只清空假 store，未隔离 Settings fallback。Profile 按既有优先级回退到此测试残留值，因此 configured=True。没有发现真实凭证参与或产品绕过 Profile 校验。

最小顺序复现命令，**1 passed / 1 failed**：

```powershell
uv run --frozen --no-sync --offline pytest tests/test_ai_provider.py::test_save_ai_settings_persists_token_sizes tests/test_damon_chat.py::test_unconfigured_and_sensitive_profile_metadata_fail_closed -q --tb=short
```

受控复查用内存 pytest 插件（无文件新增/修改）：仅在 auth 测试 protocol 内暂移除 DATA_DIR，结束后还原，使其自身临时 `.env` 生效；仅在 Damon 未配置用例 call 前通过该用例的 monkeypatch 显式设 `profiles.settings.ai_api_key=""`，用例结束自动恢复。仍保持所有原断言。`pytest.main([...], plugins=[IsolatedFixtures()])` 的实际选择为下列四项，**4 passed / 0 failed，4.39s**：

```text
tests/test_auth_env_bootstrap.py::test_bootstrap_recovers_compose_interpolated_password_from_raw_env
tests/test_auth_env_bootstrap.py::test_bootstrap_from_env_does_not_override_existing_password
tests/test_ai_provider.py::test_save_ai_settings_persists_token_sizes
tests/test_damon_chat.py::test_unconfigured_and_sensitive_profile_metadata_fail_closed
```

这是环境/顺序依赖诊断，不是仓库 fixture 修复或受控全量通过。**待跟进**：后续单独修复设置测试的全局状态恢复和 Damon fixture 的 fallback 隔离，再运行全量；本轮不修改这些 Python 文件、生产代码或测试断言。受控完整后端第二轮 **NOT RUN**。

### 本轮收尾

`git diff --check` 通过；19 个候选文件的高置信秘密模式和尾部空白检查均为 0 命中（非完整 DLP）。本轮没有 Python 修改，Ruff 对 TS/TSX 不适用；上面的 Python 定向复查是额外验证，保留共享 Provider 历史 1 条 BLE001。没有新增依赖，没有访问生产数据库或生产凭证文件，没有调用真实模型/STT/TTS/行情 API。

**NOT RUN**：人工浏览器验收、真实服务连接、全仓 Ruff/ESLint、受控全后端重跑。完整前端 Vitest、node:test、完整后端尝试与定向后端均为本轮实际执行，不能再沿用上节的 NOT RUN 描述。

当前仍为 `feat/damon-ai-phase1`，HEAD `d2e62cbd4d7c0e06a896c5ef877ff62981f3dc35`；8 个已修改、11 个未跟踪文件，共 19 个候选，暂存区空。本轮只触碰面板、面板测试和本文档，其余候选完整保留；不提交、不推送。持久状态及待办留在本文，未更新项目外记忆。

## 完整后端两项失败的测试隔离修复（2026-10-18）

本节接续上一轮，起始分支和 HEAD 均未改变，原 19 个候选完整保留。只修改 `backend/tests/test_auth_env_bootstrap.py`、`backend/tests/test_ai_provider.py`、既有未跟踪候选 `backend/tests/test_damon_chat.py` 和本文；没有产品代码、前端、依赖或数据库配置改动。

### 本轮先复现，再修复

每个命令均使用不存在的 `TICKFLOW_ENV_FILE`、唯一临时 `DATA_DIR`、空 `AI_API_KEY/TICKFLOW_API_KEY`，没有真实服务和生产凭证文件参与。修复前本轮实际结果：

| 选择 | 通过 | 失败 | 依据 |
| --- | ---: | ---: | --- |
| auth 失败用例单独运行 | 0 | 1 | auth.json 未出现在 fixture 期望路径 |
| Damon 未配置用例单独运行 | 1 | 0 | 独立进程的 Settings fallback 为空 |
| 旧设置保存测试 → Damon 未配置测试 | 1 | 1 | 旧设置测试遗留假凭证，Damon 出现 configured=True |

最小修复没有改变生产 Settings 的“进程环境优先于 `.env`”规则，也没有改变 Profile 的 store→Settings fallback：

- auth fixture 用 `monkeypatch.delenv("DATA_DIR")` 暂时移除运行器目录，让本用例自己的临时 `.env` 决定 Settings 路径；测试结束自动恢复进程环境。会话表和配置缓存改为 monkeypatch 独立替换，避免直接清空并丢弃先前测试状态。
- 旧设置保存测试将实际改动的七个共享 Settings 字段全部纳入 monkeypatch：provider、base URL、假 Key、model、UA、输出和上下文预算；此前只在 finally 恢复后两项。保留原请求和四个业务断言。
- Damon offline fixture 显式将 Settings 凭证 fallback 设为空，结束后恢复，使“未配置”用例不依赖运行顺序或运行器设置。假 store、禁网络/子进程/SQLite 的原边界保持。

修复后相同三次运行分别为 **1 passed、1 passed、2 passed**，无受控修补插件。两份已跟踪测试相对 HEAD 的 AST 静态比较确认 **99 个原断言全部保留**；Damon 仅新增 fixture 配置，没有修改其断言。

另用纯观察的内存 pytest hookwrapper 运行 auth 两项、旧设置保存和 Damon 未配置共四项，**4 passed**；协议结束后断言 DATA_DIR、auth 会话表身份/缓存、七个共享设置字段和 Damon fallback 与测试前一致。该插件不修改环境和设置、不替代 fixture，也没有写入项目。

### 本轮验证命令和已完成结果

命令工作目录为 backend：

```powershell
# 修复前后分别运行，不是沿用上一轮结果
uv run --frozen --no-sync --offline pytest tests/test_auth_env_bootstrap.py::test_bootstrap_recovers_compose_interpolated_password_from_raw_env -q --tb=short
uv run --frozen --no-sync --offline pytest tests/test_damon_chat.py::test_unconfigured_and_sensitive_profile_metadata_fail_closed -q --tb=short
uv run --frozen --no-sync --offline pytest tests/test_ai_provider.py::test_save_ai_settings_persists_token_sizes tests/test_damon_chat.py::test_unconfigured_and_sensitive_profile_metadata_fail_closed -q --tb=short

# 相关回归，262 passed / 0 failed
uv run --frozen --no-sync --offline pytest tests/test_auth_env_bootstrap.py tests/test_ai_provider.py tests/test_damon_chat.py tests/test_ai_sdk_logging.py tests/test_damon_ai.py tests/test_ai_responses.py tests/test_secrets_external_edit.py tests/test_custom_assistant.py tests/test_custom_assistant_sessions.py tests/test_extensions.py tests/test_quote_market_boundary.py tests/test_market_provider_contracts.py tests/test_anomaly_intelligence.py -q --tb=short

# 本轮三份测试的 Ruff：auth/Damon 通过，Provider 测试文件保留基线 I001 一项
uv run --frozen --no-sync --offline ruff check tests/test_auth_env_bootstrap.py tests/test_ai_provider.py tests/test_damon_chat.py
git show HEAD:backend/tests/test_ai_provider.py | uv run --frozen --no-sync --offline ruff check --stdin-filename tests/test_ai_provider.py -
```

I001 位于未修改的 `test_save_ai_settings_rejects_non_positive` 导入区，基线 458 行、候选 457 行，规则及内容一致。本轮没有新增 Ruff 诊断，没有自动清理历史问题。

前端本轮无改动，仍实际复查 `pnpm exec vitest run src/custom/damon/ai src/extensions/ExtensionRouteRecovery.test.tsx --maxWorkers=2`：**6 文件、41 passed**；`pnpm build`（含 TypeScript）通过，保留大 chunk / React Router future flag 提示。没有将上一轮完整前端 420 计为本轮执行。

### 完整后端最终结果与收尾

本轮完整套件 **4259 项：4252 passed、0 failed、6 skipped、1 xfailed，214 warnings，307.93s，退出码 0**。没有新增 skip/xfail 标记或改断言；没有复现 mining worker 原生退出异常，也不能据此宣称历史原生异常已修复。

执行方式与上轮默认环境尝试一致：唯一临时 DATA_DIR、空 AI/TickFlow Key、不存在的环境文件，`uv run --frozen --no-sync --offline python -c <内存外联闸门 + pytest.main(["tests", "-q", "--tb=short"])>`。保留前节的父进程 socket 外联拒绝保护，不额外设置 POLARS_MAX_THREADS、不加入修补 fixture/设置的 pytest 插件、不删除或选择性排除测试。auth 的进程 DATA_DIR 临时清理由本轮仓库 fixture 自身完成，并由 monkeypatch 恢复。前述纯观察恢复检查是另一次 4 项诊断，不参与本次完整运行。

因此上一节“待单独修复设置测试全局恢复、Damon fallback 隔离”的两项待办，本轮已通过测试代码修复和完整回归解除；保留上一轮失败事实及复现记录，不把它们改写成通过。

本轮检查：`git diff --check` 通过，21 个候选文件高置信秘密模式及尾部空白检查均 0 命中（非完整 DLP）；Ruff 三份修改测试无新增诊断，Provider 测试保留与 HEAD 相同的 I001 一项。无生产代码/数据库/凭证配置修改，未读取生产凭证文件、未调用真实模型/语音/行情服务。测试数据库与假配置仅位于临时存储；父进程外联闸门不是对子进程或生产部署网络隔离的保证。

**NOT RUN**：本轮完整前端 Vitest、node:test、全仓 Ruff/ESLint、人工浏览器及真实服务验收。前端只重跑上文 41 项相关测试及构建；没有沿用旧结果作为本轮通过数。

最终分支 `feat/damon-ai-phase1`，HEAD `d2e62cbd4d7c0e06a896c5ef877ff62981f3dc35`，暂存区空。工作区 **10 个已修改、11 个未跟踪，共 21 个候选**：原 19 个候选全部保留，新增的候选状态是原本已跟踪的 auth/Provider 两份测试变为已修改，不是新增仓库文件。

**仍阻塞**：真实模型、真实语音接入和任何真实连接验收，等待人工审阅及下一步授权；不因离线全量通过而自动开始。无 commit/push/fetch/pull/rebase。持久状态与待办仅更新本文，没有修改项目外记忆。

## 21 个候选复核与前端离线验收补齐（2026-10-18）

起始路径、分支、HEAD、21 个候选和空暂存区符合预期。测试隔离复核结论：三处修复只在 pytest 中替换环境/对象，未改生产 Settings 优先级或 Profile fallback。monkeypatch fixture 的 undo 由 pytest teardown 执行，不依赖测试正文正常返回；已安装 pytest 的 runner 在 setup/call 失败后仍执行 teardown。异常清理为本轮静态复核结论，不声称本轮做过失败注入。上一轮单测、顺序组合、纯观察恢复检查及完整后端 4252 通过是已有记录，本轮不重复计为执行。

安全调用链复核：Damon 成本接口仍经过现有认证，并额外校验 cookie 主体/本机模式，拒绝 Bearer；请求额外字段禁止，不能提交 endpoint 或凭证引用。Profile 在轮次开始冻结，不修改旧助手默认设置。模型入口仅发文字，不传 tools、不调用旧 dispatcher；只读策略默认表仍为空，无工具执行 HTTP 端点。未发现业务数据库写入、Shell/文件/任意 URL 工具。服务地址由管理员配置，不等于部署级出站 allowlist；无密码共享 local-owner、单进程预算仍是明确限制。

日志过滤依然在客户端请求前安装，具体 SDK logger 被阻止向 handler/父级传播；应用业务日志不被该过滤器关闭。SDK 升级后的未知 logger 和完整代理/TLS 路径仍不能仅凭当前清单判定通过。正文仍限制 16000 Unicode 码点：原始和脱敏后都检查；超限/取消先退休轮次，迟到正文和 done 不能进入成功历史，未退出任务保留准入。

### 本轮发现并修复的终态边界

静态复核发现 P2：页面接受合法 done 后清除了 70 秒定时器，却仍等待 HTTP EOF 才结束发送状态；若代理保持响应体打开，页面可能一直生成且停止处理器会因轮次已 terminal 而返回。

已先说明原因，再做最小修复：`streamDamonChat` 的消费回调可返回 false 表示协议消费者已经确认终态，传输立即 return 并执行原 finally 的 reader.cancel/releaseLock；页面只在已有 ID/序号/正文/成功码校验通过后，对成功 terminal 返回 false。错误仍按原流程退休、Abort、失败；未经校验的裸 done 不直接触发传输成功。

本轮仅修改已有候选 `frontend/src/lib/api.ts`、`frontend/src/custom/damon/ai/TextChatPanel.tsx`、其 `TextChatPanel.test.tsx`、`transport.test.ts` 和本文，不新增文件、不改后端。新增两项离线用例：实际 ReadableStream 不发送 EOF，验证合法 done 后 reader 释放、不消费尾随片段、UI 回到就绪，成功历史正确传递至下一轮。没有删除或放宽原断言。

### 本轮实际命令与结果

```powershell
# frontend：修复前 53 文件 / 420 passed；最终代码完整重跑 53 文件 / 422 passed / 0 failed
$testFiles = @(rg -l 'from .*vitest' src -g '*.test.ts' -g '*.test.tsx')
pnpm exec vitest run --maxWorkers=2 @testFiles
# 两份实际 node:test：5 passed / 0 failed
node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts
# 本轮因前端代码最小修复而追加：tsc -b 与 Vite 构建通过
pnpm build

# backend：Damon 及隔离测试 Ruff 通过
uv run --frozen --no-sync --offline ruff check app/services/damon_ai app/services/ai_sdk_logging.py app/api/damon_ai.py tests/test_damon_ai.py tests/test_damon_chat.py tests/test_ai_sdk_logging.py tests/test_auth_env_bootstrap.py
# 扩展 Ruff 检查退出 1：两条历史诊断，未自动修复
uv run --frozen --no-sync --offline ruff check app/services/ai_provider.py tests/test_ai_provider.py
# HEAD 基线各有同一诊断：BLE001（910→966 行）、I001（458→457 行），无新增
git show HEAD:backend/app/services/ai_provider.py | uv run --frozen --no-sync --offline ruff check --stdin-filename app/services/ai_provider.py -
git show HEAD:backend/tests/test_ai_provider.py | uv run --frozen --no-sync --offline ruff check --stdin-filename tests/test_ai_provider.py -
```

前端最终 422 通过包含 Damon/路由 43 项、旧助手及 CN/HK/US Preview 相关断言。现有 React Router future flag、大 chunk 警告仍在。`git diff --check`、候选范围检查、21 文件高置信敏感模式及尾部空白检查通过；扫描不是通用 DLP。

**NOT RUN**：本轮后端 pytest、失败注入、全仓 Ruff/ESLint、人工浏览器、真实模型/语音/行情和真实网络连通验收。未将上一轮隔离全后端通过描述为本轮默认环境通过。没有访问生产凭证文件、数据库或真实服务。

仍未闭环：两项历史 Ruff、Windows worker 原生退出的间歇风险、SDK 升级/代理网络日志复核、单 worker 内存预算与明文秘密存储边界。真实模型和语音接入继续阻塞，等待人工决定。本轮复核未发现测试隔离修复改变生产行为。

最终仍为 `feat/damon-ai-phase1` / `d2e62cbd4d7c0e06a896c5ef877ff62981f3dc35`，10 个已修改、11 个未跟踪，共 21 个候选，暂存区空；原候选全部保留，无 commit/push/fetch/pull/rebase。持久记录仅更新本文。
