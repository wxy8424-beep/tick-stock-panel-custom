/** Authored inert metadata. Never register these IDs in the strategy engine. */
import { validateStrategyPreview, type StrategyPreviewData, type StrategyPreviewMarket, type StrategyPreviewRow, type StrategyParameterSample } from '../../../src/custom/damon/strategy-preview/contract'
const flags = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false, is_investment_signal: false, fixture_only: true, synthetic: true } as const
export function loadStrategyPreview(market: StrategyPreviewMarket): StrategyPreviewData {
  const rows: StrategyPreviewRow[] = [0, 1, 2, 3].map(i => {
    const prefix = `fixture:strategy:${market}:${i}`, parameter_version = 'preview-params-v1'
    const symbol = market === 'HK' ? i % 2 ? '9988.HK' : '0700.HK' : i % 2 ? 'MSFT.US' : 'AAPL.US'
    const parameters: StrategyParameterSample[] = [
      { id: 'window', label: '观察窗口（合成参数）', type: 'int', value: i < 2 ? 20 : null, unit: 'completed sessions（仅样稿）', default_value: null, min: null, max: null, version: parameter_version, contract_reference: 'StrategyParamDef / StrategyDetail.params_defaults', status: i < 2 ? 'READY' : 'UNAVAILABLE', reason: '数值只属于独立样稿；未提供正式默认值或允许范围，不继承 CN 策略参数', evidence: `${prefix}:params:window` },
      { id: 'max_hold_days', label: '最长持仓天数（演示）', type: 'int', value: i < 2 ? 10 : null, unit: '天；HK/US session 执行映射未证明', default_value: null, min: null, max: null, version: parameter_version, contract_reference: 'StrategyDetail.max_hold_days', status: i < 2 ? 'READY' : 'UNAVAILABLE', reason: '仅复用字段形状；不宣称生产持仓退出或日历规则已生效', evidence: `${prefix}:params:max_hold_days` },
    ]
    return { ...flags, id: `fixture-strategy-${market}-${i}`, version: i === 3 ? 'preview-v2' : 'preview-v1', market, name: `${market} ${['趋势观察样稿', '过滤规则样稿', '待定义样稿', '量能规则阻塞样稿'][i]}`, description: '独立手写演示元数据，不是 CN 策略复制或可执行 HK/US 生产策略', strategy_type: i === 3 ? 'VOLUME_SAMPLE' : i === 1 ? 'FILTER_SAMPLE' : 'TREND_SAMPLE', configuration_id: `${prefix}:config:v1`, parameter_version,
      display_state: (['DEFINED_SAMPLE', 'INCOMPLETE_SAMPLE', 'NO_RULE_SAMPLE', 'BLOCKED_SAMPLE'] as const)[i], definition_status: (['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED'] as const)[i], validation_status: 'BLOCKED', runtime_status: null, last_run_at: null, signal_count: null,
      symbols: [symbol], instrument_type: null, universe_identity: null, input_contract_identity: null,
      entry: i < 2 ? { logic: 'AND', conditions: [{ left: 'close', op: '>', right: 'field:ma20', leftDays: 0, rightDays: 0 }, { left: 'change_pct', op: '>', right: '0', leftDays: 0 }], evidence: `${prefix}:entry` } : null,
      exit: i === 0 ? { logic: 'OR', conditions: [{ left: 'close', op: '<', right: 'field:ma20', leftDays: 0, rightDays: 0 }], evidence: `${prefix}:exit` } : null,
      rule_reason: i === 0 ? '仅声明同一完成交易日字段比较的合成 AND/OR 规则，不执行；change_pct 小数制，0为演示阈值' : i === 1 ? '退出规则未定义，保留 null，不拼接 CN 信号' : i === 2 ? '入场与退出规则均未定义，保留 null' : '量能规则的数量语义未闭合，条件保留 null，不发明生产触发公式', parameters,
      risks: [
        { key: 'stop_loss', label: '止损比例', value: i < 2 ? .08 : null, unit: 'fraction（0.08 = 8%）', status: i < 2 ? 'READY' : 'UNAVAILABLE', enforced: false, reason: '仅 StrategyDetail.stop_loss 的合成样例，不证明执行引擎强制实施', contract_reference: 'StrategyDetail.stop_loss' },
        { key: 'take_profit', label: '止盈比例', value: i === 0 ? .15 : null, unit: 'fraction（0.15 = 15%）', status: i === 0 ? 'READY' : 'UNAVAILABLE', enforced: false, reason: '仅 StrategyDetail.take_profit 字段展示；缺失不补默认值', contract_reference: 'StrategyDetail.take_profit' },
        ...[['symbol_position_cap', '单标的仓位上限'], ['total_position_cap', '总仓位上限'], ['max_drawdown', '最大回撤约束'], ['daily_risk_budget', '单日风险预算'], ['trade_frequency', '交易频率限制'], ['trading_cost', '交易成本配置']].map(([key, label]) => ({ key, label, value: null, unit: '—（未定义）', status: 'UNAVAILABLE' as const, enforced: false as const, reason: '当前策略详情没有本项 HK/US 已冻结执行契约；不能借用回测/模拟盘配置作为策略已生效风控', contract_reference: null })),
      ],
      dependencies: [
        { key: '历史行情 / 价格基准', status: 'BLOCKED', reason: '有限 Daily 读取不等于生产输入；split-only 未闭合', evidence: 'docs/custom/longbridge-historical-vendor-evidence-closure-v1.md' },
        { key: '数据质量 / 时间边界', status: 'BLOCKED', reason: 'Volume/VR20、PIT/vintage BLOCKED；finality PARTIAL；公司行动 UNKNOWN', evidence: 'docs/custom/longbridge-historical-vendor-evidence-closure-v1.md' },
        { key: '正式 Universe', status: 'BLOCKED', reason: '真实 membership 与历史可得性未闭合；页面展示证券范围不是正式 Universe', evidence: 'docs/custom/momentum-universe-foundation-v1.md' },
        { key: '因子', status: 'UNAVAILABLE', reason: '本样稿未选择 Factor definition 或 snapshot，不查询 Factor Store', evidence: `${prefix}:factor:not-selected` },
        { key: '回测', status: 'UNAVAILABLE', reason: '无实际回测结果；不生成收益、胜率或历史验证结论', evidence: `${prefix}:backtest:absent` },
        { key: '模拟盘 / 交易执行', status: 'BLOCKED', reason: '未绑定真实账户、Worker 或订单执行器；不触发通知或交易', evidence: `${prefix}:execution:absent` },
      ], evidence: `${prefix}:definition:v1`, missing_fields: ['runtime_status', 'last_run_at', 'signal_count', 'instrument_type', 'universe_identity', 'input_contract_identity', 'formal_parameter_bounds', ...(i > 0 ? ['exit'] : []), ...(i > 1 ? ['entry'] : [])],
      blockers: ['HK/US 输入和执行契约未闭合，production execution BLOCKED'], warnings: ['所有规则、状态、参数和配置身份均为固定合成样稿，不注册、不保存、不执行', '定义状态 READY 仅代表样稿结构完整，不等于历史验证或生产运行 READY'],
    }
  })
  return validateStrategyPreview({ ...flags, market, trading_date: '2026-09-16', generated_at: '2026-09-17T08:00:00Z', rows })
}
