# Tushare / Official Source Contract Validation v1

日期：2026-10-13；起点：main/c08f0aeb3f057e7eab824c724ed364747761a085。
结论：**CONTRACT DOCUMENTATION COMPLETE — REAL ENTITLEMENT VALIDATION BLOCKED**。
**PRICE RULE NOT READY**；**FULL REGULATORY CONTEXT NOT READY**。
本轮仅文档与项目外只读诊断，production code、Provider、API、DB、Dashboard、能力声明均未修改。

## 1. Scope / levels

沿用[五板块规则审计](cn-regulatory-anomaly-contract-audit-v1.md)和[来源评估](cn-regulatory-data-source-evaluation-v1.md)，仅深圳主板价格分支。
LEVEL 1 PRICE RULE BASIC：固定completed-day窗口的价格条件研究，仍必须证明调整、证券适用状态、日历及输入；不宣称正式异常事件。
LEVEL 2 PRICE RULE WITH REGULATORY RESET：另需真实正式公布/复牌和重算边界。
LEVEL 3 FULL REGULATORY CONTEXT：另需公告、重复触发、严重事件、完整状态及其他适用分支证据。
本轮最多验证LEVEL 1输入；公告overlay暂缓不允许省略价格适用性证据或宣称官方认定。

## 2. Token / authentication result

当前执行进程：**TUSHARE_TOKEN_PRESENT=false**。仅检查进程环境，不输出值/长度/hash/前后缀。
此前本地.env保存与当前进程环境继承是不同事实；本轮未加载、读取或改写.env，不写token或认证请求dump。
**USER ACTION REQUIRED: TUSHARE TOKEN NOT INHERITED**。
Tushare authentication **NOT RUN**；token accepted / API authenticated reachability / current entitlement均 **UNKNOWN**。
无真实权限拒绝、无积分拒绝、无付费拒绝证据；不能依据文档门槛将当前账号标POINTS_BLOCKED。
未注册、购买、升级或调用账号API；token缺失不判整个文档研究失败。

## 3. Dataset inventory（官方公开contract；非账号验收）

下表Required params列为候选最小请求限定；若文档参数全为可选也明确给symbol/date，禁止无界全市场拉取。
权限为公开文档要求，不是当前账号实际权限；历史起点未明确则UNKNOWN，不凭接口样例或单次行数宣称完整历史。

