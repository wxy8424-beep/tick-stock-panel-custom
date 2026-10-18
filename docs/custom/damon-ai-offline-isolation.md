# Damon AI：离线隔离启动器

日期：2026-10-18。开发基线 `66c4f00a14f119577b9151e02d677b2e623eb97a`。

本设施仅用于假模型离线验收，真实模型冒烟继续 **NO-GO**。没有监听服务器、真实凭证入口或生产工具。正常 `app.main` 启动、生产认证及模型默认行为不变。

## 使用方式

在 backend 目录、已有依赖环境中执行：

```powershell
uv run --frozen --no-sync --offline python -B scripts/damon_offline.py
uv run --frozen --no-sync --offline pytest tests/test_damon_offline.py -q --tb=short
```

第一条命令在新进程内创建临时目录，完成测试密码登录和三次假模型请求，关闭任务并删除整个临时目录。JSON 输出仅包含离线模式、计数、路径和清理结果，不输出密码、会话 Cookie 或假 Key。参数（包括 `--listen`）一律拒绝。

## 隔离机制

- 引导文件最初只导入标准库；在导入 asyncio/logging、任何 app 模块之前固定绝对临时 DATA_DIR、空隔离环境文件和测试配置。仅保留 OS 加载器变量，清除继承的凭证/代理/业务配置；禁用字节码写入。不读取生产 `.env`、auth.json 或 secrets.json。
- 仅支持独立新进程；已导入 app 的进程拒绝初始化。每次创建唯一临时目录，不使用生产目录或现有认证会话，不与其他应用共享模块全局状态。
- 使用 HTTPX ASGITransport，逻辑客户端及地址为 127.0.0.1，`trust_env=False`；无端口、无 reload、无多 worker。Windows asyncio 的内部 socketpair 在应用审计防线安装前创建，不是业务监听服务。
- 导入拦截拒绝 app.main、后台调度、行情、数据 Provider、仓库和旧助手模块。没有生产 lifespan、QuoteService、任务修复、预热或后台业务线程。Damon 路由通过现有 BackendExtensionRegistrar/Registry 注册，不调用自动发现和业务 startup 钩子。
- 复用真实密码哈希、登录、注销和会话校验；启动时仅在临时目录写测试密码哈希。只开放 auth status/login/logout 及 Damon status/profiles/chat/cancel，其他路由、文档和任意方法默认拒绝。认证状态查询可以匿名，Damon 路由必须有有效会话，拒绝 Bearer。
- 复用现有 Profile 解析、ChatRegistry 和 NDJSON API。仅接受内置确定性 FakeModel，显式替换本子进程的流入口，并禁止真实客户端工厂；退出恢复引用。不修改生产 Provider 或 HTTPX 配置。
- 独立 Python 审计防线拒绝 DNS、connect、bind、子进程和 SQLite 连接；拒绝临时根以外的文件写入和敏感配置读取。记录路径和事件种类，不记录参数/凭证。此机制是受信任假适配器的辅助防线，**不是 OS 沙箱，不能保证任意原生代码或不可信 Python 的网络隔离**。不能据此开放真实服务。

## 服务端限制

专用 ChatRegistry 子类在派发前执行：总共最多 3 次尝试（失败、取消及超时不退款），最多 1 个活动模型；最新用户输入最多 1000 Unicode 码点，消息上下文合计最多 3000 码点；模型快照输出不超过 512 tokens。

最终审查补充：准入层先检查提交的消息；假适配器还检查 ChatRegistry 加入系统提示后的实际完整消息内容，合计仍不得超过 3000 Unicode 码点。超限返回 input_limit、没有成功终态，并关闭本次运行；已预留的尝试不退款。码点口径是 Python len(str)，包含中文和非 BMP emoji。限额属于单个 OfflineRuntime 的 registry 实例；入口每个新进程只创建一个实例，不构成跨实例、跨进程或多用户的统一配额。

FakeModel 把一个 Unicode 码点定义为一个确定性的假 token 单位，512/513 的边界检查只验证测试适配器与 max_tokens 参数，不代表真实模型 tokenizer 或金额计费。没有金额封顶。

模型异常、超时、输出超限和任何取消都会保守关闭本次运行，不能通过新 conversation 或重试重新派发；第三次后同样拒绝。输入校验或并发拒绝不触发上游，不消耗派发次数。

