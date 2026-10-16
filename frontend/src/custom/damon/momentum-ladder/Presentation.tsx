import { useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { loadMomentumPreview } from '../../../../tests/fixtures/momentum_ladder'
import { displayOrder, labelText, validatePreview, type Metric, type MetricKey, type MomentumItem,
  type MomentumLadderViewModel, type MomentumMarket, type QualityStatus } from './contract'

const statusClass: Record<QualityStatus, string> = {
  READY: 'border-accent/30 bg-accent/10 text-accent', PARTIAL: 'border-warning/30 bg-warning/10 text-warning',
  BLOCKED: 'border-bear/30 bg-bear/10 text-bear', UNAVAILABLE: 'border-border bg-base text-muted',
}
function Status({ value }: { value: QualityStatus }) {
  return <span className={`inline-flex rounded border px-1.5 py-0.5 text-[10px] font-medium ${statusClass[value]}`}>{value}</span>
}
const fields: [MetricKey, string][] = [
  ['close', '收盘价'], ['change_pct', '涨跌幅'], ['consecutive_up_days', '连续上涨'],
  ['period_return_3d', '3D 收益'], ['period_return_5d', '5D 收益'], ['period_return_10d', '10D 收益'],
  ['volume_ratio', 'VR20'], ['breakout_status', '突破状态'], ['volatility_trend_status', '波动率趋势'],
]
function formatted(key: MetricKey, metric: Metric): string {
  if (metric.value === null) return '—'
  if (typeof metric.value === 'boolean') return metric.value ? '已突破' : '未突破'
  if (typeof metric.value === 'string') return metric.value
  if (key === 'change_pct' || key.startsWith('period_return')) return `${(metric.value * 100).toFixed(2)}%`
  return key === 'consecutive_up_days' ? `${metric.value} 天` : metric.value.toFixed(2)
}

export function MomentumCard({ item }: { item: MomentumItem }) {
  return <article aria-label={`${item.symbol} Momentum 示例卡片`} data-symbol={item.symbol}
    className="min-w-0 rounded-card border border-border bg-elevated/50 p-4 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div><h3 className="font-semibold text-foreground">{item.name}</h3>
        <p className="font-mono text-xs text-secondary">{item.symbol} · {item.market}</p></div>
      <span className="rounded bg-accent/10 px-2 py-1 text-[10px] text-accent">合成示例 · 非生产</span>
    </div>
    <div className="mt-3 flex flex-wrap gap-1.5">{item.labels.map(label =>
      <span key={label} className="rounded border border-border px-2 py-0.5 text-[11px] text-secondary">{labelText[label]}</span>)}</div>
    <dl className="mt-3 grid grid-cols-3 gap-2 rounded border border-border bg-base/50 p-2 text-xs">
      <div><dt className="text-muted">Strength Score</dt><dd data-score className="font-mono text-lg text-foreground">{item.strength_score?.toFixed(2) ?? '—'}</dd></div>
      <div><dt className="text-muted">Rank</dt><dd data-rank className="font-mono text-lg text-foreground">{item.rank ?? '—'}</dd></div>
      <div><dt className="text-muted">Tier</dt><dd data-tier className="font-mono text-lg text-foreground">{item.tier ?? '—'}</dd></div>
    </dl>
    {item.strength_score === null && <p className="mt-2 text-[11px] text-warning">评分依赖证据不足，未评分、未排名，不分配 tier。</p>}
    <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-xs">{fields.map(([key, title]) => {
      const metric = item.metrics[key]
      return <div key={key} data-metric={key} className="min-w-0">
        <dt className="text-muted">{title}</dt>
        <dd className="mt-0.5 break-words font-mono text-foreground">{formatted(key, metric)}</dd>
        {metric.status !== 'READY' && <Status value={metric.status} />}
        {metric.reason && <p className="mt-1 text-[10px] leading-relaxed text-warning">{metric.reason}</p>}
      </div>
    })}</dl>
    {item.market === 'HK' && <p className="mt-3 text-[11px] text-muted">主题：暂无可靠数据</p>}
    <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3 text-[11px] text-secondary">
      Data Status <Status value={item.quality.status} /> Evidence Status <Status value={item.evidence.status} />
    </div>
    <details className="mt-2 text-[11px] text-secondary">
      <summary className="cursor-pointer text-accent">证据与缺失原因（合成示例）</summary>
      <dl className="mt-2 space-y-1 break-words">
        <div><dt className="inline text-muted">Source：</dt><dd className="inline">{item.evidence.source}</dd></div>
        <div><dt className="inline text-muted">Generated At (UTC)：</dt><dd className="inline">{item.evidence.generated_at}</dd></div>
        <div><dt className="inline text-muted">Available At (UTC)：</dt><dd className="inline">{item.evidence.available_at ?? '—（历史可得时间未知）'}</dd></div>
        <div><dt className="inline text-muted">Finality：</dt><dd className="inline"><Status value={item.evidence.finality} /></dd></div>
        <div><dt className="inline text-muted">PIT status：</dt><dd className="inline"><Status value={item.evidence.pit_status} /></dd></div>
      </dl>
      {[...item.quality.reasons, ...item.evidence.reasons].map((reason, index) => <p key={index} className="mt-1">{reason}</p>)}
    </details>
  </article>
}

