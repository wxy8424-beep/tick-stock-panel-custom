import type { IndexPreviewProvenance } from '../index-preview/contract'
export type ReviewMarket = 'HK' | 'US'
export interface ReviewObservation extends IndexPreviewProvenance {
  symbol: string
  name: string
  market: ReviewMarket
  kind: 'INDEX' | 'STOCK'
  /** Fraction, formatted with the shared fmtPct helper. Not CN OverviewMarket percentage points. */
  change_pct: number | null
  turnover: number | null
  turnover_unit: string | null
  missing_reason: string | null
  evidence_reference: string
}
export interface PreviewReport extends IndexPreviewProvenance {
  id: string
  market: ReviewMarket
  trading_date: string
  title: string
  summary: string
  content: string
  generated_at: string
  available_at: null
  rows: readonly ReviewObservation[]
}
export interface ReviewPreviewData extends IndexPreviewProvenance {
  market: ReviewMarket
  reports: readonly PreviewReport[]
}
export type ReviewPreviewState = { kind: 'ready'; data: ReviewPreviewData } | { kind: 'loading' } | { kind: 'error' }
export function validateReviewPreview(data: ReviewPreviewData): ReviewPreviewData {
  const preview = (v: IndexPreviewProvenance) => v.status === 'PREVIEW' && v.source === 'synthetic-fixture'
    && v.data_mode === 'preview' && v.is_production === false && v.is_investment_signal === false && v.fixture_only === true && v.synthetic === true
  if (!preview(data) || !['HK', 'US'].includes(data.market)) throw new Error('review_fixture_required')
  if (new Set(data.reports.map(r => r.id)).size !== data.reports.length) throw new Error('duplicate_preview_report')
  for (const report of data.reports) {
    if (!preview(report) || report.market !== data.market || !/^\d{4}-\d{2}-\d{2}$/.test(report.trading_date)) throw new Error('preview_report_identity_conflict')
    if (new Set(report.rows.map(r => r.symbol)).size !== report.rows.length) throw new Error('duplicate_preview_observation')
    for (const row of report.rows) {
      if (!preview(row) || row.market !== data.market) throw new Error('mixed_review_market')
      if ([row.change_pct, row.turnover].some(v => v !== null && !Number.isFinite(v))) throw new Error('nonfinite_preview_value')
      if ((row.change_pct === null || row.turnover === null) && !row.missing_reason) throw new Error('missing_preview_reason')
      if (row.turnover !== null && !row.turnover_unit) throw new Error('preview_amount_unit_required')
    }
  }
  return data
}
