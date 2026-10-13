# Factor Snapshot Foundation v1

本层冻结既有FactorScoringEngine结果，不计算因子、不改变标准化/评分算法，不接入Anomaly Intelligence或任何生产消费者。
实现使用既有damon后端扩展注册只读路由；原实验/组合/事件数据库、Factor Engine与Registry不变。

## Model / builder

FactorSnapshot为frozen Pydantic模型；嵌套因子值、normalization使用frozen模型和tuple。
calculation metadata内部为规范JSON字符串，对外to_dict返回脱离内部状态的JSON对象；修改原result或返回对象不会改变快照。
字段包括snapshot/run/definition/证券/市场身份，as_of_date、generated_at、available_at、市场timezone，registry/engine/snapshot版本，universe ID/hash/size/members，逐因子normalization与值/分数、total_score、状态/blocker及source/input/adjustment/calculation证据。

Builder仅接收已有完整score结果、计算时registry metadata、universe metadata和provenance。

- run_id、definition_id、engine/registry/normalization版本必须显式提供；不推断当前版本即历史计算版本，unknown/unverified/latest不当已知。
- 每个output_column保留当时registry元数据与factor版本、period、mode/backend、price_basis、方向、等权complete-case、valid_count/min/max。
- universe提供完整members、universe_id、与score相同的as_of_date、aware available_at及evidence_reference；与score全部rows严格一致，不用portfolio selected_symbols替代评分股票池。
- universe_hash由排序后的完整members规范JSON计算；其余历史有效性/版本由证据提供，hash本身不证明无幸存者偏差。
- 保存整个score_cohort，使横截面可追溯；不重新评分或将缺失因子的权重重分配。
- provenance要求source、input_reference、adjustment_method、input_latest_date、aware input_available_at、availability_evidence、source_vintage及pit_status=verified；缺失返回BLOCKED，不生成假snapshot。

Builder记录真实当前generated_at/available_at，不接受回填历史生成时间。缺metadata的BLOCKED结果snapshot=null；不是空READY。
独立store可以保存符合模型的UNAVAILABLE/BLOCKED记录，但查询只选择READY。没有输入/计算来源证据时不能在生产调用中使用fixture标记。
本层验证调用方提供证据的一致性，**不独立认证供应商PIT/数据真实性**。pit_status声明需要真实input_reference/availability evidence；没有已验证producer的现有研究结果不会自动变READY。

## Time / no-lookahead

v1限定Daily证据：as_of_date必须早于generated_at的市场本地日期，不能盘中使用当日最终Daily。
input_latest_date不能晚于as_of_date；输入和universe available_at不能晚于生成时刻。
单日cutoff不证明source vintage/PIT，仍要求显式来源证据。
过去结果今天冻结只在今天及之后可见，不能成为过去事件证据。Store还保存stored_at，查询要求available_at、generated_at、stored_at都<=requested_time，避免延迟入库产生反向可见性。
Store拒绝生成/可得时间晚于实际当前时间的snapshot；不能通过写入未来记录提前暴露。
原研究结果的latest行情或latest run不会被本层自动读取、补造或用于历史证据。

## Store

独立本地data/user_data/factor_snapshots.sqlite3，runtime不入Git。
snapshot_id唯一，重复相同内容保存幂等；相同ID不同内容报immutable_snapshot_conflict。
只新增本库table/index，不对实验/组合/事件库迁移。查询mode=ro，不存在时返回UNAVAILABLE且不创建目录/库。
查询限定symbol + exact snapshot_date + definition_id + aware as_of_time，按该范围内最近available_at选择READY；不能省略definition跨研究挑latest。
没有update/delete入口；CRUD验收验证创建、读取、重复保存及拒绝覆盖。删除/保留策略不在v1范围内。

## API

GET /api/factor-snapshots/{symbol}

必需query：as_of_time（带时区）、snapshot_date（Daily日期）、definition_id。
READY返回snapshot/factors/scores/provenance。不存在/缺初始化/损坏或证据不合法返回UNAVAILABLE+安全blocker。
时间格式或缺必填参数由FastAPI返回422。查询不执行Factor Engine、访问provider、创建snapshot或更新数据库。
本阶段无写API、前端、LLM、新闻、交易或事件关联。

## Validation / limitations

测试使用临时目录和明确fixture证据，不读用户凭证或真实行情；覆盖serialization、深冻结、版本/来源缺失、universe隔离、as_of门控、未来输入/快照拒绝、延迟入库、幂等与拒绝覆盖、只读API。
现有评分/实验/组合/registry及扩展测试同时回归；新层未连接任何现有producer，因此线上缺快照时正常UNAVAILABLE。
本阶段不是解决第三方历史PIT、发布时刻或数据授权，也不宣称Anomaly Intelligence已完成。
后续producer接入必须另行明确计算时版本、universe历史证据、source vintage/可得时间；不得从缺元数据的旧portfolio结果补填当前registry标签。

2026-10-13验收：Backend targeted 120 passed；最终Backend full 3399 passed / 6 skipped / 0 failed（217既有warnings）；改动Python Ruff PASS，敏感扫描与git diff --check PASS。无前端改动，Frontend tests/build NOT RUN。
