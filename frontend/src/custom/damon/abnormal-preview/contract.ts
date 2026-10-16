import type { IndexPreviewProvenance } from '../index-preview/contract'
import { ANOMALY_TYPES, SEVERITY_LABELS } from '@/lib/anomalyPresentation'
export type AbnormalPreviewMarket = 'HK' | 'US'
export interface AbnormalPreviewRow extends IndexPreviewProvenance {
  sample_id: string
  symbol: string
  name: string
  market: AbnormalPreviewMarket
  trading_date: string
  event_type: keyof typeof ANOMALY_TYPES
  severity: keyof typeof SEVERITY_LABELS | null
  event_time: string | null
  /** Fraction, not percentage points. Fixed sample only. */
  change_pct: number | null
  sample_state: 'OBSERVATION_SAMPLE' | 'BLOCKED_SAMPLE' | null
  condition_description: string
  evidence: string
  missing_fields: readonly string[]
  reasons: readonly string[]
  blockers: readonly string[]
  warnings: readonly string[]
}
export interface AbnormalPreviewData extends IndexPreviewProvenance {
  market: AbnormalPreviewMarket
  trading_date: string
  generated_at: string
  rows: readonly AbnormalPreviewRow[]
}
export type AbnormalPreviewState = { kind: 'ready'; data: AbnormalPreviewData } | { kind: 'loading' } | { kind: 'error' }
export function validateAbnormalPreview(data: AbnormalPreviewData): AbnormalPreviewData {
  const preview = (v: IndexPreviewProvenance) => v.status === 'PREVIEW' && v.source === 'synthetic-fixture' && v.data_mode === 'preview'
    && v.is_production === false && v.is_investment_signal === false && v.fixture_only === true && v.synthetic === true
  const timestamp = (s: string) => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(s) && Number.isFinite(Date.parse(s))
  if (!preview(data) || !['HK', 'US'].includes(data.market) || !/^\d{4}-\d{2}-\d{2}$/.test(data.trading_date) || !timestamp(data.generated_at)) throw new Error('abnormal_fixture_required')
  if (new Set(data.rows.map(row => row.sample_id)).size !== data.rows.length) throw new Error('duplicate_abnormal_sample')
  for (const row of data.rows) {
    if (!preview(row) || row.market !== data.market || row.trading_date !== data.trading_date || !row.sample_id.startsWith('fixture-') || !row.evidence.startsWith('fixture:')) throw new Error('mixed_abnormal_sample')
    if (!Object.hasOwn(ANOMALY_TYPES, row.event_type) || (row.severity !== null && !Object.hasOwn(SEVERITY_LABELS, row.severity)) || ![null, 'OBSERVATION_SAMPLE', 'BLOCKED_SAMPLE'].includes(row.sample_state)) throw new Error('invalid_abnormal_sample_state')
    if (row.change_pct !== null && !Number.isFinite(row.change_pct)) throw new Error('nonfinite_abnormal_sample')
    if (row.event_time !== null && (!timestamp(row.event_time) || !row.event_time.startsWith(row.trading_date))) throw new Error('invalid_abnormal_sample_time')
    const missing = (['change_pct', 'severity', 'event_time', 'sample_state'] as const).filter(key => row[key] === null)
    if ([...missing].sort().join() !== [...row.missing_fields].sort().join() || (missing.length && !row.reasons.length)) throw new Error('abnormal_missing_reason_required')
    if (!row.condition_description.trim() || !row.blockers.length || !row.warnings.length) throw new Error('abnormal_sample_evidence_required')
  }
  return data
}
