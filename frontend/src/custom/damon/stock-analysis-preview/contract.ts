import type { IndexPreviewProvenance } from '../index-preview/contract'

export type AnalysisMarket = 'HK' | 'US'
export const quoteKeys = ['last', 'change', 'changePercent', 'open', 'high', 'low', 'previousClose'] as const
export const unknownKeys = ['sector', 'industry', 'price_basis', 'volume_unit', 'available_at', 'source_vintage', 'production_report'] as const
export interface AnalysisSample extends IndexPreviewProvenance {
  id: string
  symbol: string
  name: string
  english_name: string
  market: AnalysisMarket
  currency: 'HKD' | 'USD'
  exchange: string
  security_type: 'SYNTHETIC_SAMPLE'
  quote: Record<typeof quoteKeys[number], number | null>
  technical: { ma20: number | null; volume_ratio_20: null }
  unknown: Record<typeof unknownKeys[number], null>
  missing_reasons: Record<string, string>
  evidence: string
  execution_status: 'BLOCKED'
  blockers: readonly string[]
  warnings: readonly string[]
}
export interface AnalysisPreviewData extends IndexPreviewProvenance {
  market: AnalysisMarket
  trading_date: string
  generated_at: string
  rows: readonly AnalysisSample[]
}
export type AnalysisPreviewState = { kind: 'ready'; data: AnalysisPreviewData } | { kind: 'loading' } | { kind: 'error' }

const flagKeys = ['status', 'source', 'data_mode', 'is_production', 'is_investment_signal', 'fixture_only', 'synthetic']
function fail(): never { throw new Error('invalid_stock_analysis_preview') }
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail()
  return value as Record<string, unknown>
}
function exact(value: Record<string, unknown>, keys: readonly string[]) {
  if (Object.keys(value).length !== keys.length || keys.some(k => !Object.hasOwn(value, k))) fail()
}
function text(value: unknown): value is string { return typeof value === 'string' && !!value.trim() }
function flags(value: Record<string, unknown>) {
  if (value.status !== 'PREVIEW' || value.source !== 'synthetic-fixture' || value.data_mode !== 'preview'
    || value.is_production !== false || value.is_investment_signal !== false || value.fixture_only !== true || value.synthetic !== true) fail()
}
function utc(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value)
    && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value.replace('Z', '.000Z')
}
export function validateAnalysisPreview(value: unknown): AnalysisPreviewData {
  const data = object(value)
  exact(data, [...flagKeys, 'market', 'trading_date', 'generated_at', 'rows']); flags(data)
  if (!['HK', 'US'].includes(data.market as string) || typeof data.trading_date !== 'string'
    || !utc(`${data.trading_date}T00:00:00Z`) || !utc(data.generated_at) || !Array.isArray(data.rows)) fail()
  const ids = new Set<string>()
  for (const item of data.rows) {
    const row = object(item)
    exact(row, [...flagKeys, 'id', 'symbol', 'name', 'english_name', 'market', 'currency', 'exchange', 'security_type',
      'quote', 'technical', 'unknown', 'missing_reasons', 'evidence', 'execution_status', 'blockers', 'warnings']); flags(row)
    if (!text(row.id) || !new RegExp(`^fixture-stock-${data.market}-[AB]$`).test(row.id) || ids.has(row.id)
      || row.symbol !== `SYNTH-${row.id.slice(-1)}.${data.market}` || row.market !== data.market
      || row.currency !== (data.market === 'HK' ? 'HKD' : 'USD') || !text(row.name) || !text(row.english_name)
      || row.exchange !== `${data.market}-SYNTHETIC-VENUE` || row.security_type !== 'SYNTHETIC_SAMPLE'
      || row.execution_status !== 'BLOCKED' || row.evidence !== `fixture:stock-analysis:${data.market}:${row.id.slice(-1)}:v1`) fail()
    ids.add(row.id)
    const reasons = object(row.missing_reasons)
    if (Object.values(reasons).some(v => !text(v))) fail()
    const quote = object(row.quote); exact(quote, quoteKeys)
    const technical = object(row.technical); exact(technical, ['ma20', 'volume_ratio_20'])
    const unknown = object(row.unknown); exact(unknown, unknownKeys)
    for (const [key, v] of [...Object.entries(quote), ...Object.entries(technical), ...Object.entries(unknown)]) {
      if (v === null ? !text(reasons[key]) : typeof v !== 'number' || !Number.isFinite(v)) fail()
    }
    if (technical.volume_ratio_20 !== null || Object.values(unknown).some(v => v !== null)) fail()
    for (const key of ['blockers', 'warnings']) if (!Array.isArray(row[key]) || !row[key].length || row[key].some(v => !text(v))) fail()
  }
  return value as AnalysisPreviewData
}
