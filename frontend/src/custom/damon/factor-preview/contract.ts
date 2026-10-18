import type { FactorLibraryItem } from '@/lib/api'
import type { IndexPreviewProvenance } from '../index-preview/contract'

export type FactorPreviewMarket = 'HK' | 'US'
export type FactorPreviewQuality = 'READY' | 'PARTIAL' | 'UNAVAILABLE' | 'BLOCKED'
export const FACTOR_VIEWS = ['inspect', 'library', 'editor', 'composite', 'mining'] as const
export type FactorPreviewView = typeof FACTOR_VIEWS[number]
export const FACTOR_VIEW_LABELS: Record<FactorPreviewView, string> = {
  inspect: '检验', library: '因子库', editor: '编辑器', composite: '组合', mining: '挖掘',
}

/** Inert display metadata, never a registered Factor definition or Snapshot. */
export interface FactorPreviewRow extends IndexPreviewProvenance,
  Pick<FactorLibraryItem, 'label' | 'kind' | 'group' | 'direction'> {
  id: string
  version: string
  market: FactorPreviewMarket
  description: string
  formula: string | null
  unit: string | null
  warmup_bars: number | null
  dependencies: readonly string[] | null
  sample_value: number | null
  definition_status: FactorPreviewQuality
  validation_status: 'BLOCKED'
  execution_status: 'BLOCKED'
  pit: null
  evaluated_at: null
  ic_mean: null
  ic_ir: null
  coverage_count: null
  universe_identity: null
  input_contract_identity: null
  sample_symbols: readonly string[]
  missing_reasons: Record<string, string>
  evidence: string
  blockers: readonly string[]
  warnings: readonly string[]
}
export interface FactorPreviewData extends IndexPreviewProvenance {
  market: FactorPreviewMarket
  trading_date: string
  generated_at: string
  rows: readonly FactorPreviewRow[]
}
export type FactorPreviewState = { kind: 'ready'; data: FactorPreviewData } | { kind: 'loading' } | { kind: 'error' }

export function validateFactorPreview(data: FactorPreviewData): FactorPreviewData {
  const flags = (v: IndexPreviewProvenance) => v.status === 'PREVIEW' && v.source === 'synthetic-fixture'
    && v.data_mode === 'preview' && v.is_production === false && v.is_investment_signal === false
    && v.fixture_only === true && v.synthetic === true
  if (!flags(data) || !['HK', 'US'].includes(data.market)
    || !/^\d{4}-\d{2}-\d{2}$/.test(data.trading_date) || !Number.isFinite(Date.parse(data.trading_date))
    || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(data.generated_at)) throw new Error('invalid_factor_preview_identity')
  if (new Set(data.rows.map(r => r.id)).size !== data.rows.length) throw new Error('duplicate_factor_preview')
  for (const row of data.rows) {
    if (!flags(row) || row.market !== data.market || !row.id.startsWith(`fixture-factor-${data.market}-`)
      || !row.version.startsWith('preview-') || !row.evidence.startsWith('fixture:')
      || !row.label.trim() || !row.description.trim() || !row.group.trim()
      || !['base', 'virtual', 'custom', 'composite'].includes(row.kind)
      || !['high', 'low', 'none'].includes(row.direction)
      || !['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED'].includes(row.definition_status)
      || row.validation_status !== 'BLOCKED' || row.execution_status !== 'BLOCKED'
      || [row.pit, row.evaluated_at, row.ic_mean, row.ic_ir, row.coverage_count,
        row.universe_identity, row.input_contract_identity].some(v => v !== null)
      || !row.blockers.length || !row.warnings.length
      || row.sample_symbols.some(s => !s.endsWith(`.${data.market}`))) throw new Error('invalid_factor_preview_boundary')
    for (const key of ['sample_value', 'warmup_bars'] as const) {
      const value = row[key]
      if (value !== null && (typeof value !== 'number' || !Number.isFinite(value))) throw new Error('nonfinite_factor_preview')
    }
    if (row.warmup_bars !== null && (!Number.isSafeInteger(row.warmup_bars) || row.warmup_bars < 1)) throw new Error('invalid_factor_warmup')
    for (const key of ['formula', 'unit', 'warmup_bars', 'dependencies', 'sample_value', 'pit',
      'evaluated_at', 'ic_mean', 'ic_ir', 'coverage_count', 'universe_identity', 'input_contract_identity'] as const) {
      if (row[key] === null && !row.missing_reasons[key]?.trim()) throw new Error('missing_factor_reason')
    }
    if (row.formula !== null && !row.formula.trim() || row.unit !== null && !row.unit.trim()
      || row.dependencies !== null && (!row.dependencies.length || row.dependencies.some(v => !v.trim()))) throw new Error('empty_factor_metadata')
    if (row.definition_status === 'READY' && [row.formula, row.unit, row.warmup_bars, row.dependencies].some(v => v === null)) throw new Error('incomplete_factor_definition')
  }
  return data
}
