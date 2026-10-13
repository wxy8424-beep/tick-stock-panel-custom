# CN Exchange Regulatory Anomaly — Rule & Data Contract Audit v1

审计日：2026-10-13。项目基线：main/48af83a89e92a975740ae30634f1dd18a238ca43。
结论：**NOT READY FOR IMPLEMENTATION — DATA SOURCE REQUIRED**。
本报告仅审计，不新增规则引擎、Provider、API、数据库或前端。没有实盘/交易建议。
“规则条款已确认”不等于“项目能按规则计算”，也不等于交易所已认定某股票异常。

## 1. 权威来源、版本与证据边界

| ID | 正式文件及官方链接 | 发布 / 生效 | 核验方式及限制 |
| --- | --- | --- | --- |
| SSE | [上海证券交易所交易规则（2026年修订），上证发〔2026〕41号](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml) | 2026-04-24 / 2026-07-06 | 发布通知显示现行有效；正文通过[官方同文页面](https://www.sse.com.cn/lawandrules/sselawsrules2025/fund/trading/c/c_20260424_10817739.shtml?f_link_type=f_linkinlinenote&flow_extra=eyJpbmxpbmVfZGlzcGxheV9wb3NpdGlvbiI6MCwiZG9jX3Bvc2l0aW9uIjowLCJkb2NfaWQiOiJmZGYxZWRkMjhiMTJhYjRiLWFkNGU0ODc4MTZhNDk4OTMifQ%3D%3D)的检索正文核验。该同文页缓存仍有“尚未施行”标记，日期效力以股票交易发布通知为准。暂缓实施附件未成功取得，相关细项不冒充已核验。 |
| SZSE | [深圳证券交易所交易规则（2026年修订），正式PDF](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)；[深证上〔2026〕551号通知](https://investor.szse.cn/lawrules/rule/trade/t20260424_620190.html) | 2026-04-24 / 2026-07-06 | PDF正文已读取；通知日期通过交易所检索结果核验。 |
| BSE | [北京证券交易所交易规则，北证公告〔2026〕17号](https://www.bse.cn/jygl_list/200028217.html) | 2026-04-24 / 2026-07-06 | 官方检索正文已核验；直接HTTP下载失败。公告明确部分条款另行施行，不能将整份规则每条均视为同日生效。 |

VERIFIED：对应官方原文直接支持；UNVERIFIED：本轮未获得足够依据；AMBIGUOUS：文字存在，但无法唯一推导执行算法。
检索未见后续取代上述异常条款的正式文件，不宣称已建立实时完备的规则修订监控。
第三方转载不作为本报告规则事实源；参考项目的注释和测试不是官方证据。

## 2. 五板块规则矩阵

以下阈值均以百分数展示，“达到”含本数；尚未编成生产常量。
“3日内”等窗口的精确枚举方式见第4节，不能直接采用参考项目的1..N扫描。

| 交易所 / 板块 | 异常条款 / 窗口 / 上下阈值 | 严重条款：10日 / 30日 | 10日同向异常次数 | 官方基准 | 公式、置信度 |
| --- | --- | --- | --- | --- | --- |
| SSE / 上海主板 | 5.4.2(一)：3日内 +20% / -20% | 5.4.3(二)(三)：+100%/-50%；+200%/-70% | 5.4.3(一)：4次 | 5.4.1：上证A股指数 | 5.4.2(一)区间收益差；阈值/名称 VERIFIED |
| SSE / 科创板 | 6.10(一)：3日内 +30% / -30% | 6.11(二)(三)：+100%/-50%；+200%/-70% | 6.11(一)：3次 | 6.12：上证科创板50成份指数 | 6.12明确个股与指数涨跌幅差；多日累计公式与通用章的继承/除权实现仍 AMBIGUOUS，不凭参考代码补全 |
| SZSE / 深圳主板 | 5.4.3(一)：3日内 +20% / -20% | 5.4.4(二)(三)：+100%/-50%；+200%/-70% | 5.4.4(一)：4次 | 5.4.1：深证A股指数 | 5.4.3(一)区间收益差；VERIFIED |
| SZSE / 创业板 | 5.4.3(一)：3日内 +30% / -30% | 5.4.4(二)(三)：+100%/-50%；+200%/-70% | 5.4.4(一)：3次 | 5.4.1：创业板综合指数 | 5.4.3(一)区间收益差；VERIFIED |
| BSE / 北交所 | 5.4.2(一)：3日内 +40% / -40% | 5.4.3(二)(三)：+150%/-60%；+300%/-75% | 5.4.3(一)：3次 | 5.4.4：北证50成份指数 | 5.4.4区间收益差；VERIFIED |

区间收益差：股票期末收盘相对期初前收盘的收益，减去同期指数相应收益。
不是逐日偏离值简单求和。沪深主板还存在换手率异常分支（SSE 5.4.2(二)、SZSE 5.4.3(二)），
以及各交易所认定的其他情形：只有价格分支的实现不得声称覆盖全部异常标准。
该换手率分支需要经证实的成交股数/可流通股本与交易日对齐，当前 quantity 边界不能绕过。

### 状态、排除日、除权及复牌

| 板块 | 上市/无涨跌幅限制证据 | ST/*ST与退市 | 除权除息要求 | 停复牌与重置依据 | 未决项 |
| --- | --- | --- | --- | --- | --- |
| 上海主板 | 3.3.13：IPO前5交易日、退市整理首日、重新上市首日及交易所认定情形；5.4.5排除无价格限制日 | 当前5.4.2价格分支为±20%，不能沿用旧±12%；历史ST状态及版本边界仍必需。退市整理其他日期的完整排除口径 UNVERIFIED | 5.4.2(一)要求期间除权除息调整；第4.3节参考价与具体跨期监管调整实现未完全核验 | 5.4.2/5.4.3规定公布次一交易日或复牌日起重算 | 暂缓附件、特殊排除及逐日状态证据未齐 |
| 科创板 | 6.12排除无价格限制日；新股前5日的专章完整依据本轮 UNVERIFIED，不能用Vibe注释充当证明 | 6.14不进入风险警示板；其他状态/退市排除逐日证据 UNVERIFIED | 一般规则与科创专章如何共同定义监管跨期调整 AMBIGUOUS；不直接认定qfq等价 | 6.10、6.11分别规定公布次一交易日或复牌日起重算 | 累计调整、上市和特殊排除细项 |
| 深圳主板 | 3.3.15：IPO前5交易日等；5.4.5排除无价格限制日 | 2026正文5.4.3主板统一价格阈值，无旧±12%分支；4.5.6排除退市整理期间 | 5.4.3：期间除权除息调整；4.4.1–4.4.3规定参考价及其日涨跌基准作用 | 5.4.5规定公布次一交易日或复牌日起重算；4.3节公告提供停复牌时间 | 临时停牌与全天停牌的重算适用区别 AMBIGUOUS |
| 创业板 | 同3.3.15、5.4.5；不能根据代码推断处于第几上市交易日 | 5.4.3价格阈值±30%，不自动套主板ST规则；逐日状态仍缺 | 同5.4.3、4.4章；不能使用未经证实的来源复权替代 | 同5.4.5及4.3章 | 排除与事件历史完整性 |
| 北交所 | 3.3.12确认公开发行上市首日、退市整理首日；其他特殊情形清单本轮 UNVERIFIED；5.4.5排除无价格限制日 | 当前5.4.2价格阈值±40%；特殊状态排除全部细项 UNVERIFIED | 5.4.4要求跨期调整；5.2.3除权日行情前收盘为除权参考价 | 5.4.5公布次一交易日或复牌日起重算；停复牌正式时间需公告 | BJ股价与指数历史尚无项目契约 |

当前版本中没有观察到上述价格异常条款的独立ST阈值，不意味着ST日状态、旧版本或其他特别规定可以忽略。
不能从当前证券名称推断历史ST状态，也不能把所有退市整理、临时停牌排除规则归纳成一个未证实布尔值。

## 3. Regulatory benchmark contract

| 板块 | 名称与标识依据 | 项目现有候选symbol | 现有历史入口 | SDK/官方历史候选状态 |
| --- | --- | --- | --- | --- |
| 上海主板 | 上证A股；[上交所指数资料](https://www.sse.com.cn/aboutus/publication/factbook/documents/c/10170572/files/36d0635dee474838943e931bcc04c3df.pdf)列000002 | 000002.SH | Historical Provider拒绝指数 | AKShare指数函数可研究，当前版本/该标的真实覆盖UNVERIFIED；官方指数历史可候选，连续期间/许可待验 |
| 科创板 | 科创50；[中证官方](https://www.csindex.com.cn/)列000688 | 000688.SH | 同上 | 同上；Longbridge的该标的Daily权限/价格语义未验证 |
| 深圳主板 | 深证A股；[官方指数公司方案](https://www.cnindex.com.cn/docs/gz_399674.pdf)列399107 | 399107.SZ | 同上 | 国证/深交所历史候选；AKShare、BaoStock该标的覆盖未验证 |
| 创业板 | 创业板综合指数；[官方发布公告](https://www.cnindex.com.cn/zh_information/notices_news/2010/201206/P020191213351696999459.pdf)列399102 | 399102.SZ | 同上 | 国证历史候选；不能用399006代替 |
| 北交所 | 北证50；[官方公告](https://www.bse.cn/bse_indices_news/200027851.html)列899050 | 899050.BJ | BJ及指数均不支持 | [官方历史点位文件](https://www.bse.cn/bse_indices_news/200013831.html?flag=bse_bz50)只证明公布过指定历史区间，不证明当前滚动历史完整；各SDK实际覆盖UNVERIFIED |

必须纠正“项目完全没有mapping”的表述：`backend/app/indicators/pipeline.py`已有上述首选符号。
但它也允许替代指数，甚至在全缺时任选可用基准；这不能复用为监管口径。
上证指数000001.SH、深证成指399001.SZ、创业板指399006.SZ不是本表指定基准。
当前Repository有`kline_index_daily`路径，不等于已证明数据齐全、来源、复权和版本正确。
本轮没有扫描用户Parquet内容、请求真实监管指数或验证stock/index日期覆盖；一律不冒充可算。
Longbridge报价/静态信息也不能提供整段历史交易所监管参考价和公告事件。

## 4. Reset / count / window的官方依据与执行缺口

| 问题 | 已证实 | 尚不能采用的推断 |
| --- | --- | --- |
| 初次算到阈值就重算？ | 条款锚点为交易所公布次一交易日或复牌日 | 计算日直接t+1重置不等于公布日t+1；必须获取实际公布时间 |
| 同向次数 | 主板10日4次，科创/创业/BSE10日3次，指相应异常条款情形 | 未确认的计算hit不等于正式异常事件；多份公司公告不能直接当多次 |
| 停牌/复牌 | 规则存在复牌日起重算文字及停复牌公告制度 | 缺bar不能区分假日、停牌、漏数；不能推断复牌日期 |
| 10/30日 | 正式严重异常指标与重算文字均存在 | 普通异常重置是否/如何影响严重累计、计数，与严重重置后事件集合保留的精确状态机需正式案例/解释 |
| 连续N日内 | 文本为N日内，阈值有明确边界 | 1..N全部子窗口、停牌跨市场日的计数方式不能仅凭Vibe测试定案 |
| 同日多条件 | 严重情形可同时公布 | 唯一event_id、计数去重、普通/严重同时触发的状态转移需证据 |

因此 **RESET SEMANTICS CONTRACT_BLOCKED**。这不是“官方没提重置”，而是锚点明确、项目缺事件输入和完整执行解释。
未来需按规则版本、公告日期/发布时间、事件方向、正式异常期间、恢复交易日形成可审计状态机；本轮不实现。

## 5. 所需 RegulatoryPriceEvidence / SecurityDayEvidence（仅规格）

- symbol、market、board、asset_type及有效起止日；不能只按代码前缀推断所有历史状态。
- 明确completed交易日、官方收盘、对应期初前收盘/参考价、官方指数同日点位及上一有效日。
- 除权除息标志、权益事件类型/生效日、官方参考价或已认证的监管跨期调整依据、调整方法/版本。
- 每日上市、重新上市、ST/*ST、无涨跌幅限制及原因、退市整理状态；精确effective_from/to与来源公告。
- 证券级停牌/复牌时间、全天/盘中区别；市场休市日期另存，不把行情缺口解释成停牌。
- 正式异常/严重异常公告ID、发布时刻、所属交易日、方向/期间/类别、重算起点及撤销/更正历史。
- 所有输入保留source、source reference、fetched_at、有效日期与可得时间；没有调整/状态证据返回blocked/null。

`none`只是来源价格模式；AKShare qfq、BaoStock qfq、Longbridge adjustment均没有证明与上述监管调整等价。
现有BaoStock仅none fallback，不允许顺便扩为qfq。CN统一结果未保存官方参考价/corporate action ledger。
官方日参考价也不自动证明整段调整序列；须给出跨事件窗口的可重算依据。

PIT：完成日D只用date<=D，盘中须先确认最近完成交易日；不得用当日盘中报价或未来指数。
按同一交易日期join，不按行号、不填假日、不forward-fill。date gate不等于source-level frozen PIT；
需保留历史修订、公司行动版本和公告可得时刻。禁止盘中regulatory projection。

## 6. Vibe-Research实现对照

只读参考commit：[d643728e79b955dfdcdcd8b0dd362bd7c90c35c8](https://github.com/simonlin1212/Vibe-Research/tree/d643728e79b955dfdcdcd8b0dd362bd7c90c35c8)。
已读orchestrator/src/finance/abnormal.ts、orchestrator/test/abnormal.test.ts、desktop/src/verticals/finance/lib/abnormal.ts、
desktop/src/verticals/finance/components/AbnormalCard.tsx、datasources/CATALOG.md及methodology/constitution.md。
没有复制production code、没有运行其测试；测试断言仅用于了解实现假设。

| 项目 | 官方/本项目要求 | Vibe实际实现 | 一致性 / 可采用性 |
| --- | --- | --- | --- |
| board/benchmark | 第2、3节 | 五板块对应相同指数名称/code | 名称/主要标识一致；本项目历史可用性仍需单独核验 |
| 异常/严重阈值与次数 | 第2节 | 主板20/4、科创创业30/3、BSE40/3，严重上下阈值分别设置 | 已核验数值一致；不直接移植为已生效生产规则 |
| 区间收益差 | 主板/SZ/BSE有明确公式 | proximity.cum使用股票区间收益减指数区间收益 | 算式一致；科创继承及调整证据未闭合 |
| qfq | 交易所监管调整证据 | tx_kline默认前复权作为价格序列 | 来源qfq不等于已认证监管调整，不能采用此假设 |
| 停复牌 | 显式证券状态/公告 | 股票前一bar比指数前一日更早就认为复牌 | 会将缺数误判停牌，不能采用 |
| 新股/no-limit | 实际上市与每日状态 | 返回不足80根且开始较晚推断上市；也将长停牌复牌按上市处理 | 与证据要求不符，不能采用 |
| reset | 官方公布次日/复牌日 | 算到abnormal令abnStart=t+1；算到severe令sevStart=t+1 | 没有正式公告输入，不能采用 |
| 次数 | 正式同向情形和重算 | 用计算abnHits按索引计数 | 有明确单测但非官方认定证据，不能采用 |
| 缺指数日 | 窗口不可算且显式说明 | 日期map对齐，缺日/紧接日跳过并重起累计 | 缺口显式化可借鉴；缺日导致重置不是已证实规则 |
| 短历史 | 不足窗口明确partial/blocked | 30日不足时按已有天数算并加notes | 能否作为官方窗口接近度需解释，不自动采用 |
| BSE | 未满足数据不得支持 | 规则表有BSE，但abnormalWatch排除BSE并写gap | 诚实降级可借鉴；CATALOG另有盘后包不等于该视图已使用 |
| 退市/ST | 每日状态与版本 | 当前名称正则过滤退市；代码注释采用2026主板规则 | 当前名不能代替历史状态，不能采用 |
| null/展示 | missing不伪造0 | Crit上下为null时showPair显示0%、critRatio取0；仅error行单列 | 必须区分真零与不可算，不能照搬 |
| completed-day | 本任务禁盘中projection | intraday允许最新当日K作为估算并提示 | 与本任务不同，不采用 |
| proximity | 分项可解释，含次数 | 总level取3/10/30价格ratio最大，次数单列 | 不等于全部规则overall，未来不将count/turnover隐藏 |
| evidence/UI | 源、时间、输入和缺口 | CATALOG/constitution强调证据；AbnormalCard展示分项、来源与gap | 可借鉴表达及可追溯性，不复制规则或React代码 |

## 7. 完整数据需求矩阵

P0为任何可信价格分支上线前必须解决；P1为更广覆盖/完整异常规则所需。H为高集成难度，M中，L低。

| 数据 | 规则/板块 | 现有来源与状态 | 风险/严重度 | 候选及官方存在性 | 难度/优先级 |
| --- | --- | --- | --- | --- | --- |
| A 股票Daily | 所有累计窗口，五板块 | AKShare/BaoStock沪深部分可用；BJ拒绝 | close不是已认证监管price evidence；关键 | 官方日行情、既有源经认证补证 | M/P0 |
| B 监管指数Daily | 五基准/同日收益差 | symbol映射存在，研究Historical入口拒绝；Repository内容未验证 | 错指数替代不可接受；关键 | SSE/CNI/CSI/BSE官方、AKShare指数候选、Tushare index_daily | M/P0 |
| C 除权/官方调整 | 跨权益事件窗口，五板块 | CN结果无事件ledger/参考价；qfq无等价证明 | 错价格尺度；关键 | 交易所/发行人权益公告、官方参考价、授权数据商 | H/P0 |
| D 上市日期 | IPO排除，五板块 | 历史契约无上市日期 | 短序列不能推IPO；关键 | 官方上市公告；BaoStock basic候选未验真实字段/覆盖 | M/P0 |
| E 每日限价状态 | 排除日/首次上市/重新上市 | 未保存每日有无限制及原因 | 单看涨跌停价格不能证明原因；关键 | 交易所交易提示、Tushare stk_limit与正式状态联合 | H/P0 |
| F ST/*ST历史 | 特殊状态/版本边界 | 当前名称不足；BaoStock SDK示例有isST但adapter未取 | 当前状态不能回推；关键 | 正式实施/撤销公告；候选每日ST字段需验 | M/P0 |
| G 停复牌 | 排除、复牌重算 | BaoStock tradestatus=0被剔除；AKShare缺bar不表原因；Longbridge当前security status非历史台账 | 缺口不等于停牌；关键 | 官方公告/交易提示；Tushare suspend_d；保留BaoStock状态候选 | H/P0 |
| H 正式trigger公告 | 次数、reset，五板块 | 未接交易所异常公开信息/正式公告 | 算到阈值不能替代认定/公布；关键 | 三所交易公开信息及公司异常/严重异常公告 | H/P0 |
| I benchmark日历 | 同日对齐、交易日计数 | 现有market calendar不证明证券和指数全历史日状态 | 假日/缺数/停牌混淆；关键 | 官方年度休市公告+指数历史日记录 | M/P0 |
| J BJ历史 | BSE各窗口 | 当前ticker guard拒绝BJ，无Fallback | 不得伪支持；关键 | 北交所官方/授权沪深京数据、候选商实际覆盖待验 | H/P1（BSE上线为P0） |
| K 换手率/流通股本 | 沪深主板其他异常分支 | quantity/历史股本标准尚未闭合 | 不能声称完整标准；关键 | 官方流通股本变动、认证日换手率来源 | H/P1（完整覆盖为P0） |

## 8. Candidate Source Report（仅研究，不接入）

| 候选 | 可解决/覆盖 | key/费用/历史 | 调整与停牌语义 | 许可、稳定性及架构影响 |
| --- | --- | --- | --- | --- |
| 三交易所官方公告/交易公开信息 | 沪深京：H、D、E、F、G、C及规则 | 公开页面可读；自动化/完整历史/API授权及费用UNVERIFIED | 最适合作认定/状态/权益事实源；需文档ID、时间、勘误和事件解析 | 网页结构/下载可不稳定，本轮HTTP失败已实见；批量/再分发须核许可。只建获授权的证据adapter，不改实时链路 |
| CNI/CSI/SSE/BSE官方指数 | B、I；对应五指数 | 页面及部分历史文件存在；滚动历史、key、授权费用UNVERIFIED | 需价格指数/收益指数、日点位、编制变更区别；不提供股票停复牌 | 核验许可与缺日后才能接统一历史指数契约，不能复用替代指数fallback |
| 当前Longbridge | CN行情/历史候选 | 已有三凭证；官方[历史K线文档](https://open.longbridge.com/zh-CN/docs/quote/pull/history-candlestick)显示行情/账户额度条件，真实指数和BJ权限未验证 | adjustment不证明监管等价；当前security status不证明历史停复牌 | SDK可靠性不等于所需能力已获证。不得解锁现有Daily capability；账户操作不在授权范围 |
| 当前AKShare | 股票/指数候选 | 公共抓取通常无需账户；具体源授权/长期覆盖待核 | 当前qfq来源语义保留；股票缺bar不提供完整状态台账 | [官方维护源码的指数函数](https://github.com/akfamily/akshare/blob/main/akshare/index/index_zh_em.py)存在，但本机五指数未smoke；Eastmoney前阶段upstream_reset。仅研究，不能保证恢复 |
| 当前BaoStock 0.9.4 | 沪深basic、Daily、tradestatus/isST、权益候选 | 已有匿名接口；本阶段不新增请求。SDK示例包含相关字段，完整历史/五指数/BJ覆盖UNVERIFIED | 保留停牌/status是可能方向；factor/dividend函数不等于官方监管调整 | 模块已有隔离/超时；扩展状态历史须新契约验收，现none fallback保持不变；数据许可/再分发另核 |
| Tushare Pro（未接入） | 日线、指数、停复牌、涨跌停等组合候选 | 用户token/接口权限必需；[index_daily](https://tushare.pro/document/1?doc_id=95)、[suspend_d](https://tushare.pro/document/2?doc_id=214)、[stk_limit](https://tushare.pro/document/2?doc_id=183)文档列2000积分起等权限；积分不是已确认购买报价 | 可补状态输入，但adj_factor不自动证明监管等价；各板块/日期完整覆盖须真实验收 | **USER DATA SOURCE ACTION REQUIRED**：注册/确认权限、预算和许可。商业或再分发条款未核验；不安装SDK，不索取聊天明文token |

以上来源互补而非一个API必然解决全部问题。没有承诺公开页面可无限抓取、免授权再分发或具有冻结PIT。
官方材料获取困难可以记录UNVERIFIED，不用第三方摘要补成事实。

## 9. Final support / readiness

| Board | Rule contract | Price | Benchmark | Corporate action | Suspension | Listing/no-limit | Reset evidence | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 上海主板 | 阈值确认/特殊与执行细项未闭合 | 部分 | 映射有/历史未证 | 缺 | 缺 | 缺 | 条文有/事件缺 | CONTRACT_BLOCKED |
| 科创板 | 阈值确认/累计调整继承未闭合 | 部分 | 同上 | 缺 | 缺 | 缺 | 条文有/事件缺 | CONTRACT_BLOCKED |
| 深圳主板 | 核心条款确认/完整执行需解释 | 部分 | 同上 | 缺 | 缺 | 缺 | 条文有/事件缺 | CONTRACT_BLOCKED |
| 创业板 | 核心条款确认/完整执行需解释 | 部分 | 同上 | 缺 | 缺 | 缺 | 条文有/事件缺 | CONTRACT_BLOCKED |
| 北交所 | 核心条款确认/特殊排除待补 | 无入口 | 映射有/历史未证 | 缺 | 缺 | 缺 | 条文有/事件缺 | UNSUPPORTED |

**BSE REGULATORY PROXIMITY: UNSUPPORTED — DATA CONTRACT BLOCKED**。
US不适用、HK未实现，基金/债券/B股不得套A股规则。

最小解阻数据集合：一个拟支持板块的正式规则执行解释 + 可追溯股票/指定指数完成日序列 +
完整权益调整证据 + 每日上市/限制/ST/退市/停复牌状态 + 正式异常事件/公布时间/重置边界 +
股票/指数日历对齐及来源版本。30日窗口还需前置收盘与足以确认之前重置的事件历史，固定80根不保证充分。
如只获准做价格分支，必须明确排除换手率/交易所其他认定，不能命名为“完整监管异常判定”。

需用户决定：先支持哪个板块/是否仅价格分支；选择官方证据组合与是否评估Tushare等授权来源；
若采用商业/积分源，确认账号权限、费用与使用许可。之后再授权小范围真实数据诊断，不能直接开始生产算法。

## 10. 审计验证与Git范围

本轮仅新增此文档。没有生产测试/算法fixture/监管smoke，测试与build为NOT RUN（文档任务不需要full suite）。
参考源码只读，固定commit；官方条款及未证实处均显式标记，检索/下载失败不等于规则不存在。
后续验收必须包含除权、公告滞后、停复牌、排除日、指数缺日、规则版本边界的官方可对照案例。
文档检查、敏感扫描与staged审查通过后方可作为审计文档单独提交；不是生产功能验收或上线承诺。
