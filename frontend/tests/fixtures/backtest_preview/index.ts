import { resultKeys, validateBacktestPreview, type BacktestMarket, type BacktestPreviewData, type BacktestSample } from '../../../src/custom/damon/backtest-preview/contract'

const flags = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false, is_investment_signal: false, fixture_only: true, synthetic: true } as const
function sample(market: BacktestMarket, suffix: 'A' | 'B'): BacktestSample {
  const unknown = Object.fromEntries(resultKeys.map(key => [key, null])) as BacktestSample['unknown']
  return {
    ...flags, id: `fixture-backtest-${market}-${suffix}`, market,
    name: `${market} 合成${suffix === 'A' ? '方案' : '验证'} ${suffix}`,
    kind: suffix === 'A' ? 'strategy' : 'robustness', currency: market === 'HK' ? 'HKD' : 'USD', fixture_version: 'v1',
    definition_status: suffix === 'A' ? 'PARTIAL' : 'BLOCKED', execution_status: 'BLOCKED',
    plan: { start: market === 'HK' ? '2026-06-01' : '2026-07-01', end: '2026-09-16', timeframe: 'daily', combination: 'AND', lookback_sessions: suffix === 'B' ? null : market === 'HK' ? 20 : 30 },
    unknown, missing_reasons: { ...Object.fromEntries(resultKeys.map(key => [key, '没有真实任务、输入身份或执行证据；样稿不运行回测，不能推导生产结果'])), lookback_sessions: '此验证样稿未定义窗口，不使用默认值补齐' },
    evidence: `fixture:backtest:${market}:${suffix}:v1`,
    blockers: ['生产执行 BLOCKED：Volume / VR20、split-only、Daily finality、PIT / vintage、正式 Universe 尚未闭合'],
    warnings: ['仅固定方案元数据，不是已执行回测或业绩；不校验真实交易日历、收益、费用或成交'],
  }
}
// Separate market-owned envelopes; no production IDs, reports, input bars or task restoration.
const hk: BacktestPreviewData = { ...flags, market: 'HK', trading_date: '2026-09-16', generated_at: '2026-09-17T09:00:00Z', rows: [sample('HK', 'A'), sample('HK', 'B')] }
const us: BacktestPreviewData = { ...flags, market: 'US', trading_date: '2026-09-16', generated_at: '2026-09-17T10:00:00Z', rows: [sample('US', 'A'), sample('US', 'B')] }
export function loadBacktestPreview(market: BacktestMarket): BacktestPreviewData {
  return validateBacktestPreview(structuredClone(market === 'HK' ? hk : us))
}
