import { useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { LayoutGrid, List, Plus, Search, Trash2 } from 'lucide-react'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import { fmtPrice, fmtPct, fmtBigNum, priceColorClass } from '@/lib/format'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadWatchlistPreview } from '../../../../tests/fixtures/watchlist_preview'
import { validateWatchlistPreview, type WatchlistPreviewMarket, type WatchlistPreviewRow, type WatchlistPreviewState } from './contract'

const columns: ColumnConfig[] = [['symbol', '股票 / 代码'], ['market', '市场'], ['price', '最新价'], ['change_pct', '涨跌幅'],
  ['volume', '成交量（演示）'], ['turnover', '成交额（演示）'], ['watchlisted', '自选状态'], ['status', '数据状态'], ['source', '证据 / 来源']]
  .map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
const readOnly = 'Preview 仅展示，不会添加、删除或修改真实自选'
function sortValue(row: WatchlistPreviewRow, column: ColumnConfig) {
  if (column.id === 'volume' || column.id === 'turnover') return row[column.id].value
  return row[column.id as keyof WatchlistPreviewRow]
}
function Badge() { return <span className="rounded border border-warning/30 bg-warning/10 px-1.5 py-0.5 text-[10px] text-warning">PREVIEW · 演示</span> }
function cell(row: WatchlistPreviewRow, id: string): ReactNode {
  if (id === 'symbol') return <><strong className="block text-xs text-foreground">{row.name}</strong><span className="font-mono text-[11px] text-muted">{row.symbol}</span></>
  if (id === 'price' || id === 'change_pct') return <><span className={`font-mono ${id === 'change_pct' ? priceColorClass(row.change_pct) : ''}`}>
    {id === 'price' ? fmtPrice(row.price) : fmtPct(row.change_pct)}</span>
    {row[id] === null && <p className="mt-1 text-[10px] text-warning">{row.missing_reasons.join('；')}</p>}</>
  if (id === 'volume' || id === 'turnover') { const quantity = row[id]; return <><span className="font-mono">{fmtBigNum(quantity.value)}</span>
    <p className="mt-1 text-[10px] text-muted">{quantity.unit ?? quantity.reason}</p></> }
  if (id === 'watchlisted') return <>{row.watchlisted === null ? '—（自选状态未知）' : row.watchlisted ? '已自选（演示）' : '未自选（演示）'}</>
  if (id === 'status') return <Badge />
  if (id === 'source') return <details className="break-words text-[11px]"><summary className="cursor-pointer text-accent">synthetic-fixture</summary>
    <p>{row.evidence_reference}</p><p>生成时间（UTC）：{row.generated_at}</p><p>可得时间：—（未证明，不以生成时间代替）</p>
    <p>仅为界面证据示例，不认证生产输入。</p>{row.missing_reasons.map(reason => <p key={reason}>{reason}</p>)}</details>
  return row.market
}

