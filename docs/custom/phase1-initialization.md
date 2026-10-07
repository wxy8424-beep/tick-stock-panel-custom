# tick-stock-panel-custom 第一阶段初始化审计

日期：2026-10-07。范围：原始上游审计、环境安装、验证、独立 Git 与私有备份配置。没有修改业务核心、依赖声明、锁文件、LICENSE 或上游工作流。

## Repository

- Original upstream：https://github.com/shy3130/tick-stock-panel.git
- Upstream branch：main
- Upstream commit：`634adb61772303fa6402a561cb288238c45ea21a`（docs: 更新交流群二维码）
- 完整 clone，非 shallow；原始 main 可达 1027 个提交。其他上游分支由 upstream 保留远程跟踪，不假称都已推送到 origin。
- My origin：https://github.com/wxy8424-beep/tick-stock-panel-custom.git
- Visibility：PRIVATE，已由 GitHub CLI 实际核验。
- Development branch：main。没有为初始化制造无意义功能分支。
- 父目录 lianghua 与本仓库独立：父仓库忽略本目录，本仓库完整保留自身历史与独立备份，不能把父仓库或 gitlink 当成本仓库源码备份。

## Git

- 原始导入恢复标签：`upstream-baseline`，指向上述 upstream SHA。这是原始导入恢复点，lint 尚未通过，不标记为全面验收稳定发布。
- origin fetch/push：用户私有仓库；upstream fetch：原作者，push URL 配置为 `DISABLED` 防误推。
- Git 身份仅配置在本仓库：Codex / codex@local.invalid。GitHub 凭据助手复用现有官方 CLI 登录，不在文件中保存令牌。
- `remote.pushDefault` 和 `branch.main.pushRemote` 均为 origin。
- **Baseline pushed：NO。截至本报告保存时，上传连接被重置，GitHub REST 核验返回 Repository is empty。**
- **Remote backup status：未完成，不能把仓库已创建当成源码已远程备份。** workflow 补充授权已完成并核验，无需再次授权；下一步解决 Git 上传连接重置，再核验 main、标签和独立远程恢复。
- 已建立独立于项目目录的本地完整 bundle：父目录 `.tools/backups/tick-stock-panel-custom-20261007.bundle`，28,740,892 bytes，保存初始化提交 `930eb1acc7221e83cfe23e41f20055fa6ed50841`、59 refs 与完整历史。bundle verify 成功；实际新目录 clone、HEAD 一致、main 工作区干净、fsck 无损坏、原始标签 dereference 与上游 SHA 一致。fsck 的两个 dangling commit 是 clone 未映射的其他上游分支对象，不是完整性错误。SHA256：`64118314D08C1D382C033A4036760A0E569CF6E496B1D2925EC255DF89D88FA0`。这仅是本机恢复验证，不能抵御整机/磁盘损失，不代替 GitHub 备份。
- 自动 Actions 在首次导入前通过仓库设置暂停，避免上游 docker.yml 在 main push 时自动发布镜像。上游文件保留；本地验证不等于远程 CI 已运行。

## Architecture

已阅读 AGENTS、CONTRIBUTING、README、secondary-development、plugin-development、custom-data-source，并对照以下源码及测试，而非仅按目录推断。