| Dataset / official docs | Minimal params | Relevant returned fields / semantics | Depth / permission | Regulatory contribution / blocker |
| --- | --- | --- | --- | --- |
| [daily](https://tushare.pro/document/2?doc_id=27) | ts_code + start_date/end_date，YYYYMMDD | trade_date、OHLC、pre_close、pct_chg；未复权行情，停牌期不提供bar；pre_close为除权昨收 | 文档基础积分、6000条/次；准确最早日/账号门槛待验证 | 日价PARTIAL；不能由缺bar推停牌，pre_close尚未交叉验官方参考 |
| [index_daily](https://tushare.pro/document/2?doc_id=95) | 必需ts_code，限定日期 | trade_date、close、pre_close=昨日收盘点；文档明确399107.SZ | 2000积分，5000更高频；399107起点UNKNOWN | identity mapping已文档证明；真实账号历史NOT RUN |
| [stock_basic](https://tushare.pro/document/2?doc_id=25) | ts_code + list_status，必要时L/D/P分开查 | market、exchange、list_date、delist_date、list_status；后两状态字段需fields显式取 | 2000积分；最早历史与状态变迁深度UNKNOWN | 不是逐日证券状态；当前L默认会漏退市等状态 |
| [adj_factor](https://tushare.pro/document/2?doc_id=28) | ts_code + start_date/end_date | trade_date、adj_factor；Tushare自行生产 | 2000积分，5000高频；声称单证券历史，覆盖需实测 | vendor因子不等于官方监管调整；BLOCKED |
| [dividend](https://tushare.pro/document/2?doc_id=103) | ts_code，随后ex_date/imp_ann_date限定 | div_proc、stk_div/stk_bo_rate/stk_co_rate、cash_div_tax税前/cash_div税后、record_date/ex_date/imp_ann_date | 2000积分；说明2000起但样例更早，覆盖需实测 | 可区分预案/实施与送转现金；未证明配股/特殊参考公式完整 |
| [stk_limit](https://tushare.pro/document/2?doc_id=183) | ts_code + start_date/end_date；fields取pre_close | trade_date、up_limit/down_limit、pre_close=昨日收盘价、exchange/asset_type | 2000积分；历史最早日UNKNOWN | 不提供明确no-limit原因；其pre_close定义不能自动与daily混同 |
| [suspend_d](https://tushare.pro/document/2?doc_id=214) | ts_code + start_date/end_date | suspend_type S/R、trade_date、suspend_timing日内时间 | 2000积分，5000高频；文档2000-01-03起 | 显式停复牌候选；空结果不证明期间全正常，需覆盖/官方事件核对 |
| [namechange](https://tushare.pro/document/2?doc_id=100) | ts_code + 公告日期范围 | name、start_date/end_date、ann_date、change_reason | 页面未明确门槛/最早日：UNKNOWN | 历史名称/原因PARTIAL，不能只看名称生成完整每日ST类别 |
| [stock_st](https://tushare.pro/document/2?doc_id=397) | ts_code + trade_date或有限范围 | 历史每日name/type/type_name | 3000积分；2000起，文档提示早期无法补齐 | 明确historical ST候选；缺记录原因/完整性、ST/*ST映射需正式证据 |
| [st](https://tushare.pro/document/2?doc_id=423) | ts_code，pub_date/imp_date | 发布/实施日、st_type/st_reason/st_explain | 6000积分；最早日UNKNOWN | 事件型风险警示候选，仍需有效期与撤销/叠加核对 |
| [stk_seasoned](https://tushare.pro/document/2?doc_id=494) | ts_code + 公告日期范围 | 增发进程、fo_type、发行价/量、right_reg_dt/ex_right_dt等 | 2000积分；最早日UNKNOWN | 明确是增发；**不能把增发等同配股**，未确认完整rights/allotment contract |
| rights/allotment完整数据集 | 未找到足够公开契约证据，不猜接口名 | 配股价、比例、实施/登记/除权日、特殊参考价/批准公式 | UNKNOWN | BLOCKED，先索要明确接口/字段及原件 |

所有Tushare条目current account结果均UNKNOWN、rows为NOT RUN，不将未调用解释为UNSUPPORTED。
各页字段语义已核验，字段名存在只证明vendor schema，不直接证明exchange semantics或真实coverage。

## 4. CNI 399107 endpoint contract

来源：[CNI官方399107详情页](https://www.cnindex.com.cn/module/index-detail.html?act_menu=1&indexCode=399107)。页面→entry module→index-detail→common配置为实际读取链路，非猜URL。

- [entry-index-detail.js](https://www.cnindex.com.cn/js/pages/entry-index-detail.js)引用../common与../app/index-detail。
- [common.js](https://www.cnindex.com.cn/js/common.js)定义window.hqUrl=https://hq.cnindex.com.cn。
- [index-detail.js](https://www.cnindex.com.cn/js/app/index-detail.js)历史chart函数queryIndexHistoryData选择Daily GET `/market/market/getIndexDailyData`。
- 历史表格函数queryIndexHistoryList使用GET `/market/market/getIndexDailyDataWithDataFormat`；本轮实际probe此格式化版本。
- 参数indexCode、startDate、endDate；表格另有frequency=day。实际YYYY-MM-DD小窗口成功。
- JSON：顶层code/message/data/total/sampleDate；rows=data.data，每行数组。
- 代码/响应相互核对：date=row[0]，open[3]、high[2]、low[4]、close[5]；不把current[1]当pre_close。
- 返回列标签timestamp/current/high/open/low/close/chg/percent/amount/volume/avg。timestamp列的真实值为明确YYYY-MM-DD日期标签，未从epoch猜交易日。
- 表格历史分页在客户端historyAllData内slice、每页20行；该请求不发page/pageSize，不能把其他sample/fund接口的分页参数套来。
- 下载路径POST `/market/market/downloadDailyMarketExcel`，indexCode/startDate/endDate/frequency；仅源码核验，未执行下载。

本轮只调用普通公开GET和必要Referer/Accept；未执行sdkSZSE/GFg2安全脚本、未解密、无登录/验证码绕过。
诊断首轮的UnicodeEncodeError是本地stdout编码问题，HTTP已成功；仅项目外脚本改ASCII JSON后恢复，不修改项目业务代码。

## 5. CNI real Daily result

**VERIFIED — FINITE PUBLIC SAMPLE**，不是多年连续历史/生产SLA或授权验收。
请求：[官方小窗口](https://hq.cnindex.com.cn/market/market/getIndexDailyDataWithDataFormat?indexCode=399107&startDate=2026-06-10&endDate=2026-06-17&frequency=day)。
HTTP200，business code200；响应indexCode=399107、indexName=深证Ａ指，indexSource=null。
来源归属依据官方host+页面依赖及响应身份；不编造不存在的indexSource字符串。
6行：2026-06-17、16、15、12、11、10。响应倒序，ascending=false、descending=true，重复日期0，close全部finite且>0，行宽11。
未填假日、未排序后冒充源本来升序；未来消费需显式按日期排序。同窗口股票未取得，strict same-date alignment **NOT VERIFIED**。
无明确pre_close列；不得将current或close-chg反推成来源正式前收。将来区间base应取官方上一完成日实际close，并核验边界覆盖。
本次6行不证明10/30日或多年深度、不证明交易日历所有开闭市、不证明修订/PIT vintage、价格精度/再分发权或稳定自动化许可。

## 6. Tushare 399107 result

官方index_daily文档明确identifier **399107.SZ**；与CNI实际响应399107/深证Ａ指及SZSE分类指数一致。
identifier mapping DOCUMENTATION VERIFIED；本轮Tushare真实Daily **NOT RUN — TOKEN NOT INHERITED**。
不能判ENTITLEMENT_BLOCKED、UNSUPPORTED、AUTH_INVALID；尚无账号或请求证据。
不使用399001、000001.SH或Market Context指数替代。官方公开CNI已提供有限真实历史候选，Tushare不是唯一获取途径。

## 7. Stock Daily / pre_close semantics

000001.SZ、000002.SZ authenticated Daily均NOT RUN，row count/date范围/OHLC/coverage/same-date join未知。
Tushare公开daily contract：未复权OHLC；pre_close明确为除权昨收，pct_chg基于该昨收计算；可作为vendor参考字段候选。
**REGULATORY ADJUSTMENT EQUIVALENCE = UNVERIFIED**。
daily与stk_limit的pre_close文案不同，不自动合并；必须核对同证券除息日及正常日的来源值、官方参考价精度/特殊公式和跨期调整。
即使单日参考一致，也不能直接将逐日收益连乘或adj_factor/qfq替换5.4.3区间公式。

## 8. Corporate Action P0 validation

官方事件样本来自实际[CNINFO平安银行2026-025实施公告](https://static.cninfo.com.cn/finalpage/2026-06-05/1225352449.PDF)：本次税前现金每10股3.60元，无送红股/转增，登记2026-06-11，除息2026-06-12。
这是官方文件证实的事件，不是凭记忆指定日期；仍没有vendor真实记录与Daily pre_close/adj_factor数值匹配，不声称本轮由Tushare发现事件。
本轮未计算监管价格、未生成qfq、未手工补字段。

| Regulatory requirement | Structured candidate | Official evidence | Conclusion |
| --- | --- | --- | --- |
| ex-date / implementation | dividend.ex_date/imp_ann_date/div_proc | 实施公告与4.4.1 | PARTIAL，真实账号行未取 |
| 税前现金、送股、转增 | cash_div_tax、stk_bo_rate、stk_co_rate | 本次实施金额/方案；禁止税后cash_div充当税前输入 | PARTIAL |
| 配股价/比例及其他股份变化 | 不能用stk_seasoned增发字段自动代替 | 4.4.2及具体配股实施/特殊公式公告 | BLOCKED，完整dataset未确认 |
| 官方ex-reference | daily.pre_close候选；stk_limit定义另核 | 4.4.2–3；单日实际官方参考及舍入证据待取 | PARTIAL |
| 多事件区间累计偏离调整 | adj_factor只有vendor定义 | 5.4.3要求相应调整；未提供完整等价算法证据 | BLOCKED |
| 时效/修订/PIT | vendor公告/实施日期候选 | 原公告、变更公告及当时可得版本 | PARTIAL |

**CORPORATE ACTION CONTRACT BLOCKED**。事件文件可读、qfq可算或字段名类似均不能解除。

## 9. Security State validation

suspend_d、namechange、stock_st、st、stock_basic均未调用。历史ST的公开候选较上轮更明确，但真实有效期/完整性仍UNKNOWN。
normal trading状态不能从daily存在直接扩展为完整法律适用状态；missing bar != suspension。
stock_basic.list_status不是逐日状态；list_date/delist_date不能自动证明IPO前5交易日、重新上市或退市整理起始。
ST与*ST、其他风险警示、撤销/叠加需以正式有效期/事件映射，不按当前简称猜历史。
停复牌需显式S/R和实际时间/官方公告核对，空结果不能作为全期间正常证明。

## 10. Price Limit / No-limit

stk_limit实际账号probe NOT RUN；up_limit/down_limit/pre_close精度、覆盖和无效值原因未验证。
**NO-LIMIT CONTRACT = PARTIAL（公开schema层）**；真实排除日适用性尚BLOCKED。
listing date != no-limit proof；missing/null limits != no-limit proof。
即使取到上下限价格，仍缺当日无价格限制的正式理由、重新上市/特殊批准状态及有效起止。

## 11. Official cross-check / license

[SZSE2026正式规则](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)：沿用2026-07-06生效版本；5.4.1指定分类指数、5.4.3区间偏离与CA调整、4.4参考价、3.3.15无价格限制、4.5.6退市整理排除。
5.4.5有实际公布/复牌重算规定。LEVEL 1固定窗口研究不能冒充按交易所实际reset运行的结果；LEVEL 2/3缺该证据仍不可实现。
官方benchmark身份与CNI真实响应已交叉核对；CA单现金事件已官方核验；结构化vendor字段未完成同事件数值cross-check。
Tushare只是transport/provider。官方规则、指数归属及披露原件继续为authority；任何缺字段fail closed。
5.1.3明确交易信息使用/传播需要许可；公开GET成功不授予生产使用或再分发权。CNI历史自动化/内部存储许可、修订与SLA待确认，不绕站点访问控制。

## 12. Entitlement matrix

| Dataset | Needed For | Account Result | Rows | Required Permission | Semantic Confidence |
| --- | --- | --- | --- | --- | --- |
| CNI formatted Daily | 399107 price/base | PUBLIC_NO_ACCOUNT | 6 | 本次公开GET无账号；生产许可待验 | 小窗口身份/date/close VERIFIED，前收/长期PARTIAL |
| SZSE规则 / CNINFO样本PDF | 规则/CA authority | PUBLIC_NO_ACCOUNT | 非表格行 | 本次公开有限引用核验 | 条款/单事件VERIFIED，结构化映射PARTIAL |
| Tushare index_daily | 399107 | UNKNOWN | NOT RUN | 2000积分 | 文档映射VERIFIED，真实历史未知 |
| daily | stock price/reference | UNKNOWN | NOT RUN | 文档基础积分；账号实测待做 | PARTIAL |
| adj_factor / dividend | CA输入/诊断 | UNKNOWN | NOT RUN | 各2000积分 | PARTIAL / 监管等价BLOCKED |
| stk_limit / suspend_d | limits / halt-resume | UNKNOWN | NOT RUN | 各2000积分 | PARTIAL |
| stock_basic | listing/delisting | UNKNOWN | NOT RUN | 2000积分 | 静态PARTIAL，不是daily state |
| namechange | 名称及状态原因 | UNKNOWN | NOT RUN | 该页未明确，UNKNOWN | PARTIAL |
| stock_st / st | daily ST / 状态事件 | UNKNOWN | NOT RUN | 3000 / 6000积分 | PARTIAL |
| rights/allotment完整契约 | 配股/官方参考 | UNKNOWN | NOT RUN | 未确认接口，UNKNOWN | BLOCKED |

无真实拒绝，因此本轮blocked的是运行环境继承与未证明的语义，不能标POINTS_BLOCKED/PAID_PLAN_REQUIRED。

## 13. PRICE RULE readiness checklist

- [ ] 399107 official Daily完整目标窗口：本次6行VERIFIED，但目标窗口/base、深度/许可未封闭。
- [ ] completed-day stock Daily VERIFIED：两只股票NOT RUN。
- [ ] strict same-date alignment：未取得vendor stock进行join。
- [ ] correct interval-return inputs：官方区间公式已知，跨CA/起始base未证。
- [ ] corporate-action regulatory adjustment VERIFIED：BLOCKED。
- [ ] adequate daily exclusion evidence：PARTIAL / 实测未完成。
- [ ] no-future-data：completed日/date gate规格明确，vintage/修订/PIT仍未验。
- [ ] source provenance：CNI请求/响应来源已确认，其余结构化输入缺真实证据。
- [x] rule-version provenance：沿用已核验2026-07-06版本；不覆盖其前历史规则。

**PRICE RULE NOT READY**；没有为了收口降低P0条件。

## 14. FULL CONTEXT readiness

正式异常公告历史、trigger日期、reset/restart、同向重复触发、严重异常计数及更正关联均未验证。
**FULL REGULATORY CONTEXT NOT READY**。本轮不调用这些接口，不把价格条件研究当正式异常认定。

## 15. Exact minimal probes waiting to run（不是已执行）

先让Python进程从环境读取TUSHARE_TOKEN，不放CLI、不写文件；认证无效停止，权限拒绝只分类，不循环换接口/购买。

1. 最小可用性：daily(ts_code=000001.SZ,start_date=20260610,end_date=20260617,fields=ts_code,trade_date,open,high,low,close,pre_close,pct_chg)。成功只证明该接口接受token，不代表全部权限。
2. P0 benchmark：index_daily(ts_code=399107.SZ,start_date=20260610,end_date=20260617,fields=ts_code,trade_date,close,pre_close)，与CNI身份核对，检unique/date/finite。
3. 同窗000002.SZ Daily；按明确trade_date排序、与指数same-date join，报告缺失，不填补。
4. dividend(ts_code=000001.SZ,ex_date=20260612)，真实记录确认实施后，才对同窗adj_factor/Daily/reference核对上述官方公告；空结果EMPTY不伪造。
5. stk_limit、suspend_d、stock_st同证券同有限日期窗；namechange按明确公告日期窗，stock_basic指定fields/list_status核对；st事件仅必要小样本。无行只报告EMPTY，不能反推正常。
6. 配股先确认真实公开dataset contract和官方实施样本，不能猜不存在接口或将增发当配股。
输出仅dataset/symbol/行数/日期/字段名/语义与脱敏错误类别；权限探测不输出auth request、token或账号对象。

## 16. Remaining blockers / paid decision

| Dataset / gap | Required for | Current access | Required entitlement | Official alternative | Priority |
| --- | --- | --- | --- | --- | --- |
| token环境继承 | 所有Tushare实测 | NOT INHERITED | 不涉及购买 | 公共CNI只解决部分指数输入 | P0 |
| index_daily | benchmark历史 | UNKNOWN | 文档2000积分 | CNI有限真实样本已证，长窗口/许可待验 | P0，勿为重复已有样本盲购 |
| daily / dividend / adj_factor | 股票/CA校验 | UNKNOWN | 基础 / 2000 / 2000 | 官方实施公告+正式参考证据，不能以qfq替代 | P0，先实测再决定 |
| suspend/limits/ST | 排除日 | UNKNOWN | 2000 / 2000 / 3000；事件st6000 | SZSE正式状态/事件需完整历史 | P0，积分不能单独证明状态完备 |
| 配股/特殊参考+跨期监管调整 | CA等价性 | UNKNOWN/BLOCKED | UNKNOWN | SZSE/CNINFO原件和正式解释/案例 | P0，付款不保证解除语义blocker |

本轮**不建议购买/升级**：没有账号拒绝证据，也未证明付费dataset能闭合调整和状态契约。
先完成环境继承与现有权限小样本；真实权限阻塞后，才让用户按能解除的具体P0缺口决定，不注册新账号、不接Wind/新package。

## 17. Recommended architecture / user action

保持既有Provider→Service→Repository，本轮不创建Tushare Provider、抽象类或数据库。
下一阶段只做证据合同closure：可优先CNI官方指数+Tushare经验证的stock/状态结构化数据+官方CA/规则原件；每域单独provenance，不强求一家vendor包全部。
**USER ACTION REQUIRED: TUSHARE TOKEN NOT INHERITED**。使新Codex/Python进程安全继承环境变量，或明确另行授权仅从既有本地.env内存加载；本轮不自行加载/改写。
不要再次发送token明文，不购买；环境具备后按第15节续做真实entitlement。公开契约记录完成，账号实测阻塞如实保留。
本轮tests/build **NOT RUN（纯文档/项目外diagnostic）**；未改变生产contract、监管计算、数据源或策略。
