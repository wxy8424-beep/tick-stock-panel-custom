/** Synthetic presentation examples only. Not observations, calculations or investment signals. */
import { validatePreview, type MomentumItem, type MomentumLadderViewModel, type MomentumMarket,
  type Metric, type Label, type QualityStatus, type Tier } from '../../../src/custom/damon/momentum-ladder/contract'

const value = (v: Metric['value'], status: QualityStatus = 'READY', reason: string | null = null): Metric => ({
  value: v, status: v === null && status === 'READY' ? 'UNAVAILABLE' : status,
  reason: v === null ? reason ?? '缺少指标输入（合成示例）' : reason,
})
const generated = '2026-09-17T00:00:00Z'

function item(market: MomentumMarket, symbol: string, name: string, rank: number, tier: Tier,
  status: QualityStatus, labels: Label[]): MomentumItem {
  const missing = status === 'BLOCKED'
  return {
    symbol, name: `${name} · 示例`, market, rank: status === 'READY' ? rank : null,
    tier: status === 'READY' ? tier : null, strength_score: status === 'READY' ? (rank === 1 ? 86 : rank === 2 ? 64 : 52) : null,
    labels,
    metrics: {
      close: value(missing ? null : 100 + rank, missing ? 'UNAVAILABLE' : 'READY', missing ? '缺少已验证收盘价（示例）' : null),
      change_pct: value(missing ? null : 0.025), consecutive_up_days: value(missing ? null : 3),
      period_return_3d: value(missing ? null : 0.04), period_return_5d: value(missing ? null : 0.065),
      period_return_10d: value(missing ? null : 0.09),
      volume_ratio: missing || status === 'PARTIAL'
        ? value(null, 'BLOCKED', '成交量单位及公司行动可比性尚未证明') : value(1.8),
      breakout_status: missing ? value(null, 'UNAVAILABLE', '缺少完整突破窗口（示例）') : value(rank === 1),
      volatility_trend_status: missing ? value(null, 'UNAVAILABLE', '缺少前一交易日波动率（示例）') : value(rank === 1 ? 'CONTRACTING' : 'UNCHANGED'),
    },
    evidence: {
      status, source: `synthetic-fixture/${market.toLowerCase()}/v1`, generated_at: generated,
      available_at: status === 'READY' ? generated : null, finality: status === 'READY' ? 'READY' : 'PARTIAL',
      pit_status: status === 'READY' ? 'READY' : 'BLOCKED',
      reasons: status === 'READY' ? ['仅验证展示，不认证供应商证据'] : ['历史 PIT / vintage 尚未证明；可得时间未知'],
    },
    quality: { status, reasons: status === 'READY' ? ['合成完整案例，非生产 READY'] : ['合成缺证据案例；分数和 tier 为展示输入，不由本页计算'] },
  }
}

const hk = [
  item('HK', '0700.HK', '腾讯控股', 1, 'T1', 'READY', ['leader', 'breakout', 'volume_spike', 'consecutive_up']),
  item('HK', '9988.HK', '阿里巴巴', 2, 'T2', 'READY', ['follower', 'consecutive_up']),
  item('HK', '3690.HK', '美团', 3, 'T3', 'READY', ['qualified_momentum']),
  item('HK', '0005.HK', '汇丰控股', 4, 'T3', 'PARTIAL', []),
  item('HK', '1299.HK', '友邦保险', 5, 'T3', 'BLOCKED', []),
]
const us = [
  item('US', 'AAPL.US', 'Apple', 1, 'T1', 'READY', ['momentum_leader', 'breakout', 'gap_up', 'volume_spike', 'consecutive_up']),
  item('US', 'NVDA.US', 'NVIDIA', 2, 'T2', 'READY', ['consecutive_up']),
  item('US', 'MSFT.US', 'Microsoft', 3, 'T3', 'READY', []),
  item('US', 'AMZN.US', 'Amazon', 4, 'T3', 'PARTIAL', []),
  item('US', 'META.US', 'Meta', 5, 'T3', 'BLOCKED', []),
]

function fixture(market: MomentumMarket, items: MomentumItem[]): MomentumLadderViewModel {
  const definitions: [string, string, (i: MomentumItem) => boolean][] = market === 'HK'
    ? [['t1', 'T1 龙头', i => i.tier === 'T1'], ['t2', 'T2 强势', i => i.tier === 'T2'],
      ['t3', 'T3 强势', i => i.tier === 'T3'], ['breakout', '突破', i => i.labels.includes('breakout')],
      ['up', '连续上涨', i => i.labels.includes('consecutive_up')], ['volume', '放量', i => i.labels.includes('volume_spike')]]
    : [['leader', 'Momentum Leader', i => i.labels.includes('momentum_leader')],
      ['breakout', 'Breakout', i => i.labels.includes('breakout')], ['gap', 'Gap Up', i => i.labels.includes('gap_up')],
      ['volume', 'Volume Spike', i => i.labels.includes('volume_spike')], ['up', 'Consecutive Up', i => i.labels.includes('consecutive_up')],
      ['t2-t3', 'T2 / T3 Momentum', i => i.tier === 'T2' || i.tier === 'T3']]
  return validatePreview({
    mode: 'FIXTURE_PREVIEW', fixture_only: true, production: false, synthetic: true,
    market, trading_date: '2026-09-16',
    universe: { id: `fixture-${market.toLowerCase()}-presentation`, version: 'v1', content_hash: null },
    calculation: { id: 'momentum-daily', version: 'v1.1', content_hash: '790212a4fd6ac7f3c50f2941a1eb51e192ebd873ac3c796cc07a0dd12460e7de' },
    profile: { id: 'momentum-technical', version: 'v1.2', content_hash: '8c48c32df331939908af76363e697827eda83de41639b80767e160be22d0832f' },
    items, groups: definitions.map(([id, title, predicate]) => ({ id, title, symbols: items.filter(predicate).map(i => i.symbol) })),
    overall_status: 'PARTIAL',
    warnings: ['仅合成 fixture 预览；非生产数据，不构成投资信号。',
      'Volume/VR20、split-only、finality、PIT/vintage、正式 Universe 仍未闭合；Production Execution: BLOCKED。',
      '示例分数、rank、tier 和标签是固定展示值；不代表 Engine 计算或可执行排名。Universe hash 未建立。'],
  })
}

/** Returns a fresh isolated object. No API, localStorage, provider or SQLite access. */
export function loadMomentumPreview(market: MomentumMarket): MomentumLadderViewModel {
  return structuredClone(fixture(market, market === 'HK' ? hk : us))
}
