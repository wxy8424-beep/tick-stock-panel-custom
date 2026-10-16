/** Presentation-only DTO. Never accepts a provider response or admits production inputs. */
export type MomentumMarket = 'HK' | 'US'
export type QualityStatus = 'READY' | 'PARTIAL' | 'UNAVAILABLE' | 'BLOCKED'
export type Trend = 'EXPANDING' | 'CONTRACTING' | 'UNCHANGED'
export type Tier = 'T1' | 'T2' | 'T3'
export type Label = 'leader' | 'follower' | 'qualified_momentum' | 'momentum_leader'
  | 'breakout' | 'gap_up' | 'volume_spike' | 'consecutive_up'
export type MetricKey = 'close' | 'change_pct' | 'consecutive_up_days' | 'period_return_3d'
  | 'period_return_5d' | 'period_return_10d' | 'volume_ratio' | 'breakout_status' | 'volatility_trend_status'
export interface Metric {
  value: number | boolean | Trend | null
  status: QualityStatus
  reason: string | null
}
export interface ArtifactIdentity { id: string; version: string; content_hash: string | null }
export interface MomentumItem {
  symbol: string
  name: string
  market: MomentumMarket
  rank: number | null
  tier: Tier | null
  strength_score: number | null
  labels: readonly Label[]
  metrics: Readonly<Record<MetricKey, Metric>>
  evidence: {
    status: QualityStatus
    source: string
    generated_at: string
    available_at: string | null
    finality: QualityStatus
    pit_status: QualityStatus
    reasons: readonly string[]
  }
  quality: { status: QualityStatus; reasons: readonly string[] }
}
export interface MomentumGroup { id: string; title: string; symbols: readonly string[] }
export interface MomentumLadderViewModel {
  mode: 'FIXTURE_PREVIEW'
  fixture_only: true
  production: false
  synthetic: true
  market: MomentumMarket
  trading_date: string
  universe: ArtifactIdentity
  calculation: ArtifactIdentity
  profile: ArtifactIdentity
  items: readonly MomentumItem[]
  groups: readonly MomentumGroup[]
  overall_status: QualityStatus
  warnings: readonly string[]
}

export const labelText: Record<Label, string> = {
  leader: 'T1 龙头', follower: 'T2 强势', qualified_momentum: 'T3 强势',
  momentum_leader: 'Momentum Leader', breakout: 'Breakout', gap_up: 'Gap Up',
  volume_spike: 'Volume Spike', consecutive_up: 'Consecutive Up',
}

/** Display existing ranks only; null stays unranked. No scoring, percentile or tier math. */
export function displayOrder(items: readonly MomentumItem[]): MomentumItem[] {
  return [...items].sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity)
    || (a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0))
}

/** Fail closed at the fixture adapter boundary, rather than silently re-labelling input. */
export function validatePreview(view: MomentumLadderViewModel): MomentumLadderViewModel {
  if (view.mode !== 'FIXTURE_PREVIEW' || view.fixture_only !== true || view.production !== false || view.synthetic !== true) {
    throw new Error('fixture_preview_required')
  }
  if (view.market !== 'HK' && view.market !== 'US') throw new Error('preview_market_required')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(view.trading_date)) throw new Error('fixed_trading_date_required')
  const symbols = new Set(view.items.map(item => item.symbol))
  if (symbols.size !== view.items.length || view.items.some(item => item.market !== view.market)) {
    throw new Error('preview_market_or_identity_conflict')
  }
  if (view.groups.some(group => group.symbols.some(symbol => !symbols.has(symbol)))) throw new Error('unknown_group_member')
  return view
}
