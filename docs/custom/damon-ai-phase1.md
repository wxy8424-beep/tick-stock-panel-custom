# Damon AI Phase 1：独立页面与离线安全基础

基线：`772971dbb34c8accc1cd4b684f897bb11e523190`。开发分支：`feat/damon-ai-phase1`。

## 已实现边界

- 既有 Damon 扩展追加 `/damon/ai` 和导航；保留 `/anomalies`。不改首页、Dashboard、CN 或 HK/US Preview 调用链。
- 原创深色控制台复用 PageHeader、MarketSwitcher 和现有 Tailwind。窄屏切换对话/证据面板，支持键盘发送、清晰焦点、系统及页面减少动效。
- `voice.ts` 定义 chained/realtime 类型、会话/轮次/序号、转写、正文、音频、错误及各子状态；仅有 chained Mock 实现。未实现 Realtime adapter。
- Mock 无网络、麦克风权限、音频播放、模型调用或浏览器持久化。聆听/思考/播报均标为演示，不绘制假音频波形；消息最多 100 条，仅保存在当前页面内存。
- 停止先退休轮次，再取消 AbortSignal、定时器和待播状态。重复取消幂等；旧会话、旧轮次、倒序及重复事件不更新页面。结束会话/卸载释放资源。
- 后端契约 schema_version=1、冻结并拒绝额外字段；Profile 只允许 `damon.mock`。市场、数据模式和带时区 as_of 必须明确。
- real_cache/cache、historical/archive、preview/synthetic_fixture、simulation/simulated_event 严格对应；Preview 和模拟事件禁止 is_production=true。
- `ReadOnlyTurn` 默认工具表为空，不继承助手 dispatcher，不安装任何业务 handler，也不提供 HTTP 工具执行入口。只有服务端可信代码可注入 handler，测试仅注入离线函数。
- 拒绝未注册、写操作和上下文冲突。默认每轮 4 次、每工具 5 秒、序列化输出 4000 字符；硬上限分别为 8 次、30 秒和 8000 字符。取消整轮后不能继续执行。
- handler 必须为可信、协作取消的 async 函数。此策略不是任意代码沙箱；后续接入真实工具前必须审查副作用、阻塞及取消行为，不能用 read 标签代替审查。
- `GET /api/custom/damon/ai/status` 仅提供固定演示能力和随机 request_id，不读取配置/秘密。错误仅返回固定 code 和 request_id，不记录原始异常。

## 验证方式

前端按实际 import 区分 Vitest 与 node:test；Damon 测试为 Vitest。后端使用 uv 现有环境运行定向 pytest/Ruff。测试隔离 `.env` 与 DATA_DIR，模型和生产服务不参与验收。

验证范围包括注册保留、错误边界、键盘、窄屏面板、六种核心状态、启动/停止/释放、乱序迟到事件、Profile 白名单、证据来源、预算、超时、取消及错误不泄漏。

## 下一阶段

待用户确认后才讨论真实 STT/TTS、LLM Profile 调用、经审查的只读工具和持久化。当前页面不查询后端状态接口；状态接口作为后续接线边界，不另建前端请求客户端或 Query Cache。

本阶段不引入语音依赖或独立进程，不读取凭证，不改变现有助手/模型配置，不执行研究、回测、同步或交易。

## Phase 1.1 生命周期加固

- 扩展错误边界按路由 ID 挂载：Damon 渲染失败后切换 `/anomalies` 会创建新的边界；核心路由及旧助手不变。
- Mock 正文协议统一为 `assistant_delta` 增量片段，页面按轮次累积到同一条消息；`turn_done` 退休轮次并保留最终正文。旧 `assistant_text` 和用 state/idle 结束轮次的协议不再接受。
- 运行时校验会话/轮次 ID（1–128 个字母、数字、下划线或连字符）、正安全整数序号、事件白名单、字段和单片文本长度（最多 2000 字符），累计正文最多 8000 字符。当前协议拒绝音频事件。重复、倒序、旧会话及退休轮次事件不改变状态。
- 轮次错误退休当前轮次但保留连接，可发送下一条文字；连接错误清理定时器/AbortSignal 监听器并断开，必须显式重新开始会话。卸载先 dispose 再 abort，避免取消回调更新已卸载页面。
- 后端工具超时从派发开始计时；整轮 deadline 从 ReadOnlyTurn 创建开始计时，包括空闲。默认分别 5 秒和 30 秒（上限 30 秒和 120 秒）。清理另有默认 0.1 秒、上限 1 秒的等待额度；响应边界为执行期限加清理额度。
- 同实例默认最多 1 个在途 handler（上限 4）。调用预算在 await 前占用，不因失败、取消或重试退还。超时、取消、handler 异常、输出越界或证据冲突封闭实例并通知其他在途执行；该实例不能继续派发。
- 清理仅取消一次并有限等待，不使用可能无限等待的 gather/wait_for；返回 `cleanup_state=finished` 或 `still_running`。迟到的成功不会改变已返回的超时/取消结果。未退出任务保留跟踪并消费最终异常，不输出原始异常。
- Python 无法通用强杀协程。持续抑制取消的 handler 可以继续存在；同步阻塞事件循环时无法兑现墙钟期限。当前没有生产 handler，不提供隔离沙箱或跨请求准入；真实工具接入前须审查协作取消，必要时采用进程隔离及独立资源管理。

### 真实语音/工具执行接入 blocker

当前仍只有静态 status HTTP 接口，没有语音、对话或工具执行 HTTP 端点。以下均未实现，不能把本地 Mock 或单实例策略当成这些能力：

1. 服务端认证主体绑定 conversation/turn 与获准 Profile；每轮固定 Profile、市场、数据模式和 as_of，执行层校验，凭证仅通过既有服务端体系访问。
2. 跨请求/实例的并发准入、调用幂等、预算与 deadline 持续性，以及任务退出前资源占用的释放规则；重建实例不能成为绕过预算的机制。
3. 音频上传的格式白名单、大小/时长/采样率限制、超时和断连清理；当前既不上传也不解码音频。
4. STT 完成后经过服务端权限链调用经审查 Agent；不得 fallback 到完整旧 dispatcher，不允许转写/模型参数提升权限。
5. TTS 与 conversation_id/turn_id/序号绑定、真实播放器停止与释放、取消后的迟到音频拒绝；当前拒绝全部 audio_chunk，不能直接开启此协议。
6. STT/TTS/模型的安全错误映射、request ID、文字降级及恢复策略；真实服务未验证，Mock 失败恢复不代表真实服务可用。

验证使用现有 pytest/Vitest、离线 handler、假计时器和临时存储；真实连接、音频延迟及视觉浏览器验收仍未验证。
