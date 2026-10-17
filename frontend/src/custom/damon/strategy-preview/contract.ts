import type { CustomSignalCondition, StrategyParamDef } from '@/lib/api'
import type { IndexPreviewProvenance } from '../index-preview/contract'
export type StrategyPreviewMarket = 'HK' | 'US'
export type StrategyPreviewQuality = 'READY' | 'PARTIAL' | 'UNAVAILABLE' | 'BLOCKED'
export interface StrategyParameterSample extends Pick<StrategyParamDef, 'id' | 'label' | 'type'> {
  value: number | null; unit: string; default_value: number | null; min: number | null; max: number | null
  version: string; contract_reference: string; status: StrategyPreviewQuality; reason: string; evidence: string
}
export interface StrategyRuleSample {
  logic: 'AND' | 'OR'; conditions: readonly CustomSignalCondition[]; evidence: string
}
export interface StrategyRiskSample {
  key: string; label: string; value: number | null; unit: string; status: StrategyPreviewQuality
  enforced: false; reason: string; contract_reference: string | null
}
export interface StrategyDependencySample { key: string; status: StrategyPreviewQuality; reason: string; evidence: string }
export interface StrategyPreviewRow extends IndexPreviewProvenance {
  id: string; version: string; market: StrategyPreviewMarket; name: string; description: string
  strategy_type: 'TREND_SAMPLE' | 'FILTER_SAMPLE' | 'VOLUME_SAMPLE'; configuration_id: string; parameter_version: string
  display_state: 'DEFINED_SAMPLE' | 'INCOMPLETE_SAMPLE' | 'NO_RULE_SAMPLE' | 'BLOCKED_SAMPLE'
  definition_status: StrategyPreviewQuality; validation_status: 'BLOCKED'; runtime_status: null; last_run_at: null; signal_count: null
  symbols: readonly string[]; instrument_type: null; universe_identity: null; input_contract_identity: null
  entry: StrategyRuleSample | null; exit: StrategyRuleSample | null; rule_reason: string
  parameters: readonly StrategyParameterSample[]; risks: readonly StrategyRiskSample[]; dependencies: readonly StrategyDependencySample[]
  evidence: string; missing_fields: readonly string[]; blockers: readonly string[]; warnings: readonly string[]
}
export interface StrategyPreviewData extends IndexPreviewProvenance {
  market: StrategyPreviewMarket; trading_date: string; generated_at: string; rows: readonly StrategyPreviewRow[]
}
export type StrategyPreviewState = { kind: 'ready'; data: StrategyPreviewData } | { kind: 'loading' } | { kind: 'error' }
export function validateStrategyPreview(d: StrategyPreviewData): StrategyPreviewData {
  const flags = (v: IndexPreviewProvenance) => v.status === 'PREVIEW' && v.source === 'synthetic-fixture' && v.data_mode === 'preview' && v.is_production === false && v.is_investment_signal === false && v.fixture_only === true && v.synthetic === true
  const quality = (v: string) => ['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED'].includes(v)
  if (!flags(d) || !['HK', 'US'].includes(d.market) || !/^\d{4}-\d{2}-\d{2}$/.test(d.trading_date) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(d.generated_at) || !Number.isFinite(Date.parse(d.generated_at)) || new Set(d.rows.map(r => r.id)).size !== d.rows.length) throw new Error('strategy_preview_identity_required')
  for (const r of d.rows) {
    if (!flags(r) || r.market !== d.market || !r.id.startsWith(`fixture-strategy-${d.market}-`) || !r.version.startsWith('preview-') || !r.configuration_id.startsWith('fixture:') || !r.parameter_version.startsWith('preview-') || !r.evidence.startsWith('fixture:') || !quality(r.definition_status) || r.validation_status !== 'BLOCKED' || r.runtime_status !== null || r.last_run_at !== null || r.signal_count !== null || r.instrument_type !== null || r.universe_identity !== null || r.input_contract_identity !== null) throw new Error('invalid_strategy_preview_boundary')
    if (!['DEFINED_SAMPLE', 'INCOMPLETE_SAMPLE', 'NO_RULE_SAMPLE', 'BLOCKED_SAMPLE'].includes(r.display_state) || !['TREND_SAMPLE', 'FILTER_SAMPLE', 'VOLUME_SAMPLE'].includes(r.strategy_type) || !r.rule_reason.trim() || !r.blockers.length || !r.warnings.length || !r.missing_fields.length || r.symbols.some(s => !s.endsWith(d.market === 'HK' ? '.HK' : '.US'))) throw new Error('invalid_strategy_preview_scope')
    for (const group of [r.entry, r.exit]) if (group && (!['AND', 'OR'].includes(group.logic) || !group.conditions.length || !group.evidence.startsWith('fixture:') || group.conditions.some(c => !c.left.trim() || !['>', '>=', '<', '<=', '==', '!='].includes(c.op) || !c.right.trim() || [c.leftDays, c.rightDays].some(v => v !== undefined && (!Number.isSafeInteger(v) || v < 0))))) throw new Error('invalid_strategy_rule_sample')
    if (new Set(r.parameters.map(p => p.id)).size !== r.parameters.length) throw new Error('duplicate_strategy_parameter')
    for (const p of r.parameters) {
      if (p.version !== r.parameter_version || !p.reason.trim() || !p.evidence.startsWith('fixture:') || !quality(p.status) || !p.contract_reference.trim() || !p.unit.trim() || [p.value, p.default_value, p.min, p.max].some(v => v !== null && !Number.isFinite(v)) || p.value === null && p.status === 'READY') throw new Error('invalid_strategy_parameter_sample')
      if (p.type === 'int' && p.value !== null && !Number.isSafeInteger(p.value) || p.min !== null && p.max !== null && p.min > p.max || p.value !== null && (p.min !== null && p.value < p.min || p.max !== null && p.value > p.max)) throw new Error('invalid_strategy_parameter_range')
    }
    if (r.definition_status === 'READY' && (!r.entry || !r.exit || r.parameters.some(p => p.value === null))) throw new Error('incomplete_strategy_definition')
    for (const risk of r.risks) if (risk.enforced !== false || !quality(risk.status) || !risk.reason.trim() || risk.value !== null && !Number.isFinite(risk.value) || risk.value === null && risk.status === 'READY') throw new Error('invalid_strategy_risk_sample')
    for (const dep of r.dependencies) if (!quality(dep.status) || !dep.reason.trim() || !dep.evidence.trim()) throw new Error('invalid_strategy_dependency_sample')
  }
  return d
}
