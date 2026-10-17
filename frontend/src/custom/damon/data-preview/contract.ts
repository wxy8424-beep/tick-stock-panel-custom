import type { IndexPreviewProvenance } from '../index-preview/contract'

export type DataPreviewMarket = 'HK' | 'US'
export type QualityStatus = 'READY' | 'PARTIAL' | 'UNAVAILABLE' | 'BLOCKED'
export interface DataSourceEvidence {
  id: string; name: string; data_type: string; access: string; sdk_capability: string
  readonly_validation: string; integration: string; production_observation: null; health: null
  reason: string; evidence: string
}
export interface DataCoverageSample {
  symbol_count: number | null; date_from: string | null; date_to: string | null
  covered_sessions: number | null; missing_sessions: number | null
  ohlc_ratio: number | null; volume_ratio: number | null; turnover_ratio: number | null
}
export interface DataSetPreviewRow {
  id: string; name: string; market: DataPreviewMarket; data_type: 'DAILY' | 'UNIVERSE'
  source_id: string; evidence_kind: 'STATIC_AUDIT' | 'SYNTHETIC_SAMPLE'; quality_status: QualityStatus
  symbols: readonly string[]; fields: readonly string[]; coverage: DataCoverageSample
  adjustment: string | null; updated_at: string | null; available_at: null
  missing_fields: readonly string[]; reasons: readonly string[]; evidence: string
}
export interface DataQualityEvidence {
  key: string; label: string; status: QualityStatus; value: string | null; reason: string; evidence: string
}
export interface DataPreviewData extends IndexPreviewProvenance {
  market: DataPreviewMarket; trading_date: string; generated_at: string; audit_date: string
  sources: readonly DataSourceEvidence[]; rows: readonly DataSetPreviewRow[]; checks: readonly DataQualityEvidence[]
  blockers: readonly string[]; warnings: readonly string[]
}
export type DataPreviewState = { kind: 'ready'; data: DataPreviewData } | { kind: 'loading' } | { kind: 'error' }
export function validateDataPreview(d: DataPreviewData): DataPreviewData {
  const date = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s) && Number.isFinite(Date.parse(s))
  const time = (s: string) => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(s) && Number.isFinite(Date.parse(s))
  const quality = (s: string) => ['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED'].includes(s)
  if (d.status !== 'PREVIEW' || d.source !== 'synthetic-fixture' || d.data_mode !== 'preview' || d.is_production !== false || d.is_investment_signal !== false || d.fixture_only !== true || d.synthetic !== true || !['HK', 'US'].includes(d.market) || !date(d.trading_date) || !date(d.audit_date) || !time(d.generated_at)) throw new Error('data_preview_identity_required')
  for (const rows of [d.sources, d.rows]) if (new Set(rows.map(r => r.id)).size !== rows.length) throw new Error('duplicate_data_preview_identity')
  for (const s of d.sources) if (s.health !== null || s.production_observation !== null || !s.reason.trim() || !s.evidence.trim()) throw new Error('static_evidence_is_not_provider_health')
  for (const r of d.rows) {
    if (r.market !== d.market || !d.sources.some(s => s.id === r.source_id) || !quality(r.quality_status) || !['STATIC_AUDIT', 'SYNTHETIC_SAMPLE'].includes(r.evidence_kind) || !r.reasons.length || !r.evidence.trim() || r.available_at !== null || r.updated_at !== null && !time(r.updated_at)) throw new Error('invalid_data_preview_row')
    const c = r.coverage
    for (const k of ['symbol_count', 'covered_sessions', 'missing_sessions'] as const) if (c[k] !== null && (!Number.isSafeInteger(c[k]) || c[k] < 0)) throw new Error('invalid_data_preview_count')
    for (const k of ['ohlc_ratio', 'volume_ratio', 'turnover_ratio'] as const) if (c[k] !== null && (!Number.isFinite(c[k]) || c[k] < 0 || c[k] > 1)) throw new Error('invalid_data_preview_ratio')
    if ((c.date_from === null) !== (c.date_to === null) || c.date_from !== null && (!date(c.date_from) || !date(c.date_to!) || c.date_from > c.date_to!)) throw new Error('invalid_data_preview_range')
    // This page has no current production coverage measurement. Historical probes stay in text evidence.
    if (r.evidence_kind === 'STATIC_AUDIT' && (Object.values(c).some(v => v !== null) || r.updated_at !== null)) throw new Error('static_audit_cannot_claim_current_coverage')
    if (r.symbols.some(s => !s.endsWith(d.market === 'HK' ? '.HK' : '.US'))) throw new Error('mixed_data_preview_symbols')
    if (r.evidence_kind === 'SYNTHETIC_SAMPLE' && (!r.evidence.startsWith('fixture:') || c.symbol_count !== r.symbols.length || r.source_id !== 'synthetic-fixture')) throw new Error('synthetic_coverage_identity_required')
  }
  if (new Set(d.checks.map(c => c.key)).size !== d.checks.length || d.checks.some(c => !quality(c.status) || !c.reason.trim() || !c.evidence.trim())) throw new Error('invalid_data_quality_evidence')
  return d
}
