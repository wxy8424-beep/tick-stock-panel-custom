/** Independent synthetic UI examples; never the user's actual watchlist or market observations. */
import { validateWatchlistPreview, type WatchlistPreviewData, type WatchlistPreviewMarket,
  type WatchlistPreviewRow } from '../../../src/custom/damon/watchlist-preview/contract'
const provenance = {
  status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false,
  is_investment_signal: false, fixture_only: true, synthetic: true,
} as const

function rows(market: WatchlistPreviewMarket): WatchlistPreviewRow[] {
  const names = market === 'HK' ? [['0700.HK', '腾讯控股'], ['9988.HK', '阿里巴巴'], ['3690.HK', '美团']]
    : [['AAPL.US', 'Apple'], ['NVDA.US', 'NVIDIA'], ['MSFT.US', 'Microsoft']]
  return names.map(([symbol, name], index) => ({
    ...provenance, market, symbol, name,
    price: index === 2 ? null : market === 'HK' ? [300, 100][index] : [200, 150][index],
    change_pct: index === 2 ? null : index === 0 ? 0.025 : -0.01,
    volume: index === 2 ? { value: null, unit: null, reason: '演示案例未提供成交量，单位及可比性未证明' }
      : { value: index === 0 ? 1000000 : 800000, unit: '合成数量单位（非供应商口径）', reason: null },
    turnover: index === 2 ? { value: null, unit: null, reason: '演示案例未提供成交额，不补零' }
      : { value: index === 0 ? 50000000 : 20000000, unit: `${market === 'HK' ? 'HKD' : 'USD'}（合成）`, reason: null },
    watchlisted: index === 2 ? null : true,
    missing_reasons: index === 2 ? ['演示案例缺少已验证价格、涨跌幅和自选状态'] : [],
    evidence_reference: `fixture:watchlist:${market}:${symbol}:v1`, generated_at: '2026-09-17T00:00:00Z', available_at: null,
  }))
}

export function loadWatchlistPreview(market: WatchlistPreviewMarket): WatchlistPreviewData {
  return validateWatchlistPreview({ ...provenance, market, trading_date: '2026-09-16', rows: rows(market) })
}
