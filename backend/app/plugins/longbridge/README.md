# Longbridge realtime-only

使用官方 `longbridge` SDK 的 `Config.from_apikey` 与 `QuoteContext`。
只调用 `quote()` 和 `static_info()`，无交易、账户、订阅或历史行情能力。
SDK 按 `backend/uv.lock` 安装：`uv sync --frozen`。

认证优先读取 `data/user_data/secrets.json` 中完整的三凭证 bundle。
没有本地 bundle 时，从项目现有 `.env` / 进程环境读取以下三项，进程环境优先：
`LONGBRIDGE_APP_KEY`、`LONGBRIDGE_APP_SECRET`、`LONGBRIDGE_ACCESS_TOKEN`。
部分本地 bundle 不与环境变量混用。缺失时插件不可用，不创建 context。Context 延迟创建、复用；`close()` 清除引用与
元数据缓存（SDK 5.2.0 没有公开 `close` 方法）。禁止将凭证写入日志或 Git。

设置 → 数据源 → Longbridge → 配置凭证可输入三项 password 字段。
`POST /api/settings/longbridge-credentials` 先用候选 bundle 创建独立 QuoteContext，
只读请求 `700.HK` 报价；通过后用现有原子写入一次保存三项并 reload registry。
失败不落盘。GET 只返回脱敏 App Key、Secret/Token 存在性与配置状态，
不提供明文查看；DELETE 同时清除三项本地字段，环境后备仍可生效。
可用性状态表示 SDK/配置就绪；行情是否成功须通过只读请求验收。

按配置 `longbridge_realtime_symbols` 和现有自选列表合并、去重请求，每批最多500码。
失败批次返回固定错误分类，其他成功批次保留。币种取官方 `static_info.currency`
并缓存在 context 生命周期中；无法获取时保留 null，不能按后缀猜币种。

字段：`last_done → last_price`、`turnover → amount`；OHLC 与 prev_close 按实际报价映射。
`change_pct = (last_done - prev_close) / prev_close`，保持小数制；无有效前收时为 null。
SDK datetime 转 Unix 毫秒：aware 值直接转换；5.2.0 官方绑定将 epoch 通过
`from_timestamp(epoch, None)` 转为本机 local naive datetime，使用 `timestamp()` 逆转换，
不按市场猜时区。官方源码依据：
[v5.2.0 time.rs](https://github.com/longbridge/openapi/blob/v5.2.0/python/src/time.rs#L45-L51)。

官方文档没有确认 CN quote.volume 的股/手单位，因此全部标准 volume 保持 null。
CN 标记 `volume_unit=unverified`，HK/US 标记 `unsupported`。
本阶段 CN 报价可通过 Provider 只读获取，但不能进入 CN daily/enriched、监控、
market overview 或 final。按码批次也不能覆盖 CN 全市场分区。
港美通过现有独立内存快照缓存提供基础报价，后台仅在对应 market session 的
regular 时钟窗口轮询。现有 HK/US 时钟不是权威假日日历。
手动 refresh 可获取已配置标的的最新快照，包括休市快照。

只读验证（backend 目录）：`uv run --frozen python -m app.plugins.longbridge.smoke`。
该命令固定只请求 600519.SH、700.HK、AAPL.US，只输出存在性、时间及固定错误分类。

参考：[报价契约](https://open.longbridge.com/zh-CN/docs/quote/pull/quote)、
[静态信息](https://open.longbridge.com/zh-CN/docs/quote/pull/static)、
[Python SDK](https://longbridge.github.io/openapi/python/reference_all/)。
