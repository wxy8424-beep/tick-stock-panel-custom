/** Authored isolated ledger examples, not a broker account or execution/replay engine. */
import { validatePaperPreview, type PaperPreviewData, type PaperPreviewMarket, type PaperPositionSample } from '../../../src/custom/damon/paper-preview/contract'
const flags = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false, is_investment_signal: false, fixture_only: true, synthetic: true } as const
export function loadPaperPreview(market: PaperPreviewMarket): PaperPreviewData {
  const hk = market === 'HK', prefix = `fixture:paper:${market}`
  const symbols = hk ? ['0700.HK', '9988.HK', '3690.HK'] : ['AAPL.US', 'NVDA.US', 'MSFT.US']
  const names = hk ? ['腾讯控股', '阿里巴巴'] : ['Apple', 'NVIDIA']
  const quantities = hk ? [100, 50] : [10, 5], costs = hk ? [300, 80] : [180, 120], prices = hk ? [315, 76] : [189, 114]
  const initial = hk ? 100000 : 10000, cash = hk ? 65980 : 7598, mv = hk ? 35300 : 2460, total = hk ? 101280 : 10058, fees = hk ? 20 : 2
  const positions: PaperPositionSample[] = symbols.slice(0, 2).map((symbol, i) => ({ ...flags, sample_id: `fixture-position-${market}-${i}`, market, symbol, name: names[i], qty: quantities[i], available_qty: null,
    cost_price: costs[i], reference_price: prices[i], market_value: hk ? (i ? 3800 : 31500) : (i ? 570 : 1890), unrealized_pnl: hk ? (i ? -200 : 1500) : (i ? -30 : 90), return_pct: i ? -.05 : .05,
    reason: '可卖数量未知：HK/US 结算/可卖契约未冻结，不套用 CN T+1', evidence: `${prefix}:position:${i}:v1` }))
  return validatePaperPreview({ ...flags, market, currency: hk ? 'HKD' : 'USD', account_sample_id: `fixture-paper-${market}`, trading_date: '2026-09-16', generated_at: '2026-09-17T05:00:00Z',
    initial_cash: initial, cash, market_value: mv, total_assets: total, realized_pnl_gross: 0, unrealized_pnl_gross: hk ? 1300 : 60, fees, total_pnl_net: hk ? 1280 : 58, return_pct: hk ? .0128 : .0058,
    cost_basis: 'EXECUTION_PRICE_EX_FEES_SAMPLE', cash_flow_mode: 'NO_EXTERNAL_FLOWS_SAMPLE', positions,
    orders: symbols.map((symbol, i) => ({ ...flags, sample_id: `fixture-order-${market}-${i}`, market, symbol, side: 'buy', order_type: i === 0 ? 'market' : i === 1 ? 'close' : 'next_open', sample_status: i === 2 ? 'pending' : 'filled', qty: i === 2 ? 10 : quantities[i], ref_price: i === 2 ? null : costs[i] + 1,
      submitted_at: `2026-09-15T${hk ? '06' : '14'}:0${i}:00Z`, reason: i === 2 ? '未提供委托参考价格；未成交，不生成费用或成交记录' : null, evidence: `${prefix}:order:${i}:v1` })),
    fills: symbols.slice(0, 2).map((symbol, i) => ({ ...flags, sample_id: `fixture-fill-${market}-${i}`, order_sample_id: `fixture-order-${market}-${i}`, market, symbol, side: 'buy', qty: quantities[i], price: costs[i], fee: hk ? 10 : 1, filled_at: `2026-09-15T${hk ? '06' : '14'}:1${i}:00Z`, evidence: `${prefix}:fill:${i}:v1` })),
    history: [{ date: '2026-09-14', cash: initial, market_value: 0, total_assets: initial, return_pct: 0 },
      { date: '2026-09-15', cash, market_value: hk ? 34000 : 2400, total_assets: initial - fees, return_pct: hk ? -.0002 : -.0002 },
      { date: '2026-09-16', cash, market_value: mv, total_assets: total, return_pct: hk ? .0128 : .0058 }],
    win_rate: null, missing_fields: ['positions.available_qty', 'orders.pending.ref_price', 'win_rate'], reasons: ['可卖数量和待成交参考价未定义，保留 null', '无已平仓回合，胜率不可得，不填零'],
    blockers: ['真实 HK/US 模拟撮合/结算/可卖规则未建立', 'Longbridge 数量、split-only、finality、PIT/vintage 和正式 Universe 尚未闭合'],
    warnings: ['成本按成交价不含费用；已实现/未实现盈亏均为毛值，费用单列扣一次', '无外部出入金；待成交订单不预扣现金、不产生持仓/成交/盈亏；这是固定样稿口径，不是生产规则', '合成股数和费用不代表 HK/US 实际交易费用/税费/结算规则；不是回测或真实业绩'],
  })
}
