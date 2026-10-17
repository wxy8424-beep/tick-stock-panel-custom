import { useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import { fmtPct } from '@/lib/format'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadPaperPreview } from '../../../../tests/fixtures/paper_preview'
import { validatePaperPreview, type PaperOrderSample, type PaperPreviewMarket, type PaperPreviewState } from './contract'

const card = 'rounded-xl border border-border bg-surface/40 p-4 text-xs space-y-2'
const money = (v: number | null) => v === null ? '—' : v.toFixed(2)
const statusLabels = { pending: '待成交样例', filled: '已成交样例', cancelled: '已撤单样例', expired: '已过期样例' }
const columns: ColumnConfig[] = [['symbol', '证券'], ['side', '方向'], ['order_type', '类型'], ['qty', '数量'], ['ref_price', '委托参考价'], ['sample_status', '演示订单状态'], ['submitted_at', '固定提交时间']].map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
function Disabled({ children }: { children: ReactNode }) { return <button disabled title="Preview 模式不可执行：不修改账户、订单或成交" className="rounded-btn border border-border px-3 py-1 text-muted">{children}（Preview 不可执行）</button> }
export function PaperPreview({ market, state, controls }: { market: PaperPreviewMarket; state: PaperPreviewState; controls?: ReactNode }) {
  const [search, setSearch] = useState(''), [filter, setFilter] = useState('ALL'), [selected, setSelected] = useState<string | null>(null)
  const { sort, toggle, sortRows } = useTableSort<PaperOrderSample>((row, col) => row[col.id as keyof PaperOrderSample] as string | number | null)
  const data = state.kind === 'ready' ? validatePaperPreview(state.data) : null
  if (data && data.market !== market) throw new Error('paper_preview_market_conflict')
  const matches = (symbol: string) => `${symbol} ${data?.positions.find(p => p.symbol === symbol)?.name ?? ''}`.toLowerCase().includes(search.trim().toLowerCase())
  const orders = sortRows((data?.orders ?? []).filter(o => matches(o.symbol) && (filter === 'ALL' || o.sample_status === filter)), columns)
  const detail = orders.find(o => o.sample_id === selected) ?? orders[0]
  return <div className="flex min-h-0 flex-col" data-paper-preview={market}>
    <PageHeader title={`${market} 模拟盘 · Preview`} subtitle={`固定演示交易日：${data?.trading_date ?? '—'}`} right={<Disabled>创建账户</Disabled>} />{controls}
    <div className="mx-auto w-full max-w-[1440px] space-y-4 p-5">
      <aside aria-label="模拟账户演示声明" className="rounded-xl border border-warning/30 bg-warning/5 p-4 text-xs text-warning space-y-2"><p>演示账户｜合成订单与成交｜非真实交易记录｜不构成投资建议</p><p>PREVIEW · 合成数据 · 非生产行情。只读固定样稿，不连接券商、CN 账户或订单执行器。</p></aside>
      {state.kind === 'loading' ? <p role="status">模拟盘 Preview 加载中…</p> : state.kind === 'error' ? <ErrorState title="模拟盘 Preview 加载失败" hint="不回退真实账户或交易接口。" /> : data && <>
        <section aria-label="演示账户概览" className={card}><h2 className="text-sm font-semibold">{data.account_sample_id} · {market} · {data.currency}（演示币种）</h2>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{([['initial_cash', '初始演示资金'], ['cash', '可用现金'], ['market_value', '持仓市值'], ['total_assets', '总资产'], ['realized_pnl_gross', '已实现盈亏（未扣费用）'], ['unrealized_pnl_gross', '未实现盈亏（未扣费用）'], ['fees', '费用（单列扣除一次）'], ['total_pnl_net', '累计净盈亏']] as const).map(([k, label]) => <div key={k} data-paper-value={k} className="rounded-btn bg-elevated/30 p-3"><p className="text-muted">{label}</p><p className="font-mono text-lg">{money(data[k])} {data.currency}</p></div>)}</div>
          <p>累计净收益率：{fmtPct(data.return_pct)} · 合成持仓 {data.positions.length} 项</p><p>成本口径：买入成交价，不含费用；总资产 = 现金 + 持仓市值；累计净盈亏 = 已实现 + 未实现 - 费用。无外部出入金。</p>
          <p>已实现盈亏为 0：样稿无卖出成交，不从未成交订单推导盈亏。</p><div className="flex flex-wrap gap-2"><Disabled>买入</Disabled><Disabled>卖出</Disabled><Disabled>清仓</Disabled><Disabled>重置账户</Disabled></div>
        </section>
        <section aria-label="演示记录筛选" className="flex flex-wrap items-center gap-3 text-xs"><input aria-label="搜索模拟样稿" placeholder="证券代码 / 持仓名称" value={search} onChange={e => setSearch(e.target.value)} className="rounded-btn border border-border bg-base p-2" /><select aria-label="演示订单状态" value={filter} onChange={e => setFilter(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部订单样稿</option>{Object.entries(statusLabels).map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select><span>状态仅筛选订单；证券搜索同时筛选持仓、订单、成交。</span></section>
        <section aria-label="合成持仓" className={card}><h2 className="text-sm font-semibold">合成持仓（非券商持仓）</h2>{!data.positions.filter(p => matches(p.symbol)).length ? <EmptyState title="暂无匹配的持仓样本" /> : <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr>{['证券 / 市场', '数量', '可卖数量', '成本价（未含费用）', '固定参考价', '市值', '未实现盈亏', '收益率', '来源 / evidence'].map(t => <th key={t} className="p-2">{t}</th>)}</tr></thead><tbody>{data.positions.filter(p => matches(p.symbol)).map(p => <tr key={p.sample_id}><td className="p-2">{p.name} · {p.symbol} · {p.market}</td><td>{p.qty}</td><td>—<p className="text-warning">{p.reason}</p></td><td>{money(p.cost_price)}</td><td>{money(p.reference_price)}</td><td>{money(p.market_value)}</td><td>{money(p.unrealized_pnl)}</td><td>{fmtPct(p.return_pct)}</td><td className="break-all">{p.source} · {p.status}<p>{p.evidence}</p></td></tr>)}</tbody></table></div>}</section>
        <section aria-label="合成订单" className={card}><h2 className="text-sm font-semibold">合成订单 · 点击证券查看详情</h2>{!orders.length ? <EmptyState title="暂无匹配的订单样本" /> : <StockDataTable columns={columns} rows={orders} rowKey={(o: PaperOrderSample) => o.sample_id} sort={sort} onSortToggle={toggle} renderCell={(o: PaperOrderSample, c) => <td className="p-3">{c.id === 'symbol' ? <button data-paper-order={o.sample_id} onClick={() => setSelected(o.sample_id)} className="text-accent">{o.symbol}</button> : c.id === 'sample_status' ? statusLabels[o.sample_status] : c.id === 'side' ? o.side === 'buy' ? '买入样例' : '卖出样例' : c.id === 'order_type' ? ({ market: '即时样例', close: '收盘样例', next_open: '下次开盘样例' })[o.order_type] : c.id === 'ref_price' ? <>{money(o.ref_price)}{o.reason && <p className="text-warning">{o.reason}</p>}</> : String(o[c.id as keyof PaperOrderSample])}</td>} />}</section>
        <section aria-label="订单样本详情" className={card}><h2 className="text-sm font-semibold">只读订单详情</h2>{detail ? <><p>{detail.sample_id} · {detail.symbol} · {statusLabels[detail.sample_status]}</p><p>固定提交时间 UTC：{detail.submitted_at} · 委托参考价：{money(detail.ref_price)}</p><p>source: {detail.source} · evidence: {detail.evidence}</p>{detail.reason && <p className="text-warning">{detail.reason}</p>}<p>关联成交样本数：{data.fills.filter(f => f.order_sample_id === detail.sample_id).length}；提交时间、委托参考价不是成交证据。</p><Disabled>撤单</Disabled></> : <p>暂无选中的订单样本</p>}</section>
        <section aria-label="合成成交" className={card}><h2 className="text-sm font-semibold">合成成交台账 · 非真实交易记录</h2>{!data.fills.filter(f => matches(f.symbol)).length ? <EmptyState title="暂无匹配的成交样本" /> : data.fills.filter(f => matches(f.symbol)).map(f => <article key={f.sample_id} className="rounded-lg border border-border p-3"><p>{f.sample_id} · 订单 {f.order_sample_id} · {f.symbol} · {f.side === 'buy' ? '买入样例' : '卖出样例'}</p><p>成交数量：{f.qty} · 成交价：{money(f.price)} · 费用：{money(f.fee)} {data.currency}</p><p>固定成交时间 UTC：{f.filled_at}</p><p className="break-all">source: {f.source} · {f.status} · evidence: {f.evidence}</p></article>)}</section>
        <section aria-label="演示资产历史" className={card}><h2 className="text-sm font-semibold">固定资产历史样稿（非回测、非真实交易业绩）</h2><div className="overflow-x-auto"><table className="w-full text-left"><thead><tr>{['日期', '现金', '持仓市值', '总资产', '相对初始资金净收益率'].map(t => <th key={t}>{t}</th>)}</tr></thead><tbody>{data.history.map(h => <tr key={h.date}><td>{h.date}</td><td>{money(h.cash)}</td><td>{money(h.market_value)}</td><td>{money(h.total_assets)}</td><td>{fmtPct(h.return_pct)}</td></tr>)}</tbody></table></div><p>胜率：—（无已平仓回合，缺少胜率输入）</p></section>
        <section aria-label="演示数据质量" className={card}><p>source: {data.source} · PREVIEW · data_mode: preview · is_production: false · is_investment_signal: false</p><p>trading_date: {data.trading_date} · generated_at: {data.generated_at}（固定样稿时间）</p><p>missing_fields: {data.missing_fields.join('、')}</p>{data.reasons.map(r => <p key={r} className="text-warning">{r}</p>)}{data.blockers.map(r => <p key={r} className="text-warning">blocker: {r}</p>)}{data.warnings.map(r => <p key={r} className="text-muted">warning: {r}</p>)}</section>
      </>}
    </div>
  </div>
}
function FixturePaper({ market, controls }: { market: PaperPreviewMarket; controls: ReactNode }) {
  let state: PaperPreviewState
  try { state = { kind: 'ready', data: loadPaperPreview(market) } } catch { state = { kind: 'error' } }
  return <PaperPreview market={market} state={state} controls={controls} />
}
export function PaperMarkets({ cn }: { cn: (controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams(), requested = params.get('market')
  const market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const [visited, setVisited] = useState<readonly PaperPreviewMarket[]>(market === 'CN' ? [] : [market])
  useEffect(() => { if (market !== 'CN') setVisited(old => old.includes(market) ? old : [...old, market]) }, [market])
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']} onChange={next => setParams(old => { const copy = new URLSearchParams(old); copy.set('market', next); return copy })} />
  return <div className="h-full min-h-0">{market === 'CN' && <div data-paper-market="CN" className="flex h-full min-h-0 flex-col">{cn(controls)}</div>}{(['HK', 'US'] as const).filter(m => visited.includes(m) || m === market).map(m => <div key={m} hidden={market !== m} data-paper-market={m} className="h-full min-h-0"><FixturePaper market={m} controls={controls} /></div>)}</div>
}
