# CN Regulatory Data Source Evaluation v1

评估日：2026-10-13；基线：main/d1ca99433f7b408f2b3ab96475e95606ae9ef510。
范围：深圳主板 PRICE-RULE BRANCH 的数据可行性；纯文档，不修改生产代码、契约或数据。
结论：**PRICE RULE NOT READY**；**FULL REGULATORY CONTEXT NOT READY**。
上一阶段的 [规则审计](cn-regulatory-anomaly-contract-audit-v1.md) 继续有效；不重新审计其他四板块。

## 1. Scope / readiness 定义

Price Rule Ready：已完成日、适用证券、指定指数、监管调整和排除日均有证据，窗口定义可确定复算。
这里可以不实现完整公告/count/reset overlay，但不能把未经 reset 的滚动窗口称为交易所已认定异常。
如果输出宣称已按实际监管重算起点计算，则公告/复牌 reset 输入仍不可省略。
Full Regulatory Context Ready：另有完整正式事件、发布时点、同向重复计数、reset、更正历史和其他适用分支证据。
本评估只针对价格分支；即使将来 Price Ready，也不覆盖换手率及交易所认定的其他情形。

证据等级：VERIFIED=特定事实直接核验；PARTIAL=部分字段已证明、完整契约未满足；UNKNOWN=未证明；UNSUITABLE=当前能力不适用。
候选矩阵的 confidence 指该来源对本任务的契约贡献，不是网站权威性/公司信誉评分。
公开文档、公开文件访问和真实结构化历史请求是不同验收层次；文档样例不是本机账号数据验证。

## 2. Shenzhen main-board required contract

权威基线：[深交所2026交易规则正式PDF](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)，2026-04-24发布、2026-07-06生效；沿用上一审计已核验条款。
5.4.1的基准是深证A股指数，标识399107；不是深证成指399001。
5.4.3(一)累计偏离是股票区间收益减同期间指数收益，非逐日偏离求和；期间除权除息需相应调整。
3日内主板±20%；5.4.4的10/30日价格情形与重复异常次数是不同分支；本轮不实现阈值常量。
5.4.5排除无价格限制日，规定公布次一交易日或复牌日起重算；4.5.6排除退市整理期间。
窗口枚举、临时/全天停牌重算及普通/严重重置相互作用的执行歧义仍保留，不能用Vibe补规则。

| Domain / field | Required semantics | Missing policy |
| --- | --- | --- |
| stock symbol / board / asset_type | 证券身份及板块的有效期间；仅代码前缀不能证明历史身份 | blocked |
| trading_date / completed | 交易所交易日期和完成状态；stock/index严格同日对齐 | 不补日、不forward-fill |
| official close | 未任意复权的正式日收盘，保留精度、版本及修订 | null/blocked |
| previous official close / reference_price | 前一官方收盘与当日除权参考价分别保存，不混作一个pre_close | 必须提供字段定义 |
| corporate_action / ex_date | 现金、送股、转增、配股及其他事件；最终实施而非预案 | unknown不当无事件 |
| official ex-right reference / adjustment evidence | 当日官方参考价，或能按正式依据严格重算的输入；多事件窗口的调整方法及版本 | generic qfq不能替代 |
| trading / suspension / resumption | 逐日及必要的精确时点；全天与盘中停牌区分，复牌有公告依据 | 缺bar不推断停牌 |
| price-limit / listing / no-limit | 当日是否限价、理由、IPO/重新上市日期和交易日序号；交易所其他特殊情形 | unknown不进入可信窗口 |
| ST / *ST / risk-warning / delisting | 有效期间和公告出处；历史版本适用性，退市整理排除 | 不从当前简称反推 |
| benchmark_id / close / previous_close | 399107的官方价格指数点位及其前一有效日；不能替代指数/收益指数 | 无替代、无填补 |
| benchmark methodology / calendar | 官方指数编制/调整语义与交易日版本，不能套股票qfq；该指数公司行动通常反映在指数方法中 | 具体方法未验标UNKNOWN |
| source / dataset / source_version | 发行者与传输vendor分别标识，schema及许可版本 | 不宣称vendor即authority |
| observed_at / fetched_at / effective_period | 发布时间、抓取时间、数据适用期分别记录，历史修订保留 | 日期截断不等于源级PIT |
| evidence_id / raw_reference | 原始文件URL+hash+页/字段定位，或授权数据批次引用 | 结果必须可追溯 |

