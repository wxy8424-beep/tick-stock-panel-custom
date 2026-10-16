/** Dedicated authored environment examples. No market feed, other-page data or production statistics. */
import { validateEnvironmentPreview, type EnvironmentMarket, type EnvironmentPreviewData, type EnvironmentValue } from '../../../src/custom/damon/environment-preview/contract'

const provenance = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false,
  is_investment_signal: false, fixture_only: true, synthetic: true } as const
const value = (n: number): EnvironmentValue => ({ value: n, reason: null })
export function loadEnvironmentPreview(market: EnvironmentMarket): EnvironmentPreviewData {
  const hk = market === 'HK'
  const names = hk ? [['HSI', '恒生指数'], ['HSTECH', '恒生科技指数'], ['HSCEI', '国企指数']]
    : [['SPX', 'S&P 500'], ['IXIC', 'Nasdaq Composite'], ['DJI', 'Dow Jones'], ['RUT', 'Russell 2000']]
  return validateEnvironmentPreview({ ...provenance, market, days: ['2026-09-16', '2026-09-15'].map((date, dayIndex) => ({
    ...provenance, market, trading_date: date, generated_at: dayIndex === 0 ? '2026-09-17T01:00:00Z' : '2026-09-16T01:00:00Z', available_at: null,
    session: 'NONE', market_state: dayIndex === 0 ? 'POST_CLOSE' : 'CLOSED',
    indices: names.map(([symbol, name], i) => ({
      ...provenance, symbol, name, market, trading_date: date,
      latest_value: i === names.length - 1 ? { value: null, reason: '此指数未编写样稿点位，不以其他页面或真实报价补齐' } : value((hk ? 18000 : 5000) + i * 1000 + dayIndex * 10),
      change_pct: value(i === 0 ? (hk ? .015 : -.012) : i === 1 ? 0 : -.008),
      trend: i === 0 ? (hk ? 'UP' : 'DOWN') : i === 1 ? 'FLAT' : 'UNAVAILABLE',
      trend_reason: i >= 2 ? '演示未定义该指数趋势标签，不从涨跌幅推导' : null,
      evidence: `fixture:environment:${market}:${date}:index:${symbol}:v1`,
    })),
    metrics: {
      up: value(hk ? 60 : 40), down: value(hk ? 30 : 50), flat: value(10), up_down_ratio: value(hk ? 2 : .8),
      strong: value(hk ? 20 : 15), weak: value(hk ? 10 : 25), strong_weak_ratio: value(hk ? 2 : .6),
      breakout: value(hk ? 8 : 12), volume_spike: { value: null, reason: '未提供 Volume Spike 样稿统计；生产数量口径与 VR20 仍 BLOCKED' },
    },
    breadth_status: hk ? 'EXPANDING' : 'CONTRACTING',
    conclusion: dayIndex === 1 ? (hk ? 'NEUTRAL' : 'UNAVAILABLE') : (hk ? 'BULLISH' : 'WEAK'),
    conclusion_reason: !hk && dayIndex === 1 ? '该日期未编写环境结论，不应用 A 股或 Momentum 评分规则补算' : null,
    evidence: `fixture:environment:${market}:${date}:v1`,
    missing_fields: ['metrics.volume_spike', `indices.${names[names.length - 1][0]}.latest_value`],
    blockers: ['Volume / VR20 BLOCKED', 'split-only price basis BLOCKED', 'historical PIT/vintage BLOCKED', 'production Universe 未建立'],
    warnings: ['仅固定合成样本统计，非全市场覆盖；不是生产市场统计', '强弱、突破、趋势与环境结论均为预编写展示标签，不定义或执行生产公式', 'Daily finality PARTIAL；corporate actions UNKNOWN；Session 是固定演示状态，不证明日线最终定版'],
  })) })
}