保持生产服务端 60 秒/清理等待 0.2 秒；浏览器原 70 秒实现不修改。本设施没有浏览器客户端，不宣称本轮重新验收浏览器期限。

## 生命周期与失败清理

请求通过 ContextVar 记录自己实际派发的轮次；ASGI disconnect 只能取消本请求的轮次，不能取消并发被拒绝请求之外的其他轮次。既有 registry 在取消竞态可能产生 error/code=cancelled，专用子类统一成 cancelled 终态，不改变生产协议实现、不转换为成功。

退出先关闭准入、释放受信任假适配器，再有界等待模型清理。未结束任务报错，不能虚报退出；不合作取消的假适配器在运行期间保留活动准入，退出时通过 fixture 自身 release 结束。原型初始化、测试正文异常和被拒绝的端口绑定都由外层 finally 清理临时目录。审计防线不允许清理其他目录。

常规写入仅为本次临时根内 isolated.env、data/user_data/secrets.json、auth.json 及原子写入临时文件。退出后根目录也删除；没有创建生产数据库或 backend.log。

## 验证范围与记录

测试在独立子进程中运行：真实密码成功/失败、匿名拒绝、路由白名单、连续上下文、三次预算、并发、中文/emoji 输入边界、512/513 假 token 输出、错误、真实 60 秒超时、取消/不合作取消、真实 ASGI disconnect、在途任务退出、禁止网络/文件/后台模块及失败清理。退出断言不存在未完成任务，并核对所有写入路径与根目录删除结果。

开发过程首次 14 用例运行：12 passed、2 failed。一个是测试驱动把名为 failure 的正常验错场景误判为应以非零退出；另一个揭示仅依赖响应清理不能保证 ASGI 断连取消。保留断言，修正驱动分类并增加按请求归属的断连清理。后续纯 ASGI 边界又暴露取消终态竞态，按上述专用协议归一化处理，没有修改生产实现或既有测试。

后续一次 17 项完整运行曾为 16 passed、1 failed（取消终态竞态）；最终实现保留原断言并统一离线取消终态。非超时快速复验 16 passed、1 deselected 只是定位结果，不能代替下列完整结果。最初 Ruff 报告了新文件的命名、导入和控制流格式问题，均只在新文件内修正。

最终实际执行（backend 工作目录）：

```powershell
# 禁止字节码写入；pytest cache_dir 使用独立临时路径。
$env:PYTHONDONTWRITEBYTECODE = '1'
$cache = Join-Path $env:TEMP ('damon-offline-pytest-' + [guid]::NewGuid().ToString('N'))
uv run --frozen --no-sync --offline pytest tests/test_damon_offline.py -q --tb=short -o cache_dir=$cache
# 17 passed、0 failed、0 skipped，106.64s；包含实际 60 秒超时路径。

uv run --frozen --no-sync --offline python -B scripts/damon_offline.py
# attempts=3、active_tasks=0、cleaned=true。

uv run --frozen --no-sync --offline ruff check scripts/damon_offline.py scripts/damon_offline_app.py tests/test_damon_offline.py
# All checks passed。
```

新增定向完整通过之后，使用不存在的 TICKFLOW_ENV_FILE、唯一临时 DATA_DIR、空 AI/TickFlow Key、禁止字节码写入及临时 pytest 缓存执行相关回归：

```powershell
uv run --frozen --no-sync --offline pytest tests/test_auth_env_bootstrap.py tests/test_ai_provider.py tests/test_damon_chat.py tests/test_ai_sdk_logging.py tests/test_damon_ai.py tests/test_ai_responses.py tests/test_secrets_external_edit.py tests/test_custom_assistant.py tests/test_custom_assistant_sessions.py tests/test_extensions.py tests/test_quote_market_boundary.py tests/test_market_provider_contracts.py tests/test_anomaly_intelligence.py -q --tb=short -o cache_dir=$cache
# 262 passed、0 failed，37.37s。
```

独立入口本轮实际临时根为 `C:\Users\84248\AppData\Local\Temp\damon-offline-o_apyg7d`：写入清单仅含 isolated.env、data/user_data/auth.json、secrets.json 和它们的原子写入 .tmp 文件及父目录，返回 cleaned=true。目录已删除，没有保存凭证内容或聊天记录。pytest 自身的 runner 缓存与假服务数据是额外的测试临时产物，不是启动器允许访问的生产目录。

