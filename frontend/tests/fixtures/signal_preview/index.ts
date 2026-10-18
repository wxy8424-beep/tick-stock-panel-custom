import { validateSignalPreview, type SignalPreviewData, type SignalMarket, type SignalSample } from '../../../src/custom/damon/signal-preview/contract'

const flags = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false, is_investment_signal: false, fixture_only: true, synthetic: true } as const
export function loadSignalPreview(market: SignalMarket): SignalPreviewData {
  const rows: SignalSample[] = [0, 1, 2, 3].map(i => ({
    ...flags, id: `fixture-signal-${market}-${i}`, name: `${market} ${['价格条件样稿', '字段缺失样稿', '规则待定义样稿', '量能阻塞样稿'][i]}`,
    market, fixture_version: 'preview-v1', direction: (['entry', 'exit', 'both', 'entry'] as const)[i],
    timeframe: i === 1 ? 'intraday' : 'daily', logic: 'AND',
    conditions: i === 2 ? null : [{ left: i === 1 ? null : i === 3 ? 'volume_ratio_20' : 'close', op: market === 'HK' ? '>' : '>=',
      right: market === 'HK' && i === 0 ? { kind: 'field', value: 'ma20' } : { kind: 'number', value: i === 3 ? 1.8 : 120 },
      left_sessions: 0, right_sessions: market === 'HK' && i === 0 ? 0 : null,
      missing_reasons: { left: '没有已确认的演示左字段，不代选生产字段', right_sessions: '数值右值没有交易日偏移，不填0冒充字段偏移' } }],
    definition_status: (['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED'] as const)[i], execution_status: 'BLOCKED',
    production_version: null, last_trigger_at: null, trigger_count: null, production_binding: null,
    missing_reasons: { production_version: '未创建或加载任何生产定义版本', last_trigger_at: '未运行条件评估，无真实触发时间',
      trigger_count: '没有触发记录，未知不是0', production_binding: '没有正式 Universe / 输入契约 / 生产绑定', conditions: '未定义此样稿的条件，不生成默认规则' },
    evidence: `fixture:signal:${market}:${i}:v1`,
    blockers: ['生产信号执行 BLOCKED；不编译、不评估、不注册定义', 'Volume/VR20、split-only、PIT/vintage、正式 Universe BLOCKED；Daily finality PARTIAL；corporate actions UNKNOWN'],
    warnings: ['所有条件是合成元数据，不是投资信号；READY 仅描述样稿结构完整', '没有实时触发、命中率或生产效果证据'],
  }))
  return validateSignalPreview({ ...flags, market, trading_date: '2026-09-16', generated_at: '2026-09-17T09:00:00Z', rows })
}
