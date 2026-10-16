import type { IndexPreviewProvenance } from '../index-preview/contract'

export type EnvironmentMarket = 'HK' | 'US'
export interface EnvironmentValue { value: number | null; reason: string | null }
export interface EnvironmentIndex extends IndexPreviewProvenance {
  symbol: string
  name: string
  market: EnvironmentMarket
  trading_date: string
  latest_value: EnvironmentValue
  /** Fraction: .01 means 1%. Separate from CN RegimeRow semantics. */
  change_pct: EnvironmentValue
  trend: 'UP' | 'DOWN' | 'FLAT' | 'UNAVAILABLE'
  trend_reason: string | null
  evidence: string
}
export const environmentMetricLabels = {
  up: '上涨数量', down: '下跌数量', flat: '平盘数量', up_down_ratio: '上涨 / 下跌数量比',
  strong: '强势数量', weak: '弱势数量', strong_weak_ratio: '强势 / 弱势数量比',
  breakout: 'Breakout 数量', volume_spike: 'Volume Spike 数量',
} as const
export type EnvironmentMetric = keyof typeof environmentMetricLabels
export interface EnvironmentDay extends IndexPreviewProvenance {
  market: EnvironmentMarket
  trading_date: string
  generated_at: string
  available_at: null
  session: 'REGULAR' | 'EXTENDED' | 'NONE'
  market_state: 'OPEN' | 'CLOSED' | 'PRE_OPEN' | 'POST_CLOSE'
  indices: readonly EnvironmentIndex[]
  metrics: Record<EnvironmentMetric, EnvironmentValue>
  breadth_status: 'EXPANDING' | 'BALANCED' | 'CONTRACTING' | 'UNAVAILABLE'
  conclusion: 'BULLISH' | 'NEUTRAL' | 'WEAK' | 'UNAVAILABLE'
  conclusion_reason: string | null
  evidence: string
  missing_fields: readonly string[]
  blockers: readonly string[]
  warnings: readonly string[]
}
export interface EnvironmentPreviewData extends IndexPreviewProvenance {
  market: EnvironmentMarket
  days: readonly EnvironmentDay[]
}
export type EnvironmentPreviewState = { kind: 'ready'; data: EnvironmentPreviewData } | { kind: 'loading' } | { kind: 'error' }

export function validateEnvironmentPreview(data: EnvironmentPreviewData): EnvironmentPreviewData {
  const preview = (v: IndexPreviewProvenance) => v.status === 'PREVIEW' && v.source === 'synthetic-fixture'
    && v.data_mode === 'preview' && v.is_production === false && v.is_investment_signal === false && v.synthetic === true && v.fixture_only === true
  if (!preview(data) || !['HK', 'US'].includes(data.market)) throw new Error('environment_fixture_required')
  if (new Set(data.days.map(d => d.trading_date)).size !== data.days.length) throw new Error('duplicate_environment_date')
  for (const day of data.days) {
    if (!preview(day) || day.market !== data.market || !/^\d{4}-\d{2}-\d{2}$/.test(day.trading_date)
      || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(day.generated_at) || day.available_at !== null || !day.evidence) throw new Error('environment_identity_conflict')
    if (!['OPEN', 'CLOSED', 'PRE_OPEN', 'POST_CLOSE'].includes(day.market_state) || !['REGULAR', 'EXTENDED', 'NONE'].includes(day.session)) throw new Error('invalid_preview_session')
    const missing: string[] = []
    const quantity = (v: EnvironmentValue, path: string, count = false) => {
      if (v.value === null) {
        if (!v.reason?.trim()) throw new Error('environment_missing_reason_required')
        missing.push(path)
      } else if (!Number.isFinite(v.value) || (count && (v.value < 0 || !Number.isInteger(v.value)))) throw new Error('invalid_environment_value')
    }
    for (const key of Object.keys(environmentMetricLabels) as EnvironmentMetric[]) {
      quantity(day.metrics[key], `metrics.${key}`, !key.endsWith('_ratio'))
      if (key.endsWith('_ratio') && day.metrics[key].value !== null && day.metrics[key].value! < 0) throw new Error('invalid_environment_ratio')
    }
    if (new Set(day.indices.map(i => i.symbol)).size !== day.indices.length) throw new Error('duplicate_environment_index')
    for (const index of day.indices) {
      if (!preview(index) || index.market !== day.market || index.trading_date !== day.trading_date || !index.evidence) throw new Error('mixed_environment_index')
      quantity(index.latest_value, `indices.${index.symbol}.latest_value`)
      quantity(index.change_pct, `indices.${index.symbol}.change_pct`)
      if (!['UP', 'DOWN', 'FLAT', 'UNAVAILABLE'].includes(index.trend) || (index.trend === 'UNAVAILABLE' && !index.trend_reason)) throw new Error('missing_environment_trend_reason')
    }
    if (!['BULLISH', 'NEUTRAL', 'WEAK', 'UNAVAILABLE'].includes(day.conclusion) || (day.conclusion === 'UNAVAILABLE' && !day.conclusion_reason)) throw new Error('missing_environment_conclusion_reason')
    if (!['EXPANDING', 'BALANCED', 'CONTRACTING', 'UNAVAILABLE'].includes(day.breadth_status)) throw new Error('invalid_environment_breadth_status')
    if ([...missing].sort().join('|') !== [...day.missing_fields].sort().join('|')) throw new Error('environment_missing_fields_conflict')
  }
  return data
}