| 层/能力 | 已核对源码位置 | 实际职责与边界 |
| --- | --- | --- |
| 后端入口 | `backend/app/main.py`、`app/config.py` | FastAPI lifespan 创建 DataStore/Repository、加载 Provider 与能力、策略、调度器、监控及 custom 扩展；注册 API 与静态前端 |
| API | `backend/app/api/routes.py`、`screener.py`、`kline.py`、`events.py` | `/health`、能力、选股、K线、SSE；面板会话与开放 Token 网关平行，扩展不能覆盖核心路径 |
| Provider | `backend/app/data_providers/registry.py`、`capabilities.py`、`custom/loader.py`、`custom/provider.py`、`backend/app/plugins/` | 按数据集路由、能力声明、字段/单位标准化；TickFlow、插件和 YAML HTTP 源复用同一体系 |
| 同步服务 | `backend/app/services/kline_sync.py`、`quote_service.py`、`minute_refresh.py`、`financial_sync.py` | 同步、标准化、实时缓存更新与调度；金融口径不应在页面重复处理 |
| 存储 | `backend/app/tickflow/repository.py` 的 DataStore/KlineRepository | Parquet 分区、DuckDB 查询、维表与 enriched 快照/历史缓存，无需外部数据库服务器 |
| 指标与业务 | `backend/app/indicators/pipeline.py`、`services/screener.py`、`strategy/engine.py`、`backtest/` | enriched 基础列读出后计算指标/信号，选股与回测复用；重计算/回测有缓存及 worker 隔离 |
| 前端入口 | `frontend/src/main.tsx`、`router.tsx`、`extensions/bootstrap.ts` | 初始化扩展后挂载 React/router，统一页面与导航 |
| API/query/cache | `frontend/src/lib/api.ts`、`queryKeys.ts`、`useSharedQueries.ts` | API client、共享 QK/TanStack Query、SSE 失效与必要轮询；不另建缓存或 URL 系统 |
| 选股链路实例 | `frontend/src/pages/Screener.tsx`→`lib/api.ts`→`backend/app/api/screener.py`→`services/screener.py`→Repository/enriched→StrategyEngine | 页面共享 query/mutation；服务优先 Repository 最新日/历史缓存，慢路径再读 Parquet 并计算；API 不直接请求第三方供应商 |
| 测试 | `backend/tests/`，`frontend/src/**/*.test.ts(x)`，`.github/workflows/ci.yml` | pytest/asyncio、扩展隔离与金融数据回归、开放契约快照；前端 Vitest 与 node:test 混用，CI 当前仅后端 pytest 与前端 build |

技术栈：Python 3.11+ / FastAPI / Pydantic v2 / Polars / DuckDB / PyArrow / Parquet；React 18 / TypeScript 5 / Vite 5 / TanStack Query 5 / Tailwind 3 / ECharts 5 / lightweight-charts 4。

## Secondary Development

- L1：设置/路由矩阵，策略、信号、DSL 因子、扩展数据表及声明式页面；既有 Provider/`backend/app/plugins/<name>/plugin.yaml + provider.py`；YAML 数据源定义。运行时配置与 data 内私有文件默认不入 Git。
- L2 前端：`frontend/src/custom/damon/extension.tsx`。真实 loader 是 `import.meta.glob('../custom/*/extension.tsx')`；API v1 支持独立 route/navigation 和三个 slot：`layout.navigation.extra`、`stock-preview.footer`、`watchlist.toolbar`。契约见 `frontend/src/extensions/types.ts`、registry/bootstrap；已有 assistant 是参考实现。
- L2 后端：`backend/app/custom/damon.py` 或 `app/custom/damon/__init__.py` 包。`pkgutil.iter_modules` 发现直接模块/包，跳过 `_` 前缀；声明 EXTENSION_ID、EXTENSION_API_VERSION=1、setup(registrar)，使用 include_router、register_notification_formatter，可提供 startup(context)。注册版本/重复 ID/核心路由冲突/异常被隔离。
- 后端稳定 ExtensionContext 的 repository 协议当前只有 get_name_map；不能假称具备任意数据访问 API。新业务应通过既有服务/开放契约及明确适配，而非绕过层次直读私有缓存。
- L3：修改核心策略执行、仓位/风控/成交模型、Provider 全局契约或增加现有插槽表达不了的行为，须先分析 L1/L2 无法满足的理由、文件和同步影响，再补针对性回归。CandidateFilter、ScoringPolicy、PositionSizingPolicy、RiskPolicy、MonitorConditionEvaluator、BacktestCostModel 是文档设计示例，当前不是已实现的注册入口。
- 用户自定义 namespace 固定 `damon`；本阶段未创建空业务扩展。
- 优先复用本项目已存在能力。需要补足指标/形态/筹码/选股逻辑时再查用户指定 myhhub/stock 功能源码索引，记录来源 SHA、归属、单位与依赖，适配并测试，不能复制出第二套系统。

