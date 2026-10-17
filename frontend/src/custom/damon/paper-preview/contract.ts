import type { PaperOrder } from '@/lib/api'
import type { IndexPreviewProvenance } from '../index-preview/contract'
export type PaperPreviewMarket = 'HK' | 'US'
interface Sample extends IndexPreviewProvenance { sample_id: string; market: PaperPreviewMarket; evidence: string }
export interface PaperPositionSample extends Sample {
  symbol: string; name: string; qty: number; available_qty: null; cost_price: number; reference_price: number
  market_value: number; unrealized_pnl: number; return_pct: number; reason: string
}
export interface PaperOrderSample extends Sample {
  symbol: string; side: PaperOrder['side']; order_type: PaperOrder['order_type']; sample_status: PaperOrder['status']
  qty: number; ref_price: number | null; submitted_at: string; reason: string | null
}
export interface PaperFillSample extends Sample {
  order_sample_id: string; symbol: string; side: PaperOrder['side']; qty: number; price: number; fee: number; filled_at: string
}
export interface PaperPreviewData extends IndexPreviewProvenance {
  market: PaperPreviewMarket; currency: 'HKD' | 'USD'; account_sample_id: string; trading_date: string; generated_at: string
  initial_cash: number; cash: number; market_value: number; total_assets: number
  realized_pnl_gross: number; unrealized_pnl_gross: number; fees: number; total_pnl_net: number; return_pct: number
  cost_basis: 'EXECUTION_PRICE_EX_FEES_SAMPLE'; cash_flow_mode: 'NO_EXTERNAL_FLOWS_SAMPLE'
  positions: readonly PaperPositionSample[]; orders: readonly PaperOrderSample[]; fills: readonly PaperFillSample[]
  history: readonly { date: string; cash: number; market_value: number; total_assets: number; return_pct: number }[]
  win_rate: null; missing_fields: readonly string[]; reasons: readonly string[]; blockers: readonly string[]; warnings: readonly string[]
}
export type PaperPreviewState = { kind: 'ready'; data: PaperPreviewData } | { kind: 'loading' } | { kind: 'error' }
export function validatePaperPreview(d: PaperPreviewData): PaperPreviewData {
  const preview = (v: IndexPreviewProvenance) => v.status === 'PREVIEW' && v.source === 'synthetic-fixture' && v.data_mode === 'preview' && v.is_production === false && v.is_investment_signal === false && v.fixture_only === true && v.synthetic === true
  const time = (s: string) => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(s) && Number.isFinite(Date.parse(s))
  const cents = (n: number) => Math.round(n * 100)
  const sameMoney = (a: number, b: number) => Number.isFinite(a) && Number.isFinite(b) && cents(a) === cents(b)
  if (!preview(d) || !['HK', 'US'].includes(d.market) || d.currency !== (d.market === 'HK' ? 'HKD' : 'USD') || !d.account_sample_id.startsWith('fixture-paper-') || !time(d.generated_at) || !/^\d{4}-\d{2}-\d{2}$/.test(d.trading_date) || d.cost_basis !== 'EXECUTION_PRICE_EX_FEES_SAMPLE' || d.cash_flow_mode !== 'NO_EXTERNAL_FLOWS_SAMPLE') throw new Error('paper_fixture_required')
  for (const key of ['initial_cash', 'cash', 'market_value', 'total_assets', 'realized_pnl_gross', 'unrealized_pnl_gross', 'fees', 'total_pnl_net', 'return_pct'] as const) if (!Number.isFinite(d[key])) throw new Error('nonfinite_paper_sample')
  if (d.initial_cash <= 0 || d.cash < 0 || d.fees < 0 || !sameMoney(d.total_assets, d.cash + d.market_value) || !sameMoney(d.total_pnl_net, d.total_assets - d.initial_cash) || !sameMoney(d.total_pnl_net, d.realized_pnl_gross + d.unrealized_pnl_gross - d.fees) || d.return_pct !== d.total_pnl_net / d.initial_cash) throw new Error('paper_sample_balance_conflict')
  for (const rows of [d.positions, d.orders, d.fills]) {
    if (new Set(rows.map(r => r.sample_id)).size !== rows.length) throw new Error('duplicate_paper_sample')
    for (const r of rows) if (!preview(r) || r.market !== d.market || !r.sample_id.startsWith('fixture-') || !r.evidence.startsWith('fixture:')) throw new Error('mixed_paper_sample')
  }
  for (const p of d.positions) {
    if ([p.qty, p.cost_price, p.reference_price, p.market_value, p.unrealized_pnl, p.return_pct].some(v => !Number.isFinite(v)) || p.qty <= 0 || p.cost_price <= 0 || p.reference_price <= 0 || p.available_qty !== null || !p.reason.trim() || !sameMoney(p.market_value, p.qty * p.reference_price) || !sameMoney(p.unrealized_pnl, p.qty * (p.reference_price - p.cost_price)) || Math.abs(p.return_pct - (p.reference_price / p.cost_price - 1)) > 1e-12) throw new Error('invalid_paper_position_sample')
  }
  for (const o of d.orders) if (!['buy', 'sell'].includes(o.side) || !['market', 'next_open', 'close'].includes(o.order_type) || !['pending', 'filled', 'cancelled', 'expired'].includes(o.sample_status) || !Number.isFinite(o.qty) || o.qty <= 0 || !time(o.submitted_at) || (o.ref_price === null ? !o.reason : !Number.isFinite(o.ref_price) || o.ref_price <= 0)) throw new Error('invalid_paper_order_sample')
  for (const f of d.fills) {
    const o = d.orders.find(order => order.sample_id === f.order_sample_id)
    if (!o || o.sample_status !== 'filled' || o.symbol !== f.symbol || o.side !== f.side || !time(f.filled_at) || f.filled_at < o.submitted_at || [f.qty, f.price, f.fee].some(v => !Number.isFinite(v)) || f.qty <= 0 || f.price <= 0 || f.fee < 0) throw new Error('invalid_paper_fill_sample')
  }
  if (d.orders.some(o => o.sample_status === 'filled' && d.fills.filter(f => f.order_sample_id === o.sample_id).reduce((n, f) => n + f.qty, 0) !== o.qty)) throw new Error('paper_sample_fill_quantity_conflict')
  if (!sameMoney(d.market_value, d.positions.reduce((s, p) => s + p.market_value, 0)) || !sameMoney(d.unrealized_pnl_gross, d.positions.reduce((s, p) => s + p.unrealized_pnl, 0)) || !sameMoney(d.fees, d.fills.reduce((s, f) => s + f.fee, 0))) throw new Error('paper_sample_totals_conflict')
  if (d.win_rate !== null || !d.missing_fields.includes('win_rate') || !d.reasons.length || !d.blockers.length || !d.warnings.length) throw new Error('paper_missing_reason_required')
  if (new Set(d.history.map(h => h.date)).size !== d.history.length || d.history.some(h => !/^\d{4}-\d{2}-\d{2}$/.test(h.date) || h.date > d.trading_date || !sameMoney(h.total_assets, h.cash + h.market_value) || h.return_pct !== (cents(h.total_assets) - cents(d.initial_cash)) / cents(d.initial_cash))) throw new Error('invalid_paper_sample_history')
  return d
}