本轮只新增启动器两份、测试及本文共四个文件。开始时已有的四个 Mining Worker 诊断候选以 SHA-256 核对，均未改动；没有运行 Worker 测试或修改 Worker 断言。此前项目全量通过/失败记录不是本设施本轮结果。

`git diff --check`、四个新文件的尾部空白检查通过，高置信敏感模式扫描 0 命中（不是完整 DLP）。暂存区为空，没有提交或推送。

NOT RUN：完整后端、完整前端、node、TypeScript/前端构建、真实模型/语音/行情、生产数据库、浏览器、OS 网络隔离、真实端口占用/绑定服务器验收。拒绝端口绑定的清理用例不等于真实监听模式验收。本轮未新增 skip/xfail；历史 Worker 退出问题未解决，也未借本设施重跑后宣称解决。

在具备管理员批准的 OS 出站隔离、受控凭证、费用硬封顶等条件前，禁止把本设施改为真实模型启动器。

## B-DAMON-1.2-OFFLINE-FINAL 最终审查（2026-10-18）

本节为新一轮实际记录，前文 17/262 项为历史记录。本轮只允许修改本启动器的四个文件；未修改 WORKER-DIAG 四个候选或任何生产模块，未暂存、提交或推送。

本轮最小加固：Windows 敏感配置/数据路径用 casefold 判断；独立入口测试显式传最小允许环境；新增完整消息（包括系统提示）3000 码点检查和边界测试。新增测试未删除、跳过或放宽原断言。子进程在 app 导入前断言环境键白名单，认证仍走真实哈希和验证。

本轮执行（backend 目录）：

- `uv run --frozen --no-sync --offline pytest tests/test_damon_offline.py -q --tb=short -o cache_dir=<唯一临时路径>`：18 passed，111.91s，退出码 0，含实际 60 秒期限、3000 完整上下文、大小写路径拒绝。
- `uv run --frozen --no-sync --offline python -B scripts/damon_offline.py`：3.88s，退出码 0，attempts=3、active_tasks=0、cleaned=true。
- 新增三份 Python 文件 Ruff：All checks passed，退出码 0。首次沙箱内 pytest/Ruff 因 uv 缓存访问错误而未启动，随后原命令在沙箱外执行，不修改产品绕过问题。
- 扩大 Ruff 至八个候选中的所有 Python 文件及 Damon API、安全模块：退出码 1，仅 worker.py 的既有 BLE001；HEAD 同样存在 `except BaseException as exc`。未修改 WORKER-DIAG。
- 高置信秘密模式扫描八个候选：sk-长串、AKIA 和私钥头 0 命中；不是完整 DLP。首次扫描命令有 PowerShell 管道语法错误，修正命令后才完成扫描。

独立入口本轮实际根：`C:\Users\84248\AppData\Local\Temp\damon-offline-nzn4otj9`。审计记录写入为 isolated.env、data、data/user_data、auth.json、auth.json.tmp、secrets.json、secrets.json.tmp（后四项在 data/user_data 下）；退出后 Test-Path=False。没有读取或输出文件中的密码、Cookie 或 Key。测试中的哈希文件检查仅用于本次生成的假认证数据。

相关回归采用 `uv run --frozen --no-sync --offline python -B -c $runner`，内存 runner 在任何 app 导入前只保留 OS/loader/temp 白名单，构造唯一临时 DATA_DIR、HOME、USERPROFILE、TEMP/TMP、空业务凭证和不存在的 TICKFLOW_ENV_FILE。不设置线程限制，不修改 fixture，不传 pytest 修补插件。

runner 用 Python audit hook 拒绝非回环 DNS/connect/bind，并在运行 pytest 前主动尝试被拒绝的 offline.invalid DNS 和文档保留地址连接，确认两个闸门实际生效；另外拒绝仓库生产 data 和 .env/secrets 文件打开。它只保护该 Python 进程，不能宣称覆盖原生网络或 spawned 子进程；子进程继承的配置均为临时/空值。完整回归允许测试自身的环回通信，未启动正常生产 lifespan 作为运行服务。

