import type { IndexPreviewProvenance } from '../index-preview/contract'

export type WatchlistPreviewMarket = 'HK' | 'US'
export interface PreviewQuantity {
  value: number | null
  unit: string | null
  reason: string | null
}
export interface WatchlistPreviewRow extends IndexPreviewProvenance {
  symbol: string
  name: string
  market: WatchlistPreviewMarket
  price: number | null
  /** Fraction: .01 means 1%, matching existing watchlist formatting. */
  change_pct: number | null
  volume: PreviewQuantity
  turnover: PreviewQuantity
  watchlisted: boolean | null
  missing_reasons: readonly string[]
  evidence_reference: string
  generated_at: string
  available_at: null
}
export interface WatchlistPreviewData extends IndexPreviewProvenance {
  market: WatchlistPreviewMarket
  trading_date: string
  rows: readonly WatchlistPreviewRow[]
}
export type WatchlistPreviewState = { kind: 'ready'; data: WatchlistPreviewData } | { kind: 'error' } | { kind: 'loading' }

export function validateWatchlistPreview(data: WatchlistPreviewData): WatchlistPreviewData {
  const provenance = (value: IndexPreviewProvenance) => value.status === 'PREVIEW' && value.source === 'synthetic-fixture'
    && value.data_mode === 'preview' && value.is_production === false && value.is_investment_signal === false
    && value.fixture_only === true && value.synthetic === true
  if (!provenance(data) || !['HK', 'US'].includes(data.market)) throw new Error('watchlist_fixture_preview_required')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(data.trading_date)) throw new Error('fixed_preview_date_required')
  if (new Set(data.rows.map(row => row.symbol)).size !== data.rows.length) throw new Error('duplicate_fixture_member')
  for (const row of data.rows) {
    if (!provenance(row) || row.market !== data.market) throw new Error('mixed_watchlist_preview')
    if ((row.price === null || row.change_pct === null || row.watchlisted === null) && !row.missing_reasons.length) throw new Error('missing_preview_reason')
    for (const quantity of [row.volume, row.turnover]) {
      if (quantity.value === null ? !quantity.reason : !Number.isFinite(quantity.value) || !quantity.unit) throw new Error('quantity_preview_evidence_required')
    }
    if ([row.price, row.change_pct].some(value => value !== null && !Number.isFinite(value))) throw new Error('nonfinite_preview_value')
  }
  return data
}
