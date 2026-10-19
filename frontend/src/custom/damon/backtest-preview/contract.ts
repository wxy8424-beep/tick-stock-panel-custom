import type { IndexPreviewProvenance } from '../index-preview/contract'

export type BacktestMarket = 'HK' | 'US'
export const resultKeys = ['production_run_id', 'production_strategy_version', 'total_return', 'max_drawdown', 'trade_count', 'completed_at', 'input_contract', 'universe_identity'] as const
export interface BacktestSample extends IndexPreviewProvenance {
  id: string
  market: BacktestMarket
  name: string
  kind: 'strategy' | 'robustness'
  currency: 'HKD' | 'USD'
  fixture_version: 'v1'
  definition_status: 'PARTIAL' | 'BLOCKED'
  execution_status: 'BLOCKED'
  plan: { start: string; end: string; timeframe: 'daily'; combination: 'AND'; lookback_sessions: number | null }
  unknown: Record<typeof resultKeys[number], null>
  missing_reasons: Record<string, string>
  evidence: string
  blockers: readonly string[]
  warnings: readonly string[]
}
export interface BacktestPreviewData extends IndexPreviewProvenance {
  market: BacktestMarket
  trading_date: string
  generated_at: string
  rows: readonly BacktestSample[]
}
export type BacktestPreviewState = { kind: 'ready'; data: BacktestPreviewData } | { kind: 'loading' } | { kind: 'error' }

const flags = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false, is_investment_signal: false, fixture_only: true, synthetic: true } as const
function fail(): never { throw new Error('invalid_backtest_preview') }
function object(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== 'object' || Array.isArray(v)) fail()
  return v as Record<string, unknown>
}
function exact(v: Record<string, unknown>, keys: readonly string[]) {
  if (Object.keys(v).length !== keys.length || keys.some(k => !Object.hasOwn(v, k))) fail()
}
function text(v: unknown): v is string { return typeof v === 'string' && !!v.trim() }
function provenance(v: Record<string, unknown>) { for (const [key, value] of Object.entries(flags)) if (v[key] !== value) fail() }
function utc(v: unknown): v is string {
  return typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(v)
    && Number.isFinite(Date.parse(v)) && new Date(v).toISOString() === v.replace('Z', '.000Z')
}
function date(v: unknown): v is string { return typeof v === 'string' && utc(`${v}T00:00:00Z`) }
export function validateBacktestPreview(value: unknown): BacktestPreviewData {
  const data = object(value)
  exact(data, [...Object.keys(flags), 'market', 'trading_date', 'generated_at', 'rows']); provenance(data)
  if (!['HK', 'US'].includes(data.market as string) || !date(data.trading_date) || !utc(data.generated_at) || !Array.isArray(data.rows)) fail()
  const ids = new Set<string>()
  for (const item of data.rows) {
    const row = object(item)
    exact(row, [...Object.keys(flags), 'id', 'market', 'name', 'kind', 'currency', 'fixture_version', 'definition_status', 'execution_status', 'plan', 'unknown', 'missing_reasons', 'evidence', 'blockers', 'warnings']); provenance(row)
    if (!text(row.id) || !new RegExp(`^fixture-backtest-${data.market}-[AB]$`).test(row.id) || ids.has(row.id)
      || row.market !== data.market || !text(row.name) || !['strategy', 'robustness'].includes(row.kind as string)
      || row.currency !== (data.market === 'HK' ? 'HKD' : 'USD') || row.fixture_version !== 'v1'
      || !['PARTIAL', 'BLOCKED'].includes(row.definition_status as string) || row.execution_status !== 'BLOCKED'
      || row.evidence !== `fixture:backtest:${data.market}:${row.id.slice(-1)}:v1`) fail()
    ids.add(row.id)
    const plan = object(row.plan), unknown = object(row.unknown), reasons = object(row.missing_reasons)
    exact(plan, ['start', 'end', 'timeframe', 'combination', 'lookback_sessions']); exact(unknown, resultKeys)
    if (!date(plan.start) || !date(plan.end) || plan.start > plan.end || plan.timeframe !== 'daily' || plan.combination !== 'AND'
      || (plan.lookback_sessions !== null && (typeof plan.lookback_sessions !== 'number' || !Number.isSafeInteger(plan.lookback_sessions) || plan.lookback_sessions < 1))) fail()
    if (Object.values(reasons).some(v => !text(v)) || (plan.lookback_sessions === null && !text(reasons.lookback_sessions))) fail()
    for (const key of resultKeys) if (unknown[key] !== null || !text(reasons[key])) fail()
    for (const key of ['blockers', 'warnings']) if (!Array.isArray(row[key]) || !row[key].length || row[key].some(v => !text(v))) fail()
  }
  return value as BacktestPreviewData
}
