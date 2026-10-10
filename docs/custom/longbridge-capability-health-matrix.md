# Longbridge capability health matrix

2026-10-10；基线6272aec；本阶段只做可观测性，不解锁数据能力。

## 权威与接线

既有Longbridge.market_capabilities（financial.market_capabilities复用quantity_capabilities）是唯一契约来源。
现有settings/data-sources插件列表新增可选provider_health，按dataset→market派生；
保留market_capabilities、全局capability-matrix路由契约，无新endpoint、公共状态枚举或重复路由系统。
每项provider/market/capability/status/status_label/reason/message/usable/runtime。
中文reason消息由backend固定白名单生成；前端不再维护Longbridge blocker翻译表。
未知contract状态fail closed，未知reason不透传原文。

| 能力 | CN | HK | US |
| --- | --- | --- | --- |
| realtime | supported | supported | supported |
| daily | contract_blocked | contract_blocked | contract_blocked |
| minute | contract_blocked | contract_blocked | contract_blocked |
| depth5 | contract_blocked | contract_blocked | contract_blocked |
| financial | empty | contract_blocked | contract_blocked |

supported=满足契约；contract_blocked=缺少安全适配证据；empty=代表证券合法空响应；
unsupported=未提供能力，不自动等于SDK没有方法；unavailable=运行条件不可用。
SDK方法不存在只在具体诊断中sdk_method_unavailable，SDK缺失是sdk_missing，不误标EMPTY。
contract可用+已声明dataset+provider可用，且最近诊断无失败/空数据，才标usable。
not_checked表示未诊断，不假装已完成实时网络探测。此健康视图不改变业务路由或provider能力声明。

## 最近运行状态

runtime包含availability（available/empty/unavailable/not_checked）、diagnostic_code、
安全中文message、UTC last_checked、代表symbol；与contract状态并列。
US financial upstream_available + contract_blocked为正常组合，不显示“服务中”。
复用现有financial/quantity显式只读探针结果，按dataset/market记录本进程最近一标的；
不代表全市场成功，也非账号长期权限承诺。未运行探针显示本进程尚无记录。
记录内存有独立锁；provider.close/registry reload清除，不写data、日志或数据库。
外部独立smoke进程不会将记录注入正在运行的Dev服务，页面不会凭历史文档伪造最近诊断。
GET settings只读快照，不创建SDK context、不自动探测、不增加轮询系统。
realtime业务路径不改；本阶段未采集额外realtime请求状态，所以默认not_checked。
原有TickFlow/fuyao/stock-sdk继续使用原metadata/卡片，健康字段可选。

## 展示与安全

现有数据源卡片按capability显示CN/HK/US契约状态、backend中文blocker及最近运行信息。
健康字段缺失沿用旧status标签；unknown status显示状态未知，unknown reason不显示原始字符串。
frontend仅显示backend提供的契约事实，不根据provider/market/HTTP200/返回值推断支持。
通用标签及服务中路由标记仍属于UI文案；无前端quantity/financial判断逻辑。
runtime只复制白名单code及固定消息，不复制异常全文、credential、账户、原始报表或原始SDK数据。
快照symbol经过有限格式检查；last_checked仅为诊断时间，不是数据交易时间。

## 后续解锁

数量单位仍需market+endpoint官方依据：[quantity evidence](longbridge-quantity-unit-evidence.md)。
financial period_end仍需编码/单位/业务日期时区依据：[period evidence](longbridge-financial-period-evidence.md)。
US实际availability见[US diagnostics](longbridge-us-financial-availability.md)。
本阶段不转换数量、不转换fp_end、不伪造公告日期、不声明financial dataset。

## 验证记录

- Backend targeted152 PASS，新增health测试18项；最终full2820 passed/6 skipped/0 failed。
- 首轮full两项未修改Windows回测worker退出码异常；两项单独复验PASS，完整重跑PASS，未改回测代码。
- Python新增违规0；loader原有10项Ruff问题与HEAD基线一致，未清理。
- Settings前端13 tests PASS；pnpm build/tsc PASS，保留历史chunk体积warning。
- pnpm lint不可执行：现有脚本使用eslint但项目缺少eslint命令；未安装额外依赖或改配置。
- 现有settings响应mock接线验证PASS，GET无SDK调用；本轮不增加真实Longbridge请求，不重新探测单位。
- 9候选文件真实凭证匹配扫描0违规；diff --check PASS。
