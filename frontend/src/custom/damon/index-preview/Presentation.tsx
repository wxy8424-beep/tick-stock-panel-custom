import { useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Activity } from 'lucide-react'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { loadIndexPreview } from '../../../../tests/fixtures/index_preview'
import { sortIndexPreview, validateIndexPreview, type IndexPreviewMarket, type IndexPreviewRow, type IndexPreviewState } from './contract'

const number = (value: number | null) => value === null ? '—' : value.toFixed(2)
const color = (value: number | null) => value === null ? 'text-muted' : value > 0 ? 'text-bull' : value < 0 ? 'text-bear' : 'text-secondary'
function Badge() {
  return <span className="rounded border border-warning/30 bg-warning/10 px-2 py-0.5 text-[10px] font-medium text-warning">PREVIEW · 合成数据</span>
}

export function IndexPreview({ market, state, controls }: { market: IndexPreviewMarket; state: IndexPreviewState; controls?: ReactNode }) {
  const [direction, setDirection] = useState<'asc' | 'desc'>('desc')
  const [selected, setSelected] = useState<string | null>(null)
  const data = state.kind === 'ready' ? validateIndexPreview(state.data) : null
  if (data && data.market !== market) throw new Error('preview_market_conflict')
  const rows = sortIndexPreview(data?.rows ?? [], direction)
  const current = rows.find(row => row.symbol === selected) ?? rows[0]
  return <div className="h-full overflow-auto bg-base p-4" data-index-preview={market}>
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div><h1 className="text-lg font-semibold text-foreground">{market === 'HK' ? '港股' : '美股'}指数 · {market} · Preview</h1>
        <p className="mt-1 text-xs text-muted">Preview · 合成数据 · 非生产行情 · 不构成投资信号</p></div>
      <Badge />
    </div>
    {controls}
    <aside aria-label="指数预览声明" className="mb-4 rounded-card border border-warning/30 bg-warning/5 p-3 text-xs leading-relaxed text-warning">
      <p>仅用于界面验收，不代表真实行情。固定展示值不是指数收盘数据，也不是盘中报价。</p>
      <p>来源：synthetic-fixture · Preview 数据 · 交易日：{data?.trading_date ?? '—（未载入 fixture）'}</p>
      <p>当前仅提供界面预览，尚未接入真实港美股指数行情。</p>
    </aside>
    {state.kind === 'loading' ? <p role="status" className="py-10 text-center text-sm text-muted">Preview 加载中…</p>
      : state.kind === 'error' ? <ErrorState title="指数 Preview 加载失败" hint="未能读取本地合成 fixture；不会回退到生产数据源。" />
        : rows.length === 0 ? <EmptyState icon={Activity} title="暂无指数 Preview 数据" hint="本地合成 fixture 为空，不代表市场无行情。" />
          : <div className="grid gap-4 md:grid-cols-[15rem_1fr]">
            <aside className="rounded-card border border-border bg-surface p-3">
              <div className="mb-2 flex items-center justify-between gap-2 px-1">
                <span className="text-[11px] uppercase tracking-wider text-muted">主要指数</span>
                <button type="button" aria-label="切换涨跌幅排序" onClick={() => setDirection(d => d === 'desc' ? 'asc' : 'desc')}
                  className="rounded-btn border border-border px-2 py-1 text-[11px] text-secondary hover:bg-elevated">涨跌幅 {direction === 'desc' ? '↓' : '↑'}</button>
              </div>
              <div className="space-y-1" aria-label="Preview 指数列表">{rows.map(row =>
                <button key={row.symbol} type="button" data-preview-index={row.symbol} aria-pressed={current?.symbol === row.symbol}
                  onClick={() => setSelected(row.symbol)} className={`w-full rounded-btn px-2 py-2 text-left transition-colors ${current?.symbol === row.symbol ? 'bg-accent/15 text-foreground' : 'text-secondary hover:bg-elevated'}`}>
                  <div className="flex items-center justify-between gap-2"><span className="min-w-0 truncate text-xs font-medium" title={row.name}>{row.name}</span>
                    <span className={`shrink-0 font-mono text-[10px] ${color(row.change_pct)}`}>{row.change_pct === null ? '—' : `${number(row.change_pct)}%`}</span></div>
                  <div className="mt-0.5 flex items-center justify-between font-mono text-[10px] text-muted"><span>{row.symbol}</span><span>{number(row.latest_value)}</span></div>
                  <span className="text-[9px] text-warning">PREVIEW · 非生产</span>
                </button>)}</div>
            </aside>
            {current && <IndexPreviewCard row={current} />}
          </div>}
  </div>
}