## Environment

| 项目 | 实际环境 |
| --- | --- |
| Git | 2.54.0.windows.1 |
| Python | uv 安装的 3.12.13，隔离 `backend/.venv`；系统默认 3.9.13 不满足要求 |
| uv | 0.11.22；`uv sync --python 3.12 --extra dev --frozen` 已完成，无锁文件变动 |
| Node | 24.15.0；上游 CI 用 Node 20，因此保留版本差异说明 |
| pnpm | 实际安装/构建使用 packageManager 指定 9.10.0；本机默认 11.25.0 的脚本策略曾拦 esbuild，已改用 9.10.0，未改包声明或锁文件 |
| Docker | CLI 29.8.1 已安装；沙箱调用 daemon 权限被拒绝，镜像构建/部署 NOT RUN |

Windows 跨盘安装中 pnpm 一度停滞；只停止本次安装会话，以缓存 offline + package-import-method=copy 成功完成。官方 pnpm9 辅助包与验证日志仅在忽略的 `data/verification/`，灾难恢复后需重新准备正确版本。

## Verification

全部业务测试针对未修改的 upstream SHA；仅添加 Git 防护和二开文档。

| 检查 | 状态 | 实际结果 |
| --- | --- | --- |
| Backend dependencies | PASS | 锁文件 frozen + dev；最初 TLS 下载失败后成功重试 |
| Backend tests | PASS | `python -m pytest tests -q -rs`：2493 passed、6 skipped、210 warnings，135.93s；跳过是日期边界用例的空串分支，不是假称全量无跳过 |
| Frontend dependencies | PASS | pnpm9 frozen；复制模式 offline 重试成功 |
| Frontend Vitest | PASS | `pnpm exec vitest run --exclude src/components/DimensionMembersDialog.test.ts --exclude src/lib/neighborPrefetch.test.ts`：15 files / 97 tests passed |
| Frontend node:test | PASS | `node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts`：5 tests passed |
| Frontend lint | FAIL | 已执行 `pnpm lint`；脚本为 eslint .，但上游 devDependencies 未含 eslint，命令不可用 |
| Backend ruff | FAIL | `ruff check app tests --output-format concise`：1599 errors，包括原有中文标点/导入等；未执行自动修复 |
| Frontend build | PASS | `pnpm build`（tsc -b + vite build），2856 modules，Vite 21s；ECharts 约 1MB chunk 产生大小警告 |
| Application startup | PASS | 真正 uvicorn lifespan 启动、25 策略加载；隔离新 DATA_DIR、无 Key、127.0.0.1:33018；首页、/health、/api/capabilities、/api/screener/strategies、/api/openapi.json?tier=a 均 200；正常 shutdown，服务已停止 |
| 浏览器完整交互/付费行情/AI/实盘 | NOT RUN | 启动冒烟与静态首页 HTTP 检查不等于所有页面和付费能力验收；未使用私人数据或凭证 |
| Docker build/部署/远程 CI | NOT RUN | 本阶段无部署任务，daemon 未验收，Actions 暂停 |
| 本地 bundle 恢复 | PASS | 独立目录 clone、初始化 HEAD/原始标签一致、fsck 无损坏，完整历史已验证 |
| 私有远程恢复 | NOT RUN | 推送未成功，远程仍空，不能进行有效远程 clone 恢复验证 |

首轮 pytest 设置 DATA_DIR 环境变量覆盖了测试自行构造的 Settings，导致一项临时目录断言失败；移除该覆盖后定向两项通过、完整复验上述通过。一次沙箱权限受限执行不作为产品测试结论。前端最初把 node:test 文件交给 Vitest 报无 suite；对照源代码后按真实运行器分开全部通过。build 仅产生已跟踪 vite.config.d.ts 的换行差异，已恢复本次生成的差异，未保留核心改动。

## Risks