export function MomentumPreview({ view }: { view: MomentumLadderViewModel }) {
  validatePreview(view)
  const ordered = displayOrder(view.items)
  const grouped = new Set(view.groups.flatMap(group => group.symbols))
  const ungrouped = ordered.filter(item => !grouped.has(item.symbol))
  return <div data-momentum-preview={view.market} className="min-h-0 flex-1 overflow-y-auto">
    <PageHeader title={`${view.market === 'HK' ? '港股' : '美股'} Momentum Ladder`}
      titleExtra={<span className="rounded border border-warning/30 bg-warning/10 px-2 py-1 text-xs text-warning">Momentum Preview</span>} />
    <div className="space-y-5 p-4 sm:p-5">
      <aside aria-label="预览数据声明" className="space-y-1 rounded-card border border-warning/30 bg-warning/5 p-3 text-xs leading-relaxed text-warning">
        {view.warnings.map(warning => <p key={warning}>{warning}</p>)}
        <p>READY / PARTIAL / BLOCKED 仅展示合成案例状态，不代表 Longbridge 或生产 Momentum 已就绪。</p>
      </aside>
      <dl aria-label="Momentum 展示契约" className="grid gap-3 rounded-card border border-border bg-elevated/40 p-3 text-xs sm:grid-cols-2 xl:grid-cols-4">
        <div><dt className="text-muted">Market</dt><dd>{view.market}</dd></div>
        <div><dt className="text-muted">Trading Date</dt><dd className="font-mono">{view.trading_date}</dd></div>
        {([['Universe', view.universe], ['Calculation', view.calculation], ['Score Profile', view.profile]] as const).map(([title, identity]) =>
          <div key={title} className="min-w-0"><dt className="text-muted">{title}</dt><dd className="break-words font-mono">{identity.id} / {identity.version}</dd>
            <dd className="mt-1 break-all text-[10px] text-muted">hash: {identity.content_hash ?? '—（仅展示集合，非正式 Universe）'}</dd></div>)}
        <div><dt className="text-muted">Overall Status（预览）</dt><dd><Status value={view.overall_status} /></dd></div>
      </dl>
      {view.market === 'HK' && <p className="text-xs text-muted">T1 = leader；T2 = follower（仅梯队角色，不表示因果跟随）；T3 = qualified momentum。主题独立于角色。</p>}
      <p className="text-xs text-muted">分组可重叠；同一证券可在多个分组出现。按 fixture 已提供的 rank 展示，不在页面计算排名。</p>
      {[...view.groups, ...(ungrouped.length ? [{ id: 'unscored', title: '未评分 / 证据不完整', symbols: ungrouped.map(i => i.symbol) }] : [])].map(group =>
        <section key={group.id} aria-label={group.title}>
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">{group.title}<span className="font-mono text-xs font-normal text-muted">{group.symbols.length}</span></h2>
          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {ordered.filter(item => group.symbols.includes(item.symbol)).map(item => <MomentumCard key={item.symbol} item={item} />)}
          </div>
          {group.symbols.length === 0 && <p className="text-xs text-muted">暂无合成案例；不推断信号。</p>}
        </section>)}
    </div>
  </div>
}

/** Preserve an already visited CN tree (including its date/filter state). Direct HK/US mounts no CN queries. */
export function MomentumLadderPage({ cn }: { cn: (active: boolean) => ReactNode }) {
  const [params, setParams] = useSearchParams()
  const requested = params.get('market')
  const market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const [cnVisited, setCnVisited] = useState(market === 'CN')
  useEffect(() => { if (market === 'CN') setCnVisited(true) }, [market])
  function changeMarket(next: Market) {
    setParams(current => { const nextParams = new URLSearchParams(current); nextParams.set('market', next); return nextParams })
  }
  return <div className="flex h-full min-h-0 flex-col">
    <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']} onChange={changeMarket} />
    {(cnVisited || market === 'CN') && <div hidden={market !== 'CN'} className="min-h-0 flex-1" data-cn-ladder>{cn(market === 'CN')}</div>}
    {market !== 'CN' && <FixturePreview market={market} />}
  </div>
}

function FixturePreview({ market }: { market: MomentumMarket }) {
  const view = loadMomentumPreview(market)
  return <MomentumPreview view={view} />
}