export function WatchlistPreview({ market, state, controls }: { market: WatchlistPreviewMarket; state: WatchlistPreviewState; controls?: ReactNode }) {
  const [search, setSearch] = useState('')
  const [view, setView] = useState<'table' | 'card'>('table')
  const { sort, toggle, sortRows } = useTableSort<WatchlistPreviewRow>(sortValue)
  const data = state.kind === 'ready' ? validateWatchlistPreview(state.data) : null
  if (data && data.market !== market) throw new Error('watchlist_preview_market_conflict')
  const rows = sortRows((data?.rows ?? []).filter(row => `${row.symbol} ${row.name}`.toLowerCase().includes(search.trim().toLowerCase())), columns)
  return <div data-watchlist-preview={market} className="flex h-full min-h-0 flex-col">
    <PageHeader title={`${market === 'HK' ? '港股' : '美股'}自选 · Preview`} titleExtra={<Badge />} />
    {controls}
    <div className="min-h-0 flex-1 space-y-4 overflow-auto p-4">
      <aside aria-label="自选演示声明" className="rounded-card border border-warning/30 bg-warning/5 p-3 text-xs leading-relaxed text-warning">
        <p>演示数据｜非生产行情｜不构成投资信号</p><p>仅用于界面验收，不代表用户的真实自选或市场行情。</p>
        <p>交易日：{data?.trading_date ?? '—（未载入演示数据）'} · synthetic-fixture · {market}</p>
        <p>真实港美股生产输入仍未就绪，当前不会请求行情或保存自选变更。</p>
      </aside>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <label className="flex items-center gap-2 rounded-btn border border-border bg-elevated px-2 py-1.5"><Search className="h-3.5 w-3.5 text-muted" />
          <input aria-label="搜索演示自选" value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索演示代码 / 名称" className="w-44 bg-transparent outline-none" /></label>
        <button type="button" onClick={() => setView(v => v === 'table' ? 'card' : 'table')} aria-label={view === 'table' ? '卡片视图' : '列表视图'}
          className="rounded-btn bg-elevated p-2 text-secondary">{view === 'table' ? <LayoutGrid className="h-4 w-4" /> : <List className="h-4 w-4" />}</button>
        <button type="button" disabled title={readOnly} className="inline-flex items-center gap-1 rounded-btn bg-elevated px-2 py-1.5 text-muted disabled:cursor-not-allowed"><Plus className="h-3.5 w-3.5" />添加自选（演示只读）</button>
        <span className="text-muted">{rows.length} 只 · 排序：{columns.find(c => c.id === sort?.key)?.label ?? '示例原顺序'} {sort?.dir === 'asc' ? '↑' : sort?.dir === 'desc' ? '↓' : ''}</span>
      </div>
      {state.kind === 'loading' ? <p role="status" className="text-center text-muted">Preview 加载中…</p>
        : state.kind === 'error' ? <ErrorState title="自选 Preview 加载失败" hint="本地演示数据未载入，不会回退到生产自选或行情。" />
          : rows.length === 0 ? <EmptyState title="暂无匹配的演示自选" hint="只搜索当前市场的固定演示集合，不查询真实市场。" />
            : view === 'table' ? <StockDataTable columns={columns} rows={rows} sort={sort} onSortToggle={toggle} headerSticky
              renderCell={(row: WatchlistPreviewRow, column) => <td data-field={column.id} className="px-3 py-3 align-top text-xs text-secondary">{cell(row, column.id)}</td>}
              extraHeader="操作（只读）" renderExtraCol={() => <td className="px-3 py-3 text-right"><button type="button" disabled title={readOnly} aria-label="删除演示自选（不可用）" className="cursor-not-allowed text-muted"><Trash2 className="h-3.5 w-3.5" /></button></td>} />
              : <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{rows.map(row => <article key={row.symbol} data-preview-symbol={row.symbol} className="min-w-0 rounded-card border border-border bg-surface p-3">
                <div className="mb-3 flex items-center justify-between gap-2">{cell(row, 'symbol')}<Badge /></div>
                <dl className="grid grid-cols-2 gap-3">{columns.filter(c => c.id !== 'symbol').map(column => <div key={column.id} data-field={column.id}>
                  <dt className="text-[11px] text-muted">{column.label}</dt><dd className="mt-1 text-xs text-secondary">{cell(row, column.id)}</dd></div>)}</dl>
              </article>)}</div>}
    </div>
  </div>
}

function FixturePreview({ market, controls }: { market: WatchlistPreviewMarket; controls: ReactNode }) {
  let state: WatchlistPreviewState
  try { state = { kind: 'ready', data: loadWatchlistPreview(market) } } catch { state = { kind: 'error' } }
  return <WatchlistPreview market={market} state={state} controls={controls} />
}

export function WatchlistMarkets({ cn }: { cn: (active: boolean, controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams()
  const requested = params.get('market')
  const market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const [visited, setVisited] = useState<readonly Market[]>([market])
  useEffect(() => { setVisited(previous => previous.includes(market) ? previous : [...previous, market]) }, [market])
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']}
    onChange={next => setParams(current => { const copy = new URLSearchParams(current); copy.set('market', next); return copy })} />
  return <div className="h-full min-h-0">{(['CN', 'HK', 'US'] as const).filter(m => m === market || visited.includes(m)).map(m =>
    <div key={m} hidden={m !== market} data-watchlist-market={m} className="h-full min-h-0">
      {m === 'CN' ? cn(market === 'CN', controls) : <FixturePreview market={m} controls={controls} />}
    </div>)}</div>
}