1. 当前 GitHub 仓库已创建但无代码：上传 RPC/连接重置，尚未完成灾难恢复备份。自动审批服务反复断线还阻碍部分重试，不能宣称 push 成功。
2. 最初缺 workflow OAuth 范围；用户补充授权后 CLI 核验 repo/read:org/gist/workflow 已存在，此授权问题已经解决，无需重复登录。授权后连接重置仍存在，不能再把授权不足作为当前阻塞。workflow 用途参见 GitHub 官方说明：https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps 。
3. 两项 lint 未通过，不应称全面绿色稳定基线；按初始化限制暂不擅自改业务/工具链。实际金融能力仍取决于 Provider 和凭据。
4. `backend/app/data_providers/custom/provider.py:_normalize_pct_units` 未声明 pct_unit 的 change_pct 仍存在 median/max 推断；amplitude/turnover_rate 未声明置空。README 的全面 fail-closed 描述不完全符合实现。新增自定义源必须声明 pct_unit，并为边界写测试，本阶段不修上游行为。
5. 分钟标准化守卫仍含对 naive UTC 特征的兜底纠偏；新源必须源头明确时区，不能依赖猜测。扩展上下文与文档目标接口范围有限。
6. `.gitignore` 补强 .env.*、凭证文件与 standalone db/sidecars。当前跟踪敏感文件名检查只有空凭据 .env.example；源码高置信令牌/私钥模式未发现匹配。该检查不是全部 Git 历史或每种秘密的全面审计证明；新增用户内容提交前持续检查。
7. Git 排除 data/、私有策略运行文件、密钥、依赖和日志；源码 clone 不能恢复这些。重要运行数据应另行设计经过授权的加密备份，不能随代码上传个人账户材料。

## Recommendation

先用 L1，再用真实 L2 custom/slot。下次需求开始先搜索已实现能力和测试，确认金融边界，再选择最小方案。优先维护 `frontend/src/custom/damon/` 与 `backend/app/custom/damon/`，避免将新业务散落在核心。

### 正常开发与远程备份

保存文件本身不会触发 Git commit/push。没有设置定时后台自动提交；本仓库 AGENTS 要求 Codex 在逻辑完整、验证并审查后的阶段主动 commit + push。手工开发时也需自己触发：

```powershell
git status
git add <明确文件>
git diff --cached
git commit -m "feat: describe verified change"
git push origin <branch>
git rev-parse HEAD
git ls-remote origin refs/heads/<branch>
```

比较 SHA 一致才叫已备份；未通过的 checkpoint 标明状态，不能标记稳定。

### 恢复

远程备份真正完成后，优先在新目录恢复，保护当前未提交文件：

```powershell
git clone https://github.com/wxy8424-beep/tick-stock-panel-custom.git <新目录>
git remote add upstream https://github.com/shy3130/tick-stock-panel.git
git config remote.upstream.pushurl DISABLED
git config remote.pushDefault origin
git config branch.main.pushRemote origin
git worktree add --detach <另一个新目录> upstream-baseline
# backend: uv sync --python 3.12 --extra dev --frozen
# frontend: 使用 pnpm9.10.0，再 pnpm install --frozen-lockfile / pnpm build
```

Git config 不随 clone 恢复，需重新设远程防护/身份/凭据助手；凭证重新授权，运行数据另行恢复。原始 baseline worktree 仍需安装依赖；不能把 checkout 当作数据恢复。

远程尚未完成时，本机已有 bundle 可在另一个新目录恢复：`git clone --branch main <父目录>/.tools/backups/tick-stock-panel-custom-20261007.bundle <新目录>`。该恢复已实际验证，快照为 930eb1a；当前 Git 仓库可能有后续文档提交，恢复前核对快照与所需版本，不覆盖当前目录。

### 同步上游

```powershell
git status
git fetch upstream
git log --oneline main..upstream/main
git diff --stat main...upstream/main
git switch -c sync/upstream-YYYYMMDD main
git merge upstream/main
# 核对 custom、Provider、配置和金融口径；运行真实回归、lint/build
git push origin sync/upstream-YYYYMMDD
# 验收后再 merge 回 main，正常 push；不 reset --hard 或 force
```

同步分支保留本地自定义历史，冲突逐项解决。暂停 Actions 的恢复/发布策略以后按明确任务处理，本阶段不额外部署。
