import type { Lot } from '@/lib/api'
import type { IndexPreviewProvenance } from '../index-preview/contract'
export type LotsPreviewMarket = 'HK' | 'US'
/** Existing Lot field names/units; optionality is explicit for incomplete synthetic evidence. */
export type ReminderRuleSample = { [K in 'target_pct' | 'stop_pct' | 'remind_date' | 'lead_days']-?: Exclude<Lot[K], undefined> | null }
export interface ReminderSample extends IndexPreviewProvenance {
  name: string
  condition_description: string
  sample_state: 'PENDING_SAMPLE' | 'BLOCKED_SAMPLE' | null
  checked_at: string | null
  evidence: string
}
export const lotValueLabels = { qty: '数量', cost_price: '成本价', reference_price: '参考价格', pnl_amount: '演示盈亏金额', pnl_pct: '演示盈亏比例', stop_price: '演示止损线', target_price: '演示目标价', drawdown_pct: '演示回撤', concentration_pct: '集中度' } as const
export type LotSampleValue = keyof typeof lotValueLabels
export interface LotPreviewRow extends IndexPreviewProvenance {
  sample_id: string
  symbol: string
  name: string
  market: LotsPreviewMarket
  currency: 'HKD' | 'USD'
  qty_unit: 'synthetic-shares'
  values: Record<LotSampleValue, number | null>
  rule_sample: ReminderRuleSample
  reminder: ReminderSample
  evidence: string
  missing_fields: readonly string[]
  reasons: readonly string[]
  blockers: readonly string[]
  warnings: readonly string[]
}
export interface LotsPreviewData extends IndexPreviewProvenance {
  market: LotsPreviewMarket
  currency: 'HKD' | 'USD'
  trading_date: string
  generated_at: string
  overview: {
    position_count: number
    valued_count: number
    known_cost_amount: number | null
    known_reference_amount: number | null
    known_pnl_amount: number | null
    total_pnl_amount: number | null
    missing_reason: string
  }
  rows: readonly LotPreviewRow[]
}
export type LotsPreviewState = { kind: 'ready'; data: LotsPreviewData } | { kind: 'loading' } | { kind: 'error' }
export function validateLotsPreview(data: LotsPreviewData): LotsPreviewData {
  const preview = (v: IndexPreviewProvenance) => v.status === 'PREVIEW' && v.source === 'synthetic-fixture' && v.data_mode === 'preview'
    && v.is_production === false && v.is_investment_signal === false && v.fixture_only === true && v.synthetic === true
  const time = (s: string) => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(s) && Number.isFinite(Date.parse(s))
  if (!preview(data) || !['HK', 'US'].includes(data.market) || data.currency !== (data.market === 'HK' ? 'HKD' : 'USD') || !/^\d{4}-\d{2}-\d{2}$/.test(data.trading_date) || !time(data.generated_at)) throw new Error('lots_fixture_required')
  if (new Set(data.rows.map(r => r.sample_id)).size !== data.rows.length) throw new Error('duplicate_lot_sample')
  for (const row of data.rows) {
    if (!preview(row) || !preview(row.reminder) || row.market !== data.market || row.currency !== data.currency || row.qty_unit !== 'synthetic-shares' || !row.sample_id.startsWith('fixture-') || !row.evidence.startsWith('fixture:') || !row.reminder.evidence.startsWith('fixture:')) throw new Error('mixed_lot_sample')
    const missing: string[] = []
    for (const key of Object.keys(lotValueLabels) as LotSampleValue[]) {
      const n = row.values[key]
      if (n === null) missing.push(`values.${key}`)
      else if (!Number.isFinite(n) || (!['pnl_amount', 'pnl_pct'].includes(key) && n < 0)) throw new Error('invalid_lot_sample_value')
    }
    for (const key of ['target_pct', 'stop_pct', 'lead_days', 'remind_date'] as const) {
      const n = row.rule_sample[key]
      if (n === null) missing.push(`rule_sample.${key}`)
      else if (key === 'remind_date' ? typeof n !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(n) : typeof n !== 'number' || !Number.isFinite(n) || n < 0 || (key === 'lead_days' && !Number.isInteger(n))) throw new Error('invalid_reminder_rule_sample')
    }
    if (![null, 'PENDING_SAMPLE', 'BLOCKED_SAMPLE'].includes(row.reminder.sample_state)) throw new Error('invalid_reminder_sample_state')
    for (const key of ['sample_state', 'checked_at'] as const) if (row.reminder[key] === null) missing.push(`reminder.${key}`)
    if (row.reminder.checked_at !== null && !time(row.reminder.checked_at)) throw new Error('invalid_reminder_sample_time')
    if (missing.sort().join() !== [...row.missing_fields].sort().join() || (missing.length && !row.reasons.length) || !row.blockers.length || !row.warnings.length) throw new Error('lot_sample_missing_evidence')
  }
  const o = data.overview
  if (o.position_count !== data.rows.length || !Number.isInteger(o.valued_count) || o.valued_count < 0 || o.valued_count !== data.rows.filter(r => r.values.pnl_amount !== null).length) throw new Error('lot_overview_coverage_conflict')
  if ([o.known_cost_amount, o.known_reference_amount, o.known_pnl_amount, o.total_pnl_amount].some(v => v !== null && !Number.isFinite(v))) throw new Error('nonfinite_lot_overview')
  if ([o.known_cost_amount, o.known_reference_amount, o.known_pnl_amount, o.total_pnl_amount].some(v => v === null) && !o.missing_reason.trim()) throw new Error('lot_overview_missing_reason_required')
  if (o.valued_count !== o.position_count && (o.total_pnl_amount !== null || !o.missing_reason.trim())) throw new Error('incomplete_lot_total')
  return data
}
