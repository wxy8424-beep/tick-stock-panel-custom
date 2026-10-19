import { useState, type ReactNode } from 'react'
import { useInRouterContext, useSearchParams } from 'react-router-dom'
import { MarketSwitcherBar } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { PreviewNotice, PreviewDisabledAction } from '@/components/preview/ReadOnlyPreview'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadAnomaliesPreview } from '../../../../tests/fixtures/anomalies_preview'
import { selectAnomaliesMode, unknownKeys, validateAnomaliesPreview, type AnomaliesMarket, type AnomaliesPreviewState, type AnomalySample } from './contract'

const declaration = '演示数据｜非生产行情｜不构成真实异动事件或投资信号'
const columns: ColumnConfig[] = [['name', '合成证券 / 身份'], ['event_time', '固定事件时间 UTC'], ['change_pct', '演示涨跌幅'], ['severity', '演示严重程度']]
  .map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
const card = 'min-w-0 space-y-3 rounded-xl border border-border bg-surface/40 p-4 text-xs break-words'
export function AnomaliesPreview({ market, state, controls }: { market: AnomaliesMarket; state: AnomaliesPreviewState; controls?: ReactNode }) {
  const [search, setSearch] = useState(''), [type, setType] = useState('ALL'), [severity, setSeverity] = useState('ALL'), [selected, setSelected] = useState<string | null>(null)
  const { sort, toggle, sortRows } = useTableSort<AnomalySample>((r, col) => r[col.id as 'name' | 'event_time' | 'change_pct' | 'severity'])
  let data: ReturnType<typeof loadAnomaliesPreview> | null = null
  if (state.kind === 'ready') try { const checked = validateAnomaliesPreview(state.data); if (checked.market === market) data = checked } catch { /* no production fallback */ }
  const rows = sortRows((data?.rows ?? []).filter(r => `${r.name} ${r.symbol} ${r.sample_id}`.toLowerCase().includes(search.trim().toLowerCase())
    && (type === 'ALL' || r.event_type === type) && (severity === 'ALL' || r.severity === severity)), columns)
  const detail = rows.find(r => r.sample_id === selected) ?? rows[0]
  const percent = (r: AnomalySample) => r.change_pct === null ? `— · ${r.missing_reasons.change_pct}` : `${(r.change_pct * 100).toFixed(2)}%（合成）`
  return <div className="min-h-full min-w-0 bg-base" data-anomalies-preview={market}>
    <PageHeader className="pl-14 md:pl-5" title={`${market} 实时异动流 · Preview`} subtitle="Synthetic Data · Read-only · Not production validation" />{controls}
    <div className="space-y-4 p-3 lg:p-5"><PreviewNotice statement={declaration} description="显式离线模式，仅固定合成样稿；不轮询、不查询真实健康状态、不恢复交付、不产生提醒。" />
      {state.kind === 'loading' ? <p role="status">异动样稿加载中…</p> : !data ? <ErrorState title="异动样稿加载失败" hint="无效契约或市场混入；不回退真实事件、健康查询或交付。" /> : <>
        <section className={card} aria-label="异动样稿概览"><p>Preview 交易日：{data.trading_date} · generated_at：{data.generated_at}（固定样稿编写时间）</p>
          <p>source: synthetic-fixture · PREVIEW · data_mode: preview · is_production: false · is_investment_signal: false</p>
          <p>{data.rows.length} 个固定合成样例，不是实际市场事件数量。生产执行：BLOCKED。</p></section>
        <section className="flex flex-wrap gap-3 text-xs" aria-label="筛选异动样稿">
          <input aria-label="搜索异动样稿" placeholder="合成名称 / 代码 / fixture ID" value={search} onChange={e => setSearch(e.target.value)} className="max-w-full rounded-btn border border-border bg-base p-2" />
          <select aria-label="样稿异动类型" value={type} onChange={e => setType(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部类型</option><option>rapid_price_move</option><option>intraday_breakout</option></select>
          <select aria-label="样稿严重程度" value={severity} onChange={e => setSeverity(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部严重程度</option><option>high</option><option>medium</option><option>low</option></select>
        </section>
        {!rows.length ? <EmptyState title="暂无匹配的异动样稿" hint="不表示真实事件为空，不自动请求补齐。" /> : <StockDataTable columns={columns} rows={rows} rowKey={(r: AnomalySample) => r.sample_id} sort={sort} onSortToggle={toggle}
          renderCell={(r: AnomalySample, col) => <td className="p-3 text-xs align-top">{col.id === 'name' ? <button type="button" data-anomaly-sample={r.sample_id} onClick={() => setSelected(r.sample_id)} className="text-left text-accent"><strong className="block">{r.name} · {r.symbol}</strong>{r.sample_id}</button>
            : col.id === 'change_pct' ? percent(r) : r[col.id as 'event_time' | 'severity']}</td>} />}
        <section className={card} aria-label="合成异动详情">{!detail ? <p>暂无选中样稿</p> : <>
          <h2>{detail.sample_id} · {detail.name} · {detail.market}</h2><p>类别：{detail.event_type} · 方向：{detail.direction} · 严重程度：{detail.severity}（均为演示元数据）</p>
          <p>事件状态：{detail.sample_state} · 执行：{detail.execution_status} · 固定事件时间 UTC：{detail.event_time}</p>
          <p>涨跌幅（小数比例 × 100）：{percent(detail)}</p><p>窗口分钟：{detail.condition.window_minutes ?? `— · ${detail.missing_reasons.window_minutes}`}</p><p>{detail.condition.description}</p>
          {unknownKeys.map(key => <p key={key} data-anomaly-missing={key}>{key}: — · {detail.missing_reasons[key]}</p>)}
          <p>source: {detail.source} · evidence: {detail.evidence}</p>{detail.blockers.map(b => <p key={b} className="text-warning">blocker: {b}</p>)}{detail.warnings.map(w => <p key={w}>warning: {w}</p>)}
        </>}</section>
      </>}
      <PreviewDisabledAction label="连接真实交付" reason="Preview 模式不可执行；不查询真实事件、Worker、生产证据或执行路径" />
    </div>
  </div>
}
function ModeError() { return <div className="min-h-full bg-base" data-anomalies-mode="error"><PageHeader className="pl-14 md:pl-5" title="异动流 Preview 参数错误" />
  <div className="p-3"><PreviewNotice statement={declaration} description="显式模式参数错误时不回退真实业务。" /><ErrorState title="无法进入离线 Preview" hint="仅接受唯一 data_mode=preview 与唯一 market=HK 或 market=US；缺失、重复或非法参数均被拒绝。" /></div></div> }
function SelectedMode({ params, live, controls }: { params: URLSearchParams; live: ReactNode; controls?: ReactNode }) {
  const mode = selectAnomaliesMode(params)
  if (mode.kind === 'live') return live
  if (mode.kind === 'error') return <ModeError />
  let state: AnomaliesPreviewState
  try { state = { kind: 'ready', data: loadAnomaliesPreview(mode.market) } } catch { state = { kind: 'error' } }
  return <AnomaliesPreview key={mode.market} market={mode.market} state={state} controls={controls} />
}
function RoutedModes({ live }: { live: ReactNode }) {
  const [params, setParams] = useSearchParams(), mode = selectAnomaliesMode(params)
  const controls = mode.kind === 'preview' ? <MarketSwitcherBar value={mode.market} enabledMarkets={['HK', 'US']} onChange={next => {
    if (next !== 'HK' && next !== 'US') return
    setParams(old => { const copy = new URLSearchParams(old); copy.set('data_mode', 'preview'); copy.set('market', next); return copy })
  }} /> : undefined
  return <SelectedMode params={params} live={live} controls={controls} />
}
export function AnomaliesModes({ live }: { live: ReactNode }) {
  // Preserve existing direct (non-router) consumers; explicit malformed URLs still fail closed.
  const routed = useInRouterContext()
  return routed ? <RoutedModes live={live} /> : <SelectedMode params={new URLSearchParams(window.location.search)} live={live} />
}
