import type { IndexPreviewProvenance } from '../index-preview/contract'

export type SignalMarket = 'HK' | 'US'
export type SignalQuality = 'READY' | 'PARTIAL' | 'UNAVAILABLE' | 'BLOCKED'
export interface SignalConditionSample {
  left: string | null
  op: '>' | '>=' | '<' | '<=' | '==' | '!=' | null
  right: { kind: 'number'; value: number } | { kind: 'field'; value: string } | null
  left_sessions: number | null
  right_sessions: number | null
  missing_reasons: Record<string, string>
}
export interface SignalSample extends IndexPreviewProvenance {
  id: string; name: string; market: SignalMarket; fixture_version: 'preview-v1'
  direction: 'entry' | 'exit' | 'both'; timeframe: 'daily' | 'intraday'
  logic: 'AND'; conditions: readonly SignalConditionSample[] | null
  definition_status: SignalQuality; execution_status: 'BLOCKED'
  production_version: null; last_trigger_at: null; trigger_count: null; production_binding: null
  missing_reasons: Record<string, string>; evidence: string
  blockers: readonly string[]; warnings: readonly string[]
}
export interface SignalPreviewData extends IndexPreviewProvenance {
  market: SignalMarket; trading_date: string; generated_at: string; rows: readonly SignalSample[]
}
export type SignalPreviewState = { kind: 'ready'; data: SignalPreviewData } | { kind: 'loading' } | { kind: 'error' }

const provenanceKeys = ['status', 'source', 'data_mode', 'is_production', 'is_investment_signal', 'fixture_only', 'synthetic']
const unknownKeys = ['production_version', 'last_trigger_at', 'trigger_count', 'production_binding'] as const
const fields = ['close', 'ma20', 'volume_ratio_20'] // Display vocabulary only; never a production field registry.
function fail(): never { throw new Error('invalid_signal_preview_contract') }
function object(v: unknown): Record<string, unknown> {
  if (!v || typeof v !== 'object' || Array.isArray(v)) fail()
  return v as Record<string, unknown>
}
function exact(v: Record<string, unknown>, keys: readonly string[]) {
  if (Object.keys(v).length !== keys.length || keys.some(k => !Object.hasOwn(v, k))) fail()
}
function text(v: unknown): v is string { return typeof v === 'string' && !!v.trim() }
function reasons(v: unknown) {
  const r = object(v)
  if (Object.values(r).some(value => !text(value))) fail()
  return r
}
function flags(v: Record<string, unknown>) {
  if (v.status !== 'PREVIEW' || v.source !== 'synthetic-fixture' || v.data_mode !== 'preview'
    || v.is_production !== false || v.is_investment_signal !== false || v.fixture_only !== true || v.synthetic !== true) fail()
}
function utc(v: unknown) {
  return typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(v)
    && Number.isFinite(Date.parse(v)) && new Date(v).toISOString() === v.replace('Z', '.000Z')
}
export function validateSignalPreview(value: unknown): SignalPreviewData {
  const d = object(value)
  exact(d, [...provenanceKeys, 'market', 'trading_date', 'generated_at', 'rows']); flags(d)
  if (!['HK', 'US'].includes(d.market as string) || typeof d.trading_date !== 'string'
    || !utc(`${d.trading_date}T00:00:00Z`) || !utc(d.generated_at) || !Array.isArray(d.rows)) fail()
  const ids = new Set<string>()
  for (const item of d.rows) {
    const r = object(item)
    exact(r, [...provenanceKeys, 'id', 'name', 'market', 'fixture_version', 'direction', 'timeframe', 'logic', 'conditions',
      'definition_status', 'execution_status', ...unknownKeys, 'missing_reasons', 'evidence', 'blockers', 'warnings']); flags(r)
    if (!text(r.id) || !new RegExp(`^fixture-signal-${d.market}-[0-9]+$`).test(r.id) || ids.has(r.id)
      || r.market !== d.market || !text(r.name) || r.fixture_version !== 'preview-v1'
      || !['entry', 'exit', 'both'].includes(r.direction as string) || !['daily', 'intraday'].includes(r.timeframe as string)
      || r.logic !== 'AND' || !['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED'].includes(r.definition_status as string)
      || r.execution_status !== 'BLOCKED' || unknownKeys.some(k => r[k] !== null)
      || r.evidence !== `fixture:signal:${d.market}:${r.id.split('-').at(-1)}:v1`) fail()
    ids.add(r.id)
    const missing = reasons(r.missing_reasons)
    if (unknownKeys.some(k => !text(missing[k]))) fail()
    for (const k of ['blockers', 'warnings']) if (!Array.isArray(r[k]) || !r[k].length || r[k].some(v => !text(v))) fail()
    if (r.conditions === null) {
      if (!text(missing.conditions) || r.definition_status === 'READY') fail()
      continue
    }
    if (!Array.isArray(r.conditions) || !r.conditions.length) fail()
    for (const value of r.conditions) {
      const c = object(value)
      exact(c, ['left', 'op', 'right', 'left_sessions', 'right_sessions', 'missing_reasons'])
      const missing = reasons(c.missing_reasons)
      for (const k of ['left', 'op', 'right', 'left_sessions', 'right_sessions']) {
        if (c[k] === null && !text(missing[k])) fail()
      }
      if (c.left !== null && !fields.includes(c.left as string) || c.op !== null && !['>', '>=', '<', '<=', '==', '!='].includes(c.op as string)) fail()
      for (const k of ['left_sessions', 'right_sessions']) {
        if (c[k] !== null && (typeof c[k] !== 'number' || !Number.isSafeInteger(c[k]) || (c[k] as number) < 0 || r.timeframe === 'intraday' && c[k] !== 0)) fail()
      }
      if (c.right !== null) {
        const right = object(c.right); exact(right, ['kind', 'value'])
        if (right.kind === 'number' ? typeof right.value !== 'number' || !Number.isFinite(right.value)
          : right.kind !== 'field' || !fields.includes(right.value as string)) fail()
        if (right.kind === 'number' && c.right_sessions !== null) fail()
      }
      if (r.definition_status === 'READY' && (c.left === null || c.op === null || c.right === null || c.left_sessions === null
        || object(c.right).kind === 'field' && c.right_sessions === null)) fail()
    }
  }
  return value as SignalPreviewData
}
