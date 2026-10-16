import { useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BookOpenCheck, History } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { MarkdownRenderer } from '@/components/financials/MarkdownRenderer'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import { fmtPct, fmtBigNum, priceColorClass } from '@/lib/format'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadReviewPreview } from '../../../../tests/fixtures/review_preview'
import { validateReviewPreview, type ReviewMarket, type ReviewObservation, type ReviewPreviewState } from './contract'

const columns: ColumnConfig[] = [['symbol', '名称 / 代码'], ['kind', '类型'], ['change_pct', '涨跌幅（演示）'], ['turnover', '成交额（演示）'], ['source', '状态 / 证据']]
  .map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
function sortValue(row: ReviewObservation, col: ColumnConfig) { return row[col.id as keyof ReviewObservation] }
function Badge() { return <span className="rounded border border-warning/30 bg-warning/10 px-2 py-0.5 text-[10px] text-warning">PREVIEW · 合成样稿</span> }

export function ReviewPreview({ market, state, controls }: { market: ReviewMarket; state: ReviewPreviewState; controls?: ReactNode }) {
  const [selected, setSelected] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [kind, setKind] = useState('ALL')
  const [missingOnly, setMissingOnly] = useState(false)
  const { sort, toggle, sortRows } = useTableSort<ReviewObservation>(sortValue)
  const data = state.kind === 'ready' ? validateReviewPreview(state.data) : null
  if (data && data.market !== market) throw new Error('review_preview_market_conflict')
  const report = data?.reports.find(r => r.id === selected) ?? data?.reports[0]
  const rows = sortRows((report?.rows ?? []).filter(row => (kind === 'ALL' || row.kind === kind)
    && (!missingOnly || row.missing_reason !== null) && `${row.symbol} ${row.name}`.toLowerCase().includes(search.trim().toLowerCase())), columns)
  return <div data-review-preview={market} className="flex h-full min-h-0 flex-col">
    <PageHeader title={`${market === 'HK' ? '港股' : '美股'}复盘 · Preview`} titleExtra={<Badge />}
      subtitle={`交易日：${report?.trading_date ?? '—（未载入样稿）'} · 固定演示日期`}
      right={<button disabled title="演示只读，不调用 AI、不归档、不设置定时或推送" className="rounded-btn bg-elevated px-3 py-1.5 text-xs text-muted">生成 / 归档 / 推送不可用</button>} />
    {controls}
    <div className="min-h-0 flex-1 overflow-auto px-4 py-4 sm:px-6">
      <div className="mx-auto max-w-[1280px] space-y-3">
        <aside aria-label="复盘演示声明" className="rounded-card border border-warning/30 bg-warning/5 px-4 py-3 text-xs leading-relaxed text-warning">
          <p>演示数据｜非生产行情｜不构成投资信号</p><p>固定合成复盘样稿，仅用于界面验收，不是 AI 生成，不代表真实市场表现。</p>
          <p>synthetic-fixture · {market} · 非全市场覆盖 · 不读取生产报告或自选数据</p>
        </aside>
        {state.kind === 'loading' ? <p role="status" className="py-8 text-center text-muted">复盘 Preview 加载中…</p>
          : state.kind === 'error' ? <ErrorState title="复盘 Preview 加载失败" hint="本地样稿未载入，不回退到生产报告或行情。" />
            : !report ? <EmptyState icon={BookOpenCheck} title="暂无复盘演示样稿" hint="固定 fixture 为空，不代表真实市场没有复盘。" />
              : <>
                <div className="rounded-card border border-border bg-surface/80 px-4 py-3 text-xs text-secondary">
                  <h2 className="mb-1 font-medium text-foreground">演示摘要</h2><p>{report.summary}</p><p className="mt-1 text-muted">主题 / 催化剂：暂无可靠数据，不根据名称或涨跌推断。</p>
                </div>
                <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_16rem]">
                  <section className="min-w-0 rounded-card border border-border bg-surface/80 p-4">
                    <h2 className="mb-3 text-sm font-semibold">{report.title}</h2><Badge />
                    <MarkdownRenderer content={report.content} />
                    <details className="mt-4 break-words border-t border-border pt-3 text-xs text-secondary">
                      <summary className="cursor-pointer text-accent">来源 / evidence / 缺失原因</summary>
                      <p>source: {report.source} · status: {report.status}</p><p>evidence: {report.id}</p>
                      <p>样稿生成时间（固定演示，UTC）：{report.generated_at}</p><p>available_at：—（历史可得时间未证明）</p>
                      <p>finality：未证明；PIT/vintage：未证明。生产输入仍 BLOCKED。</p>
                    </details>
                  </section>
                  <aside aria-label="历史复盘演示" className="rounded-card border border-border bg-surface/80 p-3">
                    <h2 className="mb-2 flex items-center gap-1 text-xs font-semibold"><History className="h-3.5 w-3.5" />历史样稿（仅 fixture）</h2>
                    {data?.reports.map(r => <button key={r.id} data-report-date={r.trading_date} type="button" aria-pressed={r.id === report.id}
                      onClick={() => setSelected(r.id)} className={`mb-2 w-full rounded-btn border border-border px-3 py-2 text-left text-xs ${r.id === report.id ? 'bg-accent/10 text-accent' : 'text-secondary hover:bg-elevated'}`}>
                      <span className="block font-mono">{r.trading_date}</span><span>{market} · 合成样稿 · 未归档到生产</span>
                    </button>)}
                  </aside>
                </div>
                <section aria-label="演示观察列表" className="min-w-0 space-y-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <input aria-label="搜索复盘演示" placeholder="搜索当前样稿代码 / 名称" value={search} onChange={event => setSearch(event.target.value)} className="rounded-btn border border-border bg-elevated px-3 py-1.5 outline-none" />
                    <select aria-label="复盘演示类型" value={kind} onChange={event => setKind(event.target.value)} className="rounded-btn border border-border bg-elevated px-2 py-1.5">
                      <option value="ALL">全部示例</option><option value="INDEX">指数示例</option><option value="STOCK">股票示例</option></select>
                    <label className="inline-flex items-center gap-1"><input type="checkbox" checked={missingOnly} onChange={event => setMissingOnly(event.target.checked)} />仅缺失字段</label>
                    <span className="text-muted">{rows.length} 条 · 排序：{columns.find(c => c.id === sort?.key)?.label ?? '示例原顺序'} {sort?.dir === 'asc' ? '↑' : sort?.dir === 'desc' ? '↓' : ''}</span>
                  </div>
                  {rows.length === 0 ? <EmptyState title="暂无匹配的复盘示例" hint="仅筛选当前市场及日期的合成集合。" /> : <StockDataTable columns={columns} rows={rows} sort={sort} onSortToggle={toggle}
                    renderCell={(row: ReviewObservation, col) => <td className="px-3 py-3 align-top text-xs text-secondary" data-review-field={col.id}>
                      {col.id === 'symbol' ? <><strong className="block">{row.name}</strong><span className="font-mono text-muted">{row.symbol}</span></>
                        : col.id === 'kind' ? (row.kind === 'INDEX' ? '指数示例' : '股票示例')
                          : col.id === 'change_pct' ? <span className={`font-mono ${priceColorClass(row.change_pct)}`}>{fmtPct(row.change_pct)}</span>
                            : col.id === 'turnover' ? <><span className="font-mono">{fmtBigNum(row.turnover)}</span><p className="text-[10px] text-muted">{row.turnover_unit}</p></>
                              : <><Badge /><p className="mt-1 break-all text-[10px] text-muted">{row.evidence_reference}</p></>}
                      {(col.id === 'change_pct' || col.id === 'turnover') && row.missing_reason && <p className="mt-1 text-[10px] text-warning">{row.missing_reason}</p>}
                    </td>} />}
                </section>
              </>}
      </div>
    </div>
  </div>
}
function FixtureReview({ market, controls }: { market: ReviewMarket; controls: ReactNode }) {
  let state: ReviewPreviewState
  try { state = { kind: 'ready', data: loadReviewPreview(market) } } catch { state = { kind: 'error' } }
  return <ReviewPreview market={market} state={state} controls={controls} />
}
export function ReviewMarkets({ cn }: { cn: (active: boolean, controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams()
  const requested = params.get('market')
  const market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const [visited, setVisited] = useState<readonly Market[]>([market])
  useEffect(() => { setVisited(previous => previous.includes(market) ? previous : [...previous, market]) }, [market])
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']}
    onChange={next => setParams(current => { const copy = new URLSearchParams(current); copy.set('market', next); return copy })} />
  return <div className="h-full min-h-0">{(['CN', 'HK', 'US'] as const).filter(m => visited.includes(m) || m === market).map(m =>
    <div key={m} hidden={market !== m} data-review-market={m} className="h-full min-h-0">
      {m === 'CN' ? cn(market === 'CN', controls) : <FixtureReview market={m} controls={controls} />}
    </div>)}</div>
}