第一次相关回归：3 collection errors，8.24s，pytest 返回 2（外层 uv 命令返回 1）；原因是 runner 未提供临时 HOME/USERPROFILE，TickFlow 在 Path.home() 初始化失败。仅修正内存 runner 后重跑：

```powershell
# $runner 先完成上述最小环境和审计闸门自检，再执行：
pytest.main([
    'tests/test_auth_env_bootstrap.py', 'tests/test_ai_provider.py',
    'tests/test_damon_chat.py', 'tests/test_ai_sdk_logging.py',
    'tests/test_damon_ai.py', 'tests/test_ai_responses.py',
    'tests/test_secrets_external_edit.py', 'tests/test_custom_assistant.py',
    'tests/test_custom_assistant_sessions.py', 'tests/test_extensions.py',
    'tests/test_quote_market_boundary.py', 'tests/test_market_provider_contracts.py',
    'tests/test_anomaly_intelligence.py', '-q', '--tb=short',
    '-o', 'cache_dir=<临时根>/pytest-cache', '--basetemp=<临时根>/pytest-tmp'
])
```

262 passed，35.62s；runner 36.80s，退出码 0。实际临时根 `C:\Users\84248\AppData\Local\Temp\damon-final-regression-v8mo31p1`。此处 Python 表达式是 $runner 内部调用，不是 PowerShell 独立命令。

安全审查边界：离线环境/导入、真实认证、假适配器、准入预算及 Unicode 限制有静态和运行证据；512 是传给 adapter 的真实 max_tokens 参数，假模型只验证假 token 单位。生产协议静态映射为 Chat Completions max_tokens / Responses max_output_tokens，没有真实模型或金额保证。任务集合归零和子进程退出已验证，不扩大为任意原生线程/句柄的泄漏证明。SDK 日志抑制仍在客户端构造前安装，只抑制 openai/httpx/httpcore 命名空间；依赖升级必须重新做真实 SDK + MockTransport 日志复核。

真实模型继续 NO-GO：OS 出站策略、受控凭证和可执行费用上限尚未验收；单实例内存配额不是多 worker 配额，生产无密码共享主体不是多人隔离，现有 secrets JSON 不是加密保险库。Mining Worker 间歇退出问题根因仍未闭环，诊断探针不等于修复。

NOT RUN：本轮前端 Vitest、node:test、TypeScript/前端构建、浏览器、真实模型/语音/行情、生产数据库和 OS 网络隔离验收。没有前端或生产依赖变化。

### 本轮完整后端结果

相关回归通过后，沿用同一已自检的内存 runner，仅把 pytest 选择改为整个 tests：

```python
pytest.main(['tests', '-q', '--tb=short', '-o',
             'cache_dir=<临时根>/pytest-cache', '--basetemp=<临时根>/pytest-tmp'])
```

外层实际命令 `uv run --frozen --no-sync --offline python -B -c $runner`。默认线程配置（没有 POLARS_MAX_THREADS 或其他线程限制）、原始断言、没有排除项或修补插件，WORKER-DIAG 环境开关默认未设置，专用测试自行启用并恢复。

**4278 passed、0 failed、6 skipped、1 xfailed、214 warnings，404.21s；runner 总耗时 406.05s，退出码 0。** 总收集 4285 项。实际临时根 `C:\Users\84248\AppData\Local\Temp\damon-final-regression-r8znjcma`。网络拒绝计数仍为 2，均为 pytest 前主动自检；没有额外的父进程 Python 外联记录。pytest 自身缓存、各测试临时存储和日志属于该验收临时根，不与生产 DATA_DIR 共用。未把临时验收目录的保留描述为启动器清理失败：启动器创建的独立根已删除，完整 pytest runner 的诊断临时产物另行保留。

完整回归包含本次离线设施及现有 Worker 诊断测试；没有修改 WORKER-DIAG 源码、退出阈值或断言。历史 Worker 失败本次未复现，不代表其间歇根因已确定或修复。214 条告警未通过本任务修改无关代码消除。

最终候选范围仍为 1 个已修改文件、7 个未跟踪文件，共 8 个；暂存区为空。WORKER-DIAG 四个文件 SHA-256 与执行前一致。本轮实际修改仅 DAMON-OFFLINE 四个文件。生产代码和前端 diff 为空；diff/尾部空白检查与八文件高置信敏感模式扫描最终复查通过。历史通过数没有作为本轮结果引用。