价格偏离示意：100 × [(stock_end / adjusted_stock_base − 1) − (index_end / index_base − 1)]。
此处 adjusted_stock_base 是待证明的监管跨期调整口径，不是现有qfq字段；实际执行定义仍需官方例证封闭。
不同期间的官方参考价如何串联，不能仅凭这一示意式推导生产算法。

## 3. Existing source assessment

只读核对当前源码：`backend/app/data_providers/historical.py`、`baostock_daily.py`、`backend/app/indicators/pipeline.py`及上一阶段Longbridge契约。

| Source | 当前项目实际能力 | 候选能力与缺口 | Regulatory suitability |
| --- | --- | --- | --- |
| Longbridge 5.2.0 | 实时快照、security-level状态；现有边界不解锁Daily | [官方历史K线API](https://open.longbridge.com/zh-CN/docs/quote/pull/history-candlestick)存在不等于本项目已验证399107、官方参考价、CA、历史ST/停复牌；需账号与行情权限，未调用 | 当前realtime能力UNSUITABLE；未验证历史能力UNKNOWN |
| AKShare | CN stock_zh_a_hist，源标明Eastmoney；raw none与独立akshare_qfq；无官方前收/参考价/CA ledger/证券状态历史 | 是网页数据wrapper而非监管authority；[官方源码index_zh_em](https://github.com/akfamily/akshare/blob/main/akshare/index/index_zh_em.py)有指数历史函数，但当前版本399107覆盖/日期完整性/稳定性未probe | PARTIAL，普通OHLC可研究，不能签监管contract |
| BaoStock 0.9.4 | none模式fallback；字段date/code/OHLC/tradestatus/adjustflag；丢弃tradestatus=0行；无volume、无证券状态对外输出 | [SDK资料](https://pypi.org/project/baostock/0.9.4/)及安装示例有preclose/isST、基础资料/分红/复权接口候选；当前adapter没有保存这些证据；399107/配股/状态完整历史未实测 | PARTIAL；SDK字段可用性不等于监管语义 |

CN factory限制股票范围，拒绝指数；Repository存在kline_index_daily不证明来源和连续历史齐全。
enriched已有399107首选，但允许399001等替代、甚至任意可用指数，故 **UNSUITABLE AS REGULATORY INPUT**。
三来源均没有在当前项目中证明完整官方调整、每日特殊状态及正式事件链；本轮不请求用户凭证、不解锁能力、不扫描用户行情库来冒充来源验证。

## 4. Official source assessment

| Official source | Public / format / login | Historical depth / update | Contract contribution / automation / rights |
| --- | --- | --- | --- |
| [SZSE主板公开栏目](https://www.szse.cn/www/certificate/maind/)与[官方栏目导航](https://www.szse.cn/application/publicindex/header/index.html) | 公开HTML，主板、交易公开信息、风险警示、停复牌及上市公告目录；本次页面GET无需登录 | 页面有日期查询入口；逐证券完整状态历史、最早可用日及机器接口SLA UNKNOWN；按公告/交易日发布 | 适合作authority locator；没有验证稳定JSON/CSV/XLS历史导出，不将网页GET当自动化许可 |
| [CNI / 国证指数](https://www.cnindex.com.cn/) | 公开HTML/PDF；[官方方案](https://www.cnindex.com.cn/docs/gz_399674.pdf)确认399107名称/身份 | 本次PDF证明标识，不证明日线历史。399107 close/preclose的最早日、完整下载、频率/SLA UNKNOWN | 官方指数历史首选；公开显示不等于授权机器历史供应，需确认具体导出字段、价格指数版本、许可 |
| [CNINFO巨潮资讯](https://www.cninfo.com.cn/) | 公开检索页面及公告PDF；本次单PDF无需登录；商业API与公开页面权限不能混同 | 公司公告按事件更新；本次只验证一份2026实施公告，完整历史/检索漏报率/结构化接口 UNKNOWN | 公司行动实施和发行人披露的原始证据候选；公司公告不自动等于交易所正式异常公布 |
| SZSE交易规则、休市通知、上市/停复牌/风险警示文件 | 公开HTML/PDF公告；不建立爬虫 | 可追溯到具体发布文件；完整历史汇编与每日状态快照 UNKNOWN | 交易日/有效期authority；休市日历不能替代证券停牌/无价格限制状态 |

公开来源目前足够做内部小规模证据核验；是否允许持续自动下载、长期存储及再分发未完成许可确认。
未证实生产自动化授权；不推断“无需登录=无限免费API”。证据收集也须尊重站点访问约束，不能绕反爬/登录。

### Minimal public probes（本机真实执行，无账号、无下载落盘）

项目外`.tools/probe-sz-regulatory-public-sources.py`，标准HTTPS校验，15秒timeout/文件上限1MiB，每URL一次，无SDK/凭证/cookie；未保存原文。

| Probe | Result | Sample/schema evidence | What it does NOT verify |
| --- | --- | --- | --- |
| SZSE主板上述HTML | HTTP200，61,475bytes；SHA256 33c7d3260f77f7007aa850aa8834fd0bd4ce0223784fc5396bd61541595fd106 | HTML目录可达；浏览器读取见主板/上市/风险信息入口 | JSON schema、完整历史、自动化许可 |
| CNI gz_399674.pdf | HTTP200，413,760bytes，PDF magic；SHA256 f43e5ba14c83152516323e18600c980c597fe5ff67f7159be2ce9b659d44e43e | 官方标识材料，承接上一审计399107证据 | 不是399107 Daily样本/历史下载 |
| [平安银行000001，2026-025实施公告](https://static.cninfo.com.cn/finalpage/2026-06-05/1225352449.PDF) | HTTP200，139,278bytes，PDF magic；SHA256 8e9d5facebfd8c46e049f0e6b0839e2be31ef292a5e3db903591fc08be9af5b8 | PDF正文核验：本次现金每10股3.60元含税，无送转；登记2026-06-11、除息2026-06-12 | 不含完整官方价格参考历史，不证明混合配股/特殊公式/其他证券历史 |

公告样本区分本次实施与全年累计及个人税后金额；不能将税后股息当官方除息输入。
网页检索对CNI动态查询页有解析失败，本机静态PDF成功；不能据此宣布官方历史接口存在/不存在。
历史可用性：仅证实以上具体材料；Daily row/多年连续状态数据 **NOT VERIFIED**，不能因访问成功标READY。

## 5. Account / paid source assessment

未注册账号、未购买、未读取token发请求；以下只核验provider公开文档。账号真实权限与套餐报价均未验。

**Tushare Pro — 推荐的下一轮结构化候选，不是监管authority。**

- [index_daily](https://tushare.pro/document/1?doc_id=95)明确区分399107与399001；指数历史/stock Daily候选需逐标的覆盖与价格定义核验。不能在此写“已取得399107”。
- [dividend](https://tushare.pro/document/2?doc_id=103)：有实施进度、送/转、税前税后现金、登记/除息/实施公告日期；文档称2000起、晚间更新、2000积分。示例又含更早日期，准确历史边界待实测；配股/特殊参考价与监管调整等价性未证明。
- [suspend_d](https://tushare.pro/document/2?doc_id=214)记录S/R、日期及停牌时间，文档起点2000-01-03；[stk_limit](https://tushare.pro/document/2?doc_id=183)含pre_close及上下限。pre_close是否除权参考/源计算值、无价格限制日的空值原因必须另验，不能只由缺字段推状态。
- [stock_basic](https://tushare.pro/document/1?doc_id=25)有上市/退市日期、板块及当前上市状态；不能用当前状态重建每日历史ST/no-limit/退市整理。
- [stk_shock](https://tushare.pro/document/2?doc_id=451)、[stk_high_shock](https://tushare.pro/document/2?doc_id=452)公开列公告日期、原因、期间、交易市场，权限6000积分。实际历史深度、原始公告ID/发布时刻/修订、完整性未验。示例含证券后缀与市场描述需核对的组合，不可盲接；不能直接当reset/count authority。
- Python SDK/API已公开；账号与token需要，免费额度/付费/积分权限按dataset区分，最终费用UNKNOWN。积分门槛不是报价。本轮不要求用户提供token。
- 深圳主板范围：文档含SZ证券示例，但全历史覆盖UNKNOWN；API稳定性只到公开schema层面，SLA/字段修订UNKNOWN。集成复杂度中，锁定风险中；价格/CA/state/announcements分别落source版本，不将一家vendor数据当全域权威。
- 许可：内部保存、自动访问、原始/派生再分发需确认当前条款；开源SDK许可不等于商业数据许可。

**Wind / 机构数据授权 — 后备询价候选。**

[Wind官方市场数据页面](https://www.wind.com.cn/portal/zh/WDS/marketdata.html)公开说明API及Python支持；不能据此证明历史监管包。
需机构账号/授权的具体产品、费用、entitlement、历史深度、深圳主板/399107覆盖、CA参考价、每日状态/停复牌、公告原件与更正、历史版本、SLA、再分发条款全部 **UNKNOWN / 待书面答复**。
集成复杂度暂估高、锁定风险暂估高（评估判断，不是实测）；不能默认买终端就拥有WDS历史API权限。
优先索要字段字典+许可说明+边界样本，只有缺口无法由官方和较小结构化组合填补时再考虑采购。

## 6. Source candidate matrix

单元格是契约现状；文档存在/可候选不表示已经supported。完整覆盖未证实一律保留UNKNOWN。

| Source | Stock Daily | Official Benchmark | Corp Action | Security State | Suspension | Announcements | Account | Cost | Contract Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Longbridge当前能力 | realtime非本目标 | 历史UNKNOWN | UNKNOWN | 当前security signal非历史 | 不构成历史 | UNKNOWN | 是/行情权限 | 套餐UNKNOWN | UNSUITABLE |
| AKShare/Eastmoney wrapper | 现有raw/qfq | SDK候选、399107未验 | qfq不等于官方证据 | 完整历史UNKNOWN | 当前无契约 | 当前无契约 | 现有接口无需用户token | wrapper免费≠来源许可 | PARTIAL |
| BaoStock | 现有none fallback | 399107未验 | SDK候选、官方等价未验 | isST/tradestatus候选未接 | 完整历史UNKNOWN | 当前无契约 | 当前SDK非用户账号登录 | 现有SDK无收费认证、数据许可待验 | PARTIAL |
| SZSE公开文件/栏目 | 稳定日线导出UNKNOWN | authority、历史供应未验 | 正式规则/公告、参考日库未验 | 官方事件，完整ledger未验 | 官方公告目录 | 正式公开信息、reset需定位 | 样本无需 | 样本公开、批量授权UNKNOWN | PARTIAL |
| CNI官方指数源 | 非职责 | 399107标识VERIFIED、Daily未验 | 指数方法待验 | 非职责 | 非证券职责 | 指数公告非异常事件 | 样本无需，供应权限UNKNOWN | 历史授权UNKNOWN | PARTIAL |
| CNINFO法定披露 | 非本次行情源 | 非职责 | 实施公告样本VERIFIED | 公司披露、完整历史未验 | 公司公告需正式时间核对 | 披露原件非完整交易所事件库 | 样本无需/API未知 | 公开查阅、API/批量UNKNOWN | PARTIAL |
| Tushare Pro | 文档可候选、数据未验 | index_daily候选 | dividend/adj_factor不足以证明监管调整 | basic/limit不足以证明全历史 | suspend_d文档候选 | shock接口候选、ID/时间完整性未验 | 是/token+分dataset权限 | UNKNOWN，积分不等于价格 | PARTIAL |
| Wind机构产品 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | 待vendor确认具体授权 | UNKNOWN | UNKNOWN |

没有任何来源组合已满足整个监管contract；authority可追溯与机器历史完整性分别验收。

## 7. MINIMUM PRICE-RULE DATASET

| Field / dataset | Required semantics | Preferred source | Fallback source | Current availability / blocker |
| --- | --- | --- | --- | --- |
| 证券身份+completed Daily原始close | 精确正式价、前收/参考价区分、适用日期 | 经官方核对的授权日行情 | AKShare/BaoStock仅候选 | 普通OHLC存在；official reference/修订语义未验 |
| 399107 Daily close/base | 正式价格指数、不替代、同步完成日 | CNI/SZSE官方历史供给 | 授权index_daily并与官方核对 | 标识已验；历史样本、覆盖、版本/许可未验 |
| trading calendar/alignment | 交易所开闭市+同日join，完整有效窗口 | SZSE正式日历/通知 | 授权trade calendar核对 | 日历现存不证明证券有效日；不可用行号join |
| CA事件与监管调整 | 每次除权除息、送转/配股/特殊批准参考价与跨期复算 | 正式实施公告+官方参考价/说明 | 专业CA结构化数据并链原件 | 单现金公告样本存在；全事件覆盖及算法等价未验 |
| 当日可纳入状态 | IPO/重上市/no-limit、退市整理、ST等有效历史 | SZSE状态/上市/特别处理公告 | 授权历史状态+官方抽样核对 | 当前列表/名称/限价值不够，UNKNOWN |
| 停复牌及window/reset边界 | 全日/盘中区别、复牌实际时点；无缺bar推断 | SZSE正式公告 | suspend_d等经核验候选 | 历史完整性及临时停牌适用歧义未封闭 |
| rule/normalization/calculation version | 生效日期匹配，可重算，整数/Decimal精度及舍入规则有依据 | 正式条款+可核对案例 | 无规则authority替代 | 窗口枚举/跨事件调整等尚AMBIGUOUS |
| event boundary（若声称实际监管重算） | exchange publication的正式时点/有效起点 | SZSE正式公开记录 | 授权事件索引链接官方原件 | 完整事件/状态转移未验；缺失只可原始未reset研究 |

最少仍缺：399107完整日历史；官方价格参考及跨期CA语义；逐日可纳入/停复牌状态；窗口执行歧义封闭及许可。
把公告/count overlay暂缓不等于这些价格适用性输入可以省略。当前 **PRICE RULE NOT READY**。

## 8. Full Regulatory Dataset

除上述全部输入，还需要：正式异常/严重异常公告ID、exchange发布时间、证券与有效板块、方向/规则条款/期间、撤销更正、正式复牌与reset起点、同向重复触发历史及去重关联。
需验证实际公开记录覆盖、publication date与期间结束日差异、普通/严重同时触发及重算互相影响的状态机；不能靠计算命中生成正式事件。
还须持续维护特殊处理/上市/无价格限制/退市整理完整历史与规则版本；若称完整异常标准，则需另补换手率等分支的可靠quantity/流通股本契约。
发行人“异常波动公告”、龙虎榜交易披露、vendor原因摘要和交易所正式事件不同，不直接当等价reset记录。
当前 **FULL REGULATORY CONTEXT NOT READY**。

## 9. Candidate integration architecture（design only）

沿现有Provider → Service校验/标准化 → Repository的边界，保留普通Historical Provider与realtime消费者不变。
未来先做少量离线证据样本+字段映射验收，再决定是否需要regulatory-specific model；本轮不建抽象类/迁移/API。
价格和399107历史可共用同一授权行情connector，但各自dataset ID与字段映射隔离；不走enriched benchmark substitution。
CA/证券状态与正式公告确实可能来自独立发行者/来源，建议分别保留证据输入/有效期记录，由一个验证Service对齐，不创建一套平行行情缓存。
只有验证了独立供给需求才拆RegulatoryPrice/Benchmark/SecurityState/Announcement provider接口；不是四个名字各写一套框架。
Repository未来保存证据索引和版本化输入，计算可拒绝UNKNOWN；本轮不设计具体数据库表、不写Evidence DB。
禁止静默fallback：换来源须重新证明contract，原始/参考/调整价格混淆或缺状态应blocked。

Evidence contract：source issuer、transport vendor、dataset、symbol/date、raw URL/document ID+hash/定位、observed/fetched/available_at、effective_from/to、normalization_version、rule_version、calculation_version及依赖证据集合。
必须保留历史修订/vintage；仅trading_date截断不是完整PIT。Vibe-Research只启发provenance，不提供监管authority或正式状态推断。

## 10. License / entitlement concerns

官方公开文件可用于本次有限引用核验；持续自动化、长期归档和数据再分发授权均需单独确认。
AKShare/BaoStock/Tushare开源SDK不授予上游金融数据使用/分发许可；商业数据权限按具体dataset、频率、期限及使用主体确认。
生产前须记录内部研究用途、缓存/保留期限、原文与派生数据展示/导出限制、provider终止服务后的数据保留权；当前未获授权的项UNKNOWN。
不付费、不注册、不绕登录；本报告的API存在性不构成用户已有entitlement。

## 11. Price-rule readiness

**PRICE RULE NOT READY**。普通OHLC可取得与监管合同满足是不同事实；本轮没有完成结构化官方benchmark/CA/state的全覆盖验收。
可下一步做纯样本合同closure，不建议立即生产price rule/proximity。未reset研究输出必须明确非正式监管判定。

## 12. Full-context readiness

**FULL REGULATORY CONTEXT NOT READY**。即便价格数据未来齐全，公告/重复触发/reset、更正与特殊日历史仍是独立硬门槛。
不把Price Ready替代Full Ready，不以现有anomaly或Market Context的数据/阈值代替监管事件。

## 13. Recommended source strategy

按语义 → authority/provenance → 历史完整 → 稳定 → 自动化 → 许可 → 成本 → 复杂度排序。

1. 官方规则及399107身份固定；优先确认CNI/SZSE的实际历史导出/授权供应，禁止近似指数替代。
2. 以CNINFO实施公告+SZSE正式参考价/规则作为CA校对锚点；下一阶段需现金、送转、配股/混合、特殊调整样本，不仅验证qfq。
3. 以SZSE状态/停复牌/上市资料为authority；若公开记录难以完整机器读取，允许授权结构化数据帮助索引，但每类字段先做官方核对。
4. 首选评估Tushare按域组合（Daily/index/dividend/suspend/limit/basic/shock），不直接“选Tushare全覆盖”；缺配股、daily状态、参考价或正式发布时间时保留blocked。
5. 仍无法闭合关键历史/许可/SLA时，向Wind等机构供应商询问准确字段字典/样本/授权报价，不盲购通用终端。
推荐组合：授权stock Daily + CNI/官方核验的399107 + CNINFO/SZSE CA证据 + 官方状态/事件（可由授权vendor结构化索引）。one vendor != authoritative for all。

## 14. User decisions required / next gate

**USER DATA SOURCE ACTION REQUIRED**，不是现在要求提供凭证。

- Decision 1：是否允许下一阶段评估需账号/token的来源？建议允许先验证Tushare具体dataset权限/样本，不先购买；token只在本机安全配置。
- Decision 2：是否愿意在免费/公开来源无法闭合CA参考价和历史状态时付费？建议先要求供应商提交字段、覆盖、官方出处及内部研究许可，再定预算。
- Decision 3：是否接受第一版仅“深圳主板已完成日 Price Rule研究分支”？建议接受小范围合同closure；明确不宣称完整监管异常接近度，不省略价格窗口必要状态。

下一阶段建议：**SOURCE CONTRACT VALIDATION，NOT PRODUCTION IMPLEMENTATION**。
放行条件：获得授权的399107+stock日样本；CA跨事件调整可复算；有效日/停复牌有历史证据；窗口歧义解决；许可确认；源修订/PIT限制明确。
本轮无tests/build需求，无production code/SDK安装/用户凭证请求/账号创建/批量爬取；公开probe与引用已完成，候选未当成已接入。
