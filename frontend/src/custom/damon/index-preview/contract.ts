/** Dedicated presentation DTO; display codes are not provider instrument identities. */
export type IndexPreviewMarket = 'HK' | 'US'
export interface IndexPreviewProvenance {
  status: 'PREVIEW'
  source: 'synthetic-fixture'
  data_mode: 'preview'
  is_production: false
  is_investment_signal: false
  fixture_only: true
  synthetic: true
}
export interface IndexPreviewRow extends IndexPreviewProvenance {
  symbol: string
  name: string
  market: IndexPreviewMarket
  trading_date: string
  latest_value: number | null
  change: number | null
  /** Percentage points: 1 means 1%, matching the existing CN index display contract. */
  change_pct: number | null
  open: number | null
  high: number | null
  low: number | null
  prev_close: number | null
  turnover: number | null
  turnover_currency: 'HKD' | 'USD'
  missing_reason: string | null
}
export interface IndexPreviewData extends IndexPreviewProvenance {
  market: IndexPreviewMarket
  trading_date: string
  rows: readonly IndexPreviewRow[]
}
export type IndexPreviewState = { kind: 'ready'; data: IndexPreviewData }
  | { kind: 'loading' } | { kind: 'error' }

export function validateIndexPreview(data: IndexPreviewData): IndexPreviewData {
  function provenance(value: IndexPreviewProvenance) {
    return value.status === 'PREVIEW' && value.source === 'synthetic-fixture' && value.data_mode === 'preview'
      && value.is_production === false && value.is_investment_signal === false && value.fixture_only === true && value.synthetic === true
  }
  if (!provenance(data) || (data.market !== 'HK' && data.market !== 'US')) throw new Error('index_fixture_preview_required')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(data.trading_date)) throw new Error('preview_trading_date_required')
  if (new Set(data.rows.map(row => row.symbol)).size !== data.rows.length) throw new Error('duplicate_preview_index')
  for (const row of data.rows) {
    if (!provenance(row) || row.market !== data.market || row.trading_date !== data.trading_date) throw new Error('mixed_preview_identity')
    for (const key of ['latest_value', 'change', 'change_pct', 'open', 'high', 'low', 'prev_close', 'turnover'] as const) {
      if (row[key] !== null && !Number.isFinite(row[key])) throw new Error('nonfinite_preview_value')
      if (row[key] === null && !row.missing_reason) throw new Error('missing_preview_reason')
    }
  }
  return data
}

export function sortIndexPreview(rows: readonly IndexPreviewRow[], direction: 'asc' | 'desc'): IndexPreviewRow[] {
  return [...rows].sort((a, b) => {
    if (a.change_pct === null && b.change_pct !== null) return 1
    if (b.change_pct === null && a.change_pct !== null) return -1
    const change = a.change_pct !== null && b.change_pct !== null ? (a.change_pct - b.change_pct) * (direction === 'asc' ? 1 : -1) : 0
    return change || (a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0)
  })
}