function IndexPreviewCard({ row }: { row: IndexPreviewRow }) {
  const fields: [string, number | null][] = [['最新值', row.latest_value], ['涨跌', row.change], ['涨跌幅', row.change_pct],
    ['开盘', row.open], ['最高', row.high], ['最低', row.low], ['昨收', row.prev_close], ['成交额（fixture）', row.turnover]]
  return <main data-selected-preview={row.symbol} className="min-w-0 rounded-card border border-border bg-surface p-3">
    <div className="mb-4 flex flex-wrap items-center gap-2"><Activity className="h-4 w-4 text-accent" />
      <h2 className="text-sm font-semibold text-foreground">{row.name}</h2><span className="font-mono text-xs text-muted">{row.symbol}</span><Badge /></div>
    <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">{fields.map(([name, value]) => <div key={name} data-preview-field={name}>
      <dt className="text-xs text-muted">{name}</dt><dd className={`mt-1 break-all font-mono text-lg ${name === '涨跌' || name === '涨跌幅' ? color(value) : 'text-foreground'}`}>
        {number(value)}{value !== null && name === '涨跌幅' ? '%' : ''}{value !== null && name === '成交额（fixture）' ? ` ${row.turnover_currency}` : ''}</dd>
      {value === null && <p className="mt-1 text-[11px] text-warning">{row.missing_reason}</p>}
    </div>)}</dl>
    <dl className="mt-5 space-y-1 border-t border-border pt-3 text-xs text-secondary">
      <div><dt className="inline text-muted">状态：</dt><dd className="inline">{row.status}</dd></div>
      <div><dt className="inline text-muted">来源：</dt><dd className="inline">{row.source}</dd></div>
      <div><dt className="inline text-muted">模式：</dt><dd className="inline">{row.data_mode} · 非生产行情 · 不构成投资信号</dd></div>
      <div><dt className="inline text-muted">交易日：</dt><dd className="inline">{row.trading_date} · Preview 数据</dd></div>
    </dl>
  </main>
}

function FixtureIndexPreview({ market, controls }: { market: IndexPreviewMarket; controls: ReactNode }) {
  let state: IndexPreviewState
  try { state = { kind: 'ready', data: loadIndexPreview(market) } } catch { state = { kind: 'error' } }
  return <IndexPreview market={market} state={state} controls={controls} />
}

/** URL is the market authority; visited panels retain only their own UI state. */
export function IndexMarkets({ cn }: { cn: (controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams()
  const value = params.get('market')
  const market: Market = value === 'HK' || value === 'US' ? value : 'CN'
  const [visited, setVisited] = useState<readonly Market[]>([market])
  useEffect(() => { setVisited(previous => previous.includes(market) ? previous : [...previous, market]) }, [market])
  const controls = <MarketSwitcherBar className="mb-4 rounded-card border px-3" value={market} enabledMarkets={['CN', 'HK', 'US']}
    onChange={next => setParams(current => { const copy = new URLSearchParams(current); copy.set('market', next); return copy })} />
  return <div className="h-full min-h-0">{(['CN', 'HK', 'US'] as const).filter(m => visited.includes(m) || m === market).map(m =>
    <div key={m} hidden={market !== m} data-index-market={m} className="h-full min-h-0">
      {m === 'CN' ? cn(controls) : <FixtureIndexPreview market={m} controls={controls} />}
    </div>)}</div>
}
