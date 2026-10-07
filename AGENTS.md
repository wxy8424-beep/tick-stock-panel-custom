# AI 开发入口

修改、调试或审查本仓库前，必须完整阅读并遵循根目录的 [`CONTRIBUTING.md`](CONTRIBUTING.md)。其中定义了项目架构、数据契约、数据源插件化、缓存与性能要求、测试矩阵以及 PR 复审和合并标准。

涉及代码二次开发、前端插槽、后端可替换策略、扩展注册或上游升级兼容时，还必须阅读 [`docs/secondary-development.md`](docs/secondary-development.md)。该文档区分当前已实现能力与目标扩展契约；不得根据设计示例虚构尚不存在的 API。

同时遵守以下规则：

- 先理解调用链和现有测试，再进行修改。
- 保持实现简单、改动范围最小，不处理无关问题。
- 不覆盖工作区已有修改，不虚构测试或审查结果。
- 以实际验证结果作为完成标准。

## 私有二次开发规则（2026-10-07）

本仓库保留 shy3130/tick-stock-panel 的完整 Git 历史与 MIT LICENSE。初始化审计、真实验证结果、恢复与上游同步步骤见 [docs/custom/phase1-initialization.md](docs/custom/phase1-initialization.md)。

- `origin` 必须是用户的 PRIVATE 仓库 `wxy8424-beep/tick-stock-panel-custom`；原作者地址仅作 `upstream`，禁止向其 push。首次导入标签 `upstream-baseline` 指向原始 SHA，不能把导入恢复点或测试失败版本冒充全面验收稳定版。
- 收到业务需求先报告：需求理解、现有能力、L1/L2/L3、预计修改文件、上游兼容影响、测试方案，然后按明确需求直接实施。先搜索已有实现及测试，不建立第二套行情、缓存、Provider、策略、回测、API client 或 Query Cache。
- L1 优先使用配置、策略/信号/因子、扩展数据与已有 Provider/插件；L2 使用真实已实现的前后端扩展注册。自定义 namespace 固定 `damon`，前端 `src/custom/damon/extension.tsx`，后端 `app/custom/damon.py` 或具有 `__init__.py` 的 `app/custom/damon/` 包；使用哪个入口须先核对当前加载器。
- L3 前必须说明 L1/L2 为什么不能满足、具体核心文件、同步冲突与回归测试。评分/仓位/风控等文档设计示例不是现成可替换 API。不得为方便而复制整个页面或 engine。
- Provider 边界必须明确百分数/小数、量/金额单位、raw/qfq、北京时间/UTC、交易日与 PIT。新增源显式声明单位；不采用现有代码遗留的猜单位分支，不伪造能力或行情。通过现有 API→Service→Provider/Repository 链路消费数据。
- 后端保持 uv/pyproject/uv.lock；前端保持 pnpm/package/pnpm-lock，使用 packageManager 声明版本。测试运行器须按文件真实实现区分 Vitest 与 node:test，不执行不存在的 `pnpm test`。
- 重要任务先检查 Git 和用户修改，必要时建立恢复 commit 并 push。main 用于验收版本，大功能 feature/、修复 fix/、上游同步 sync/upstream-YYYYMMDD；同步采用 merge 和回归测试，不以 reset/rebase/force 覆盖用户历史。
- 用户已授权日常逻辑完整阶段的 Conventional Commit 和向 PRIVATE origin 的正常 push，不必重复询问普通提交权限。逐文件暂存，审查 diff/敏感内容，核对私有属性，再提交；push 后比较本地 HEAD 与远程 SHA，未一致不得报告备份成功。
- `.env`、凭证、个人账户/持仓、运行数据、日志、数据库、缓存、依赖不入 Git；已有敏感文件只取消跟踪并保留原件，历史秘密暂停 push，不自行重写历史。data 下私有策略也是运行数据；需要恢复的非敏感策略源码另存审查后的版本化模板。未知修改不覆盖，禁止危险 Git 操作或删除远程/分支/标签。
- 重要会话遵守父目录的 Obsidian 记忆库规则，更新持久项目状态及未解决事项，不保存凭证或聊天转储。本阶段只做初始化，不主动开发业务功能或执行实盘交易。
