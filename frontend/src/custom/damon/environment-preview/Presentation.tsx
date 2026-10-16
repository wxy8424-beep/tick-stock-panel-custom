import { useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Activity } from 'lucide-react'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import { fmtPct, priceColorClass } from '@/lib/format'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadEnvironmentPreview } from '../../../../tests/fixtures/environment_preview'
import { environmentMetricLabels, validateEnvironmentPreview, type EnvironmentIndex, type EnvironmentMarket, type EnvironmentPreviewState, type EnvironmentValue } from './contract'

const card = 'rounded-card border border-border bg-surface/80 p-4 shadow-sm'
const columns: ColumnConfig[] = [['symbol', '名称 / 代码'], ['latest_value', '样稿点位'], ['change_pct', '涨跌幅（演示）'], ['trend', '趋势（演示）'], ['source', '状态 / 证据']]
  .map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
function sortValue(row: EnvironmentIndex, col: ColumnConfig) {
  if (col.id === 'latest_value' || col.id === 'change_pct') return row[col.id].value
  return row[col.id as 'symbol' | 'trend' | 'source']
}
function Badge() { return <span className="rounded border border-warning/30 bg-warning/10 px-2 py-0.5 text-[10px] text-warning">PREVIEW · 合成数据</span> }
function Metric({ label, data }: { label: string; data: EnvironmentValue }) {
  return <div className="min-w-0 rounded-btn border border-border bg-elevated/30 p-3">
    <p className="text-xs text-muted">{label}（演示）</p><p className="my-1 font-mono text-lg">{data.value ?? '—'}</p>
    {data.reason && <p className="text-xs text-warning">{data.reason}</p>}
  </div>
}
export function EnvironmentPreview({ market, state, controls }: { market: EnvironmentMarket; state: EnvironmentPreviewState; controls?: ReactNode }) {
  const [date, setDate] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [missingOnly, setMissingOnly] = useState(false)
  const { sort, toggle, sortRows } = useTableSort<EnvironmentIndex>(sortValue)
  const data = state.kind === 'ready' ? validateEnvironmentPreview(state.data) : null
  if (data && data.market !== market) throw new Error('environment_preview_market_conflict')
  const day = data?.days.find(d => d.trading_date === date) ?? data?.days[0]
  const rows = sortRows((day?.indices ?? []).filter(i => `${i.name} ${i.symbol}`.toLowerCase().includes(search.trim().toLowerCase())
    && (!missingOnly || i.latest_value.value === null || i.change_pct.value === null || i.trend === 'UNAVAILABLE')), columns)
  return <div data-environment-preview={market} className="mx-auto max-w-[1440px] space-y-4 px-4 py-5">
    <PageHeader title={`${market === 'HK' ? '港股' : '美股'}市场环境 · Preview`} titleExtra={<Badge />}
      subtitle="固定合成样稿 · 非生产市场统计" right={<button disabled className="rounded-btn bg-elevated px-3 py-1.5 text-xs text-muted" title="Preview 不调用计算、同步或生产接口">生产重算不可用</button>} />
    {controls}
    <aside aria-label="市场环境演示声明" className="rounded-card border border-warning/30 bg-warning/5 p-4 text-xs leading-relaxed text-warning">
      <p>演示数据｜非生产行情｜不构成投资信号</p><p>仅用于界面验收，不代表真实行情。HK/US 独立样稿，不是全市场统计、真实 Universe 或 Momentum 结果。</p>
      <p>日期和 Session 均为固定演示状态，不跟随当前时间，不证明供应商 completed bar / finality。</p>
    </aside>
    {state.kind === 'loading' ? <p role="status" className="py-8 text-center text-muted">市场环境 Preview 加载中…</p>
      : state.kind === 'error' ? <ErrorState title="市场环境 Preview 加载失败" hint="本地 fixture 不可用，不回退生产接口。" />
        : !day ? <EmptyState icon={Activity} title="暂无市场环境演示数据" hint="fixture 为空，不表示真实市场无数据。" />
          : <>
            <section aria-label="市场总体状态" className={card}>
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-sm font-semibold">{market} · {market === 'HK' ? '港股' : '美股'}市场总体状态</h2><Badge />
                <label className="ml-auto flex items-center gap-2 text-xs">交易日：
                  <select aria-label="市场环境演示日期" value={day.trading_date} onChange={e => setDate(e.target.value)} className="rounded-btn border border-border bg-elevated px-2 py-1">
                    {data?.days.map(d => <option key={d.trading_date} value={d.trading_date}>{d.trading_date}</option>)}
                  </select></label>
              </div>
              <p className="mt-2 text-xs text-secondary">Session：{day.session}（固定演示） · 市场状态：{day.market_state}（演示） · 数据状态：{day.status}</p>
              <p className="mt-1 break-all text-xs text-muted">source: {day.source} · evidence: {day.evidence}</p>
            </section>
            <section aria-label="指数环境" className={`${card} min-w-0 space-y-3`}>
              <h2 className="text-sm font-semibold">指数环境 · 合成样稿</h2>
              <div className="flex flex-wrap items-center gap-3 text-xs">
                <input aria-label="搜索环境指数" value={search} placeholder="名称 / 代码" onChange={e => setSearch(e.target.value)} className="rounded-btn border border-border bg-elevated px-3 py-1.5" />
                <label className="flex items-center gap-1"><input type="checkbox" checked={missingOnly} onChange={e => setMissingOnly(e.target.checked)} />仅缺失字段</label>
                <span className="text-muted">排序：{columns.find(c => c.id === sort?.key)?.label ?? '样稿顺序'} {sort?.dir === 'asc' ? '↑' : sort?.dir === 'desc' ? '↓' : ''}</span>
              </div>
              {!rows.length ? <EmptyState title="暂无匹配的环境指数" hint="仅筛选当前市场、当前演示日期。" /> : <StockDataTable columns={columns} rows={rows} sort={sort} onSortToggle={toggle}
                renderCell={(row: EnvironmentIndex, col) => <td data-environment-field={col.id} className="px-3 py-3 align-top text-xs text-secondary">
                  {col.id === 'symbol' ? <><strong className="block">{row.name}</strong><span className="font-mono text-muted">{row.symbol}</span></>
                    : col.id === 'latest_value' ? <><span className="font-mono">{row.latest_value.value === null ? '—' : row.latest_value.value.toFixed(2)}</span><p className="text-warning">{row.latest_value.reason}</p></>
                      : col.id === 'change_pct' ? <><span className={`font-mono ${priceColorClass(row.change_pct.value)}`}>{fmtPct(row.change_pct.value)}</span><p className="text-warning">{row.change_pct.reason}</p></>
                        : col.id === 'trend' ? <>{row.trend}（演示）<p className="text-warning">{row.trend_reason}</p></>
                          : <><Badge /><p className="mt-1">{row.source}</p><p className="break-all text-[10px] text-muted">{row.evidence}</p></>}
                </td>} />}
            </section>
            <div className="grid gap-4 lg:grid-cols-2">
              <section aria-label="市场宽度" className={card}><h2 className="mb-3 text-sm font-semibold">市场宽度 · Preview fixture 统计</h2>
                <p className="mb-3 text-xs text-muted">宽度状态：{day.breadth_status}（预编写演示标签，非市场计算）</p>
                <div className="grid grid-cols-2 gap-2">{(['up', 'down', 'flat', 'up_down_ratio'] as const).map(key => <Metric key={key} label={environmentMetricLabels[key]} data={day.metrics[key]} />)}</div>
              </section>
              <section aria-label="强弱环境" className={card}><h2 className="mb-3 text-sm font-semibold">强弱环境 · Preview fixture 统计</h2>
                <p className="mb-3 text-xs text-muted">强弱 / 突破为固定样稿值，不定义或运行生产阈值。</p>
                <div className="grid grid-cols-2 gap-2">{(['strong', 'weak', 'strong_weak_ratio', 'breakout', 'volume_spike'] as const).map(key => <Metric key={key} label={environmentMetricLabels[key]} data={day.metrics[key]} />)}</div>
              </section>
            </div>
            <section aria-label="市场环境结论" className={card}><h2 className="text-sm font-semibold">环境结论（演示标签）</h2>
              <p className="my-2 font-mono text-xl">{day.conclusion}</p>{day.conclusion_reason && <p className="text-xs text-warning">{day.conclusion_reason}</p>}
              <p className="text-xs text-muted">固定展示状态，不是生产结论，不通过 A 股环境评分或 Momentum Score 推导，不提供投资信号。</p>
            </section>
            <section aria-label="市场环境数据质量" className={`${card} space-y-2 break-words text-xs text-secondary`}>
              <h2 className="text-sm font-semibold">数据质量 / evidence</h2>
              <p>source: {day.source} · data_status: {day.status} · data_mode: {day.data_mode}</p>
              <p>trading_date: {day.trading_date} · generated_at: {day.generated_at}（固定样稿时间，UTC）</p>
              <p>available_at: —（历史可得时间未证明） · is_production: false · is_investment_signal: false</p>
              <p className="break-all">evidence: {day.evidence}</p>
              <p>missing_fields: {day.missing_fields.length ? day.missing_fields.join('、') : '无（仅该样稿）'}</p>
              <ul className="space-y-1 text-warning">{day.blockers.map(reason => <li key={reason}>blocker: {reason}</li>)}</ul>
              <ul className="space-y-1 text-muted">{day.warnings.map(reason => <li key={reason}>warning: {reason}</li>)}</ul>
            </section>
          </>}
  </div>
}
function FixtureEnvironment({ market, controls }: { market: EnvironmentMarket; controls: ReactNode }) {
  let state: EnvironmentPreviewState
  try { state = { kind: 'ready', data: loadEnvironmentPreview(market) } } catch { state = { kind: 'error' } }
  return <EnvironmentPreview market={market} state={state} controls={controls} />
}
export function EnvironmentMarkets({ cn }: { cn: (active: boolean, controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams()
  const requested = params.get('market')
  const market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const [visited, setVisited] = useState<readonly Market[]>([market])
  useEffect(() => { setVisited(previous => previous.includes(market) ? previous : [...previous, market]) }, [market])
  const controls = <MarketSwitcherBar className="rounded-card border px-4" value={market} enabledMarkets={['CN', 'HK', 'US']}
    onChange={next => setParams(current => { const copy = new URLSearchParams(current); copy.set('market', next); return copy })} />
  return <div className="h-full min-h-0">{(['CN', 'HK', 'US'] as const).filter(m => visited.includes(m) || m === market).map(m =>
    <div key={m} hidden={market !== m} data-environment-market={m} className="h-full min-h-0">
      {m === 'CN' ? cn(market === 'CN', controls) : <FixtureEnvironment market={m} controls={controls} />}
    </div>)}</div>
}
