import type { IndexPreviewProvenance } from '../index-preview/contract'

export type FinancialMarket = 'HK' | 'US'
export type FinancialQuality = 'READY' | 'PARTIAL' | 'UNAVAILABLE' | 'BLOCKED'
export const statementFields = {
  revenue: ['营业收入', 'income'], operating_profit: ['营业利润', 'income'], net_income: ['净利润', 'income'],
  total_assets: ['总资产', 'balance'], total_liabilities: ['总负债', 'balance'], total_equity: ['股东权益', 'balance'],
  operating_cash_flow: ['经营活动现金流', 'cash'], capex: ['资本开支（正数流出）', 'cash'], free_cash_flow: ['自由现金流', 'cash'],
  net_margin: ['净利率', 'income'],
} as const
export type FinancialField = keyof typeof statementFields
export interface FinancialSampleValue {
  value: number | null; status: FinancialQuality; reason: string | null
  origin: 'SYNTHETIC_INPUT' | 'DERIVED_SAMPLE'; formula: string; evidence: string
}
export interface FinancialReportSample {
  id: string; period_start: string; period_end: string; report_type: 'ANNUAL' | 'QUARTER'
  flow_basis: 'FULL_YEAR' | 'SINGLE_QUARTER'; balance_basis: 'PERIOD_END'
  announce_at: string | null; available_at: string | null; time_reason: string | null
  values: Record<FinancialField, FinancialSampleValue>
}
export interface FinancialValuationSample extends FinancialSampleValue {
  key: 'PE' | 'PB' | 'PS' | 'DIVIDEND_YIELD' | 'MARKET_CAP' | 'EPS'
  unit: string; currency: 'HKD' | 'USD'; input_source: 'synthetic-fixture'
  price_at: string | null; price: number | null; report_id: string; financial_period: string; inputs: string
}
export interface FinancialCompanySample extends IndexPreviewProvenance {
  symbol: string; name: string; market: FinancialMarket; currency: 'HKD' | 'USD'; amount_unit: 'MILLION'
  reports: readonly FinancialReportSample[]; valuations: readonly FinancialValuationSample[]
}
export interface FinancialPreviewData extends IndexPreviewProvenance {
  market: FinancialMarket; trading_date: string; generated_at: string; companies: readonly FinancialCompanySample[]
  blockers: readonly string[]; warnings: readonly string[]
}
export type FinancialPreviewState = { kind: 'ready'; data: FinancialPreviewData } | { kind: 'loading' } | { kind: 'error' }

export function validateFinancialPreview(d: FinancialPreviewData): FinancialPreviewData {
  const flags = (v: IndexPreviewProvenance) => v.status === 'PREVIEW' && v.source === 'synthetic-fixture' && v.data_mode === 'preview' && v.is_production === false && v.is_investment_signal === false && v.fixture_only === true && v.synthetic === true
  const date = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s) && Number.isFinite(Date.parse(s))
  const time = (s: string) => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(s) && Number.isFinite(Date.parse(s))
  const value = (v: FinancialSampleValue) => {
    if (!['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED'].includes(v.status) || !['SYNTHETIC_INPUT', 'DERIVED_SAMPLE'].includes(v.origin) || !v.formula.trim() || !v.evidence.startsWith('fixture:') || (v.value !== null && !Number.isFinite(v.value)) || (v.value === null || v.status !== 'READY') && !v.reason?.trim() || v.value === null && v.status === 'READY') throw new Error('invalid_financial_sample_value')
  }
  if (!flags(d) || !['HK', 'US'].includes(d.market) || !date(d.trading_date) || !time(d.generated_at) || new Set(d.companies.map(c => c.symbol)).size !== d.companies.length) throw new Error('financial_preview_identity_required')
  for (const c of d.companies) {
    if (!flags(c) || c.market !== d.market || !c.symbol.endsWith(c.market === 'HK' ? '.HK' : '.US') || c.currency !== (c.market === 'HK' ? 'HKD' : 'USD') || c.amount_unit !== 'MILLION' || new Set(c.reports.map(r => r.id)).size !== c.reports.length) throw new Error('mixed_financial_sample')
    for (const r of c.reports) {
      if (!r.id.startsWith('fixture-') || !date(r.period_start) || !date(r.period_end) || r.period_start > r.period_end || r.period_end > d.trading_date || !['ANNUAL', 'QUARTER'].includes(r.report_type) || r.flow_basis !== (r.report_type === 'ANNUAL' ? 'FULL_YEAR' : 'SINGLE_QUARTER') || r.balance_basis !== 'PERIOD_END') throw new Error('invalid_financial_period')
      for (const t of [r.announce_at, r.available_at]) if (t !== null && (!time(t) || t.slice(0, 10) <= r.period_end || t > d.generated_at)) throw new Error('invalid_financial_availability')
      if ((r.announce_at === null || r.available_at === null) && !r.time_reason || r.announce_at !== null && r.available_at !== null && r.available_at < r.announce_at) throw new Error('financial_time_reason_required')
      for (const k of Object.keys(statementFields) as FinancialField[]) value(r.values[k])
      const v = r.values, ocf = v.operating_cash_flow.value, capex = v.capex.value, ni = v.net_income.value, rev = v.revenue.value
      const fcf = ocf === null || capex === null ? null : ocf - capex
      const margin = ni === null || rev === null || rev <= 0 ? null : 100 * ni / rev
      if (v.free_cash_flow.value !== fcf || v.net_margin.value !== margin) throw new Error('financial_derived_value_conflict')
      if (v.total_assets.value !== null && v.total_liabilities.value !== null && v.total_equity.value !== null && v.total_assets.value !== v.total_liabilities.value + v.total_equity.value) throw new Error('financial_sample_balance_conflict')
    }
    if (new Set(c.valuations.map(v => v.key)).size !== c.valuations.length) throw new Error('duplicate_financial_valuation')
    for (const v of c.valuations) {
      value(v)
      const r = c.reports.find(r => r.id === v.report_id)
      if (!r || v.currency !== c.currency || v.input_source !== 'synthetic-fixture' || v.financial_period !== r.period_end || !v.unit.trim() || !v.inputs.trim()) throw new Error('financial_valuation_binding_conflict')
      if (v.price_at !== null && (!time(v.price_at) || v.price_at > d.generated_at)) throw new Error('invalid_valuation_time')
      if (v.price !== null && (!Number.isFinite(v.price) || v.price <= 0)) throw new Error('invalid_valuation_price')
      if (v.key !== 'EPS' && v.value !== null && (!v.price_at || !r.available_at || r.available_at > v.price_at || v.price === null)) throw new Error('valuation_time_alignment_unproven')
      if ((v.status === 'BLOCKED' || v.status === 'UNAVAILABLE') && v.value !== null) throw new Error('blocked_valuation_must_be_null')
    }
  }
  return d
}
