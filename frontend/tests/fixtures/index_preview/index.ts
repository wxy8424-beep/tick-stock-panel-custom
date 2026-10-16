/** Fixed synthetic display values. Never quote, historical candle or Archive data. */
import { validateIndexPreview, type IndexPreviewData, type IndexPreviewMarket, type IndexPreviewProvenance,
  type IndexPreviewRow } from '../../../src/custom/damon/index-preview/contract'

const provenance: IndexPreviewProvenance = {
  status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false,
  is_investment_signal: false, fixture_only: true, synthetic: true,
}
const tradingDate = '2026-09-16'
function row(market: IndexPreviewMarket, values: Pick<IndexPreviewRow,
  'symbol' | 'name' | 'latest_value' | 'change' | 'change_pct' | 'open' | 'high' | 'low' | 'prev_close' | 'turnover'>): IndexPreviewRow {
  return { ...provenance, market, trading_date: tradingDate, ...values,
    turnover_currency: market === 'HK' ? 'HKD' : 'USD',
    missing_reason: values.turnover === null ? 'fixture 未定义成交额；不补零、不从其他市场取值' : null }
}
const hk: IndexPreviewRow[] = [
  row('HK', { symbol: 'HSI', name: '恒生指数', latest_value: 20000, change: 200, change_pct: 1.01,
    open: 19830, high: 20120, low: 19800, prev_close: 19800, turnover: 120000000000 }),
  row('HK', { symbol: 'HSTECH', name: '恒生科技指数', latest_value: 4000, change: -40, change_pct: -0.99,
    open: 4030, high: 4060, low: 3960, prev_close: 4040, turnover: 30000000000 }),
  row('HK', { symbol: 'HSCEI', name: '国企指数', latest_value: 7000, change: 0, change_pct: 0,
    open: 6980, high: 7040, low: 6950, prev_close: 7000, turnover: 50000000000 }),
]
const us: IndexPreviewRow[] = [
  row('US', { symbol: 'SPX', name: 'S&P 500', latest_value: 5000, change: 25, change_pct: 0.50,
    open: 4980, high: 5020, low: 4960, prev_close: 4975, turnover: 150000000000 }),
  row('US', { symbol: 'IXIC', name: 'Nasdaq Composite', latest_value: 16000, change: 200, change_pct: 1.27,
    open: 15820, high: 16080, low: 15760, prev_close: 15800, turnover: 100000000000 }),
  row('US', { symbol: 'DJI', name: 'Dow Jones Industrial Average', latest_value: 39000, change: -100, change_pct: -0.26,
    open: 39120, high: 39200, low: 38850, prev_close: 39100, turnover: 60000000000 }),
  row('US', { symbol: 'RUT', name: 'Russell 2000', latest_value: 2000, change: 0, change_pct: 0,
    open: 1990, high: 2020, low: 1980, prev_close: 2000, turnover: null }),
]

export function loadIndexPreview(market: IndexPreviewMarket): IndexPreviewData {
  return validateIndexPreview(structuredClone({ ...provenance, market, trading_date: tradingDate, rows: market === 'HK' ? hk : us }))
}
