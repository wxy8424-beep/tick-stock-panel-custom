import type { IndexPreviewProvenance } from '../index-preview/contract'

export type AnomaliesMarket = 'HK' | 'US'
export const unknownKeys = ['production_event_id', 'episode_id', 'rule_version', 'health_state', 'delivery_sequence', 'last_success_at', 'intelligence'] as const
export interface AnomalySample extends IndexPreviewProvenance {
  sample_id: string
  market: AnomaliesMarket
  symbol: string
  name: string
  event_type: 'rapid_price_move' | 'intraday_breakout'
  direction: 'up' | 'down'
  severity: 'low' | 'medium' | 'high'
  sample_state: 'SYNTHETIC_SAMPLE'
  event_time: string
  change_pct: number | null
  condition: { window_minutes: number | null; description: string }
  execution_status: 'BLOCKED'
  unknown: Record<typeof unknownKeys[number], null>
  missing_reasons: Record<string, string>
  evidence: string
  blockers: readonly string[]
  warnings: readonly string[]
}
export interface AnomaliesPreviewData extends IndexPreviewProvenance {
  market: AnomaliesMarket
  trading_date: string
  generated_at: string
  rows: readonly AnomalySample[]
}
export type AnomaliesPreviewState = { kind: 'ready'; data: AnomaliesPreviewData } | { kind: 'loading' } | { kind: 'error' }
export type AnomaliesMode = { kind: 'live' } | { kind: 'error' } | { kind: 'preview'; market: AnomaliesMarket }
export function selectAnomaliesMode(params: URLSearchParams): AnomaliesMode {
  const modes = params.getAll('data_mode'), markets = params.getAll('market')
  if (!modes.length) return { kind: 'live' }
  if (modes.length !== 1 || modes[0] !== 'preview' || markets.length !== 1 || !['HK', 'US'].includes(markets[0])) return { kind: 'error' }
  return { kind: 'preview', market: markets[0] as AnomaliesMarket }
}
const flags = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false, is_investment_signal: false, fixture_only: true, synthetic: true } as const
function fail(): never { throw new Error('invalid_anomalies_preview') }
function object(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== 'object' || Array.isArray(v)) fail()
  return v as Record<string, unknown>
}
function exact(v: Record<string, unknown>, keys: readonly string[]) { if (Object.keys(v).length !== keys.length || keys.some(k => !Object.hasOwn(v, k))) fail() }
function text(v: unknown): v is string { return typeof v === 'string' && !!v.trim() }
function provenance(v: Record<string, unknown>) { for (const [key, expected] of Object.entries(flags)) if (v[key] !== expected) fail() }
function utc(v: unknown): v is string {
  return typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(v)
    && Number.isFinite(Date.parse(v)) && new Date(v).toISOString() === v.replace('Z', '.000Z')
}
export function validateAnomaliesPreview(value: unknown): AnomaliesPreviewData {
  const data = object(value)
  exact(data, [...Object.keys(flags), 'market', 'trading_date', 'generated_at', 'rows']); provenance(data)
  if (!['HK', 'US'].includes(data.market as string) || typeof data.trading_date !== 'string' || !utc(`${data.trading_date}T00:00:00Z`) || !utc(data.generated_at) || !Array.isArray(data.rows)) fail()
  const ids = new Set<string>()
  for (const item of data.rows) {
    const row = object(item)
    exact(row, [...Object.keys(flags), 'sample_id', 'market', 'symbol', 'name', 'event_type', 'direction', 'severity', 'sample_state', 'event_time', 'change_pct', 'condition', 'execution_status', 'unknown', 'missing_reasons', 'evidence', 'blockers', 'warnings']); provenance(row)
    if (!text(row.sample_id) || !new RegExp(`^fixture-anomaly-${data.market}-[AB]$`).test(row.sample_id) || ids.has(row.sample_id)
      || row.market !== data.market || row.symbol !== `SYNTH-${row.sample_id.slice(-1)}.${data.market}` || !text(row.name)
      || !['rapid_price_move', 'intraday_breakout'].includes(row.event_type as string) || !['up', 'down'].includes(row.direction as string)
      || !['low', 'medium', 'high'].includes(row.severity as string) || row.sample_state !== 'SYNTHETIC_SAMPLE'
      || !utc(row.event_time) || row.event_time.slice(0, 10) !== data.trading_date || row.execution_status !== 'BLOCKED'
      || row.evidence !== `fixture:anomalies:${data.market}:${row.sample_id.slice(-1)}:v1`) fail()
    ids.add(row.sample_id)
    const reasons = object(row.missing_reasons), unknown = object(row.unknown), condition = object(row.condition)
    exact(unknown, unknownKeys); exact(condition, ['window_minutes', 'description'])
    if (!text(condition.description) || Object.values(reasons).some(v => !text(v))) fail()
    if (row.change_pct === null ? !text(reasons.change_pct) : typeof row.change_pct !== 'number' || !Number.isFinite(row.change_pct)) fail()
    if (condition.window_minutes === null ? !text(reasons.window_minutes) : typeof condition.window_minutes !== 'number' || !Number.isSafeInteger(condition.window_minutes) || condition.window_minutes < 1) fail()
    for (const key of unknownKeys) if (unknown[key] !== null || !text(reasons[key])) fail()
    for (const key of ['blockers', 'warnings']) if (!Array.isArray(row[key]) || !row[key].length || row[key].some(v => !text(v))) fail()
  }
  return value as AnomaliesPreviewData
}
