import { useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadSignalPreview } from '../../../../tests/fixtures/signal_preview'
import { validateSignalPreview, type SignalMarket, type SignalPreviewState, type SignalSample } from './contract'

const declaration = '演示信号定义｜合成数据｜非生产配置｜不评估条件、不产生真实信号｜不构成投资建议'
const qualities = ['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED'] as const
const directions = { entry: '入场', exit: '出场', both: '出入通用' }
const columns: ColumnConfig[] = [['name', '合成定义名称 / 标识'], ['direction', '方向'], ['timeframe', '时间框架'], ['definition_status', '定义质量']]
  .map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
const card = 'min-w-0 rounded-xl border border-border bg-surface/40 p-4 text-xs space-y-3'
export function SignalPreview({ market, state, controls }: { market: SignalMarket; state: SignalPreviewState; controls?: ReactNode }) {
  const [search, setSearch] = useState(''), [direction, setDirection] = useState('ALL'), [timeframe, setTimeframe] = useState('ALL')
  const [quality, setQuality] = useState('ALL'), [selected, setSelected] = useState<string | null>(null)
  const { sort, toggle, sortRows } = useTableSort<SignalSample>((r, c) => r[c.id as 'name' | 'direction' | 'timeframe' | 'definition_status'])
  let data: ReturnType<typeof loadSignalPreview> | null = null
  if (state.kind === 'ready') {
    try { const checked = validateSignalPreview(state.data); if (checked.market === market) data = checked } catch { /* Fail closed; no production fallback. */ }
  }
  const rows = sortRows((data?.rows ?? []).filter(r => `${r.name} ${r.id}`.toLowerCase().includes(search.trim().toLowerCase())
    && (direction === 'ALL' || r.direction === direction) && (timeframe === 'ALL' || r.timeframe === timeframe)
    && (quality === 'ALL' || r.definition_status === quality)), columns)
  const detail = rows.find(r => r.id === selected) ?? rows[0]
  return <div className="min-h-full bg-base">
    <PageHeader className="pl-14 md:pl-5" title={`${market} 信号定义 · Preview`} subtitle="仅结构化合成元数据 · 不是执行中的信号库" />
    {controls}
    <div className="space-y-4 p-3 lg:p-5">
      <div role="note" className="rounded-xl border border-warning/30 bg-warning/5 p-4 text-sm text-warning"><strong>{declaration}</strong><p>仅用于界面验收，不是实际信号定义、触发记录或生产能力证明。</p></div>
      {state.kind === 'loading' ? <p role="status">信号样稿加载中…</p> : !data ? <ErrorState title="信号样稿加载失败" hint="拒绝错误市场或无效契约；不回退生产信号或字段选项。" /> : <>
        <section className={card} aria-label="信号样稿概览">
          <p>交易日：{data.trading_date} · generated_at：{data.generated_at}（固定编写时间，非触发时间）</p>
          <p>source: synthetic-fixture · PREVIEW · data_mode: preview · is_production: false · is_investment_signal: false</p>
          <p>{data.rows.length} 项固定样稿，不是市场覆盖数或真实启用数。生产执行：BLOCKED</p>
        </section>
        <section aria-label="筛选信号样稿" className="flex flex-wrap gap-3 text-xs">
          <input aria-label="搜索信号样稿" value={search} onChange={e => setSearch(e.target.value)} placeholder="名称 / fixture ID" className="max-w-full rounded-btn border border-border bg-base p-2" />
          <select aria-label="样稿方向" value={direction} onChange={e => setDirection(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部方向</option>{Object.entries(directions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
          <select aria-label="样稿时间框架" value={timeframe} onChange={e => setTimeframe(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部时间框架</option><option value="daily">daily</option><option value="intraday">intraday</option></select>
          <select aria-label="样稿定义质量" value={quality} onChange={e => setQuality(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部定义质量</option>{qualities.map(q => <option key={q}>{q}</option>)}</select>
        </section>
        {!rows.length ? <EmptyState title="暂无匹配的信号样稿" hint="不表示真实信号库为空，不自动下载、创建或评估。" /> : <StockDataTable columns={columns} rows={rows} rowKey={(r: SignalSample) => r.id} sort={sort} onSortToggle={toggle}
          renderCell={(r: SignalSample, col) => <td className="p-3 text-xs align-top">{col.id === 'name' ? <button data-signal-id={r.id} onClick={() => setSelected(r.id)} className="text-left text-accent"><strong className="block">{r.name}</strong><span className="font-mono">{r.id}</span></button>
            : col.id === 'direction' ? directions[r.direction] : col.id === 'definition_status' ? `${r.definition_status} · 限定样稿` : r.timeframe}</td>} />}
        <section aria-label="信号样稿详情" className={card}>{!detail ? <p>暂无选中样稿</p> : <>
          <h2 className="font-semibold">{detail.name} · {detail.id}</h2>
          <p>市场：{detail.market} · fixture_version：{detail.fixture_version} · 方向：{directions[detail.direction]} · timeframe：{detail.timeframe}</p>
          <p>定义质量：{detail.definition_status}（仅样稿完整性） · 生产执行：{detail.execution_status}</p>
          <p>组合逻辑：AND · 只读条件，不转换为表达式、不编译或评估。</p>
          {!detail.conditions ? <p>conditions: — · {detail.missing_reasons.conditions}</p> : <div className="overflow-x-auto"><table className="w-full text-left" aria-label="结构化合成条件"><thead><tr>{['左字段', '比较', '右值类型', '右值', '左交易日偏移', '右交易日偏移'].map(t => <th scope="col" key={t} className="p-2">{t}</th>)}</tr></thead><tbody>{detail.conditions.map((c, i) => <tr key={i}>{[c.left, c.op, c.right?.kind, c.right?.value, c.left_sessions, c.right_sessions].map((v, n) => <td key={n} className="p-2">{v ?? `— · ${c.missing_reasons[['left', 'op', 'right', 'right', 'left_sessions', 'right_sessions'][n]]}`}</td>)}</tr>)}</tbody></table></div>}
          <p className="break-all">source: {detail.source} · evidence: {detail.evidence}</p>
          {(['production_version', 'last_trigger_at', 'trigger_count', 'production_binding'] as const).map(k => <p key={k} data-signal-missing={k}>{k}: — · {detail.missing_reasons[k]}</p>)}
          {detail.blockers.map(b => <p key={b} className="text-warning">blocker: {b}</p>)}
          {detail.warnings.map(w => <p key={w}>warning: {w}</p>)}
        </>}</section>
      </>}
      <section className="flex flex-wrap gap-2" aria-label="Preview 不可执行操作">{['保存', '编辑', '启停', '删除', 'AI 生成', '注册', '评估'].map(a => <button type="button" disabled key={a} title="Preview 模式不可执行；不连接生产信号、策略、回测或监控" className="rounded-btn border border-border px-3 py-1 text-xs text-muted">{a}（Preview 不可执行）</button>)}</section>
    </div>
  </div>
}
function FixtureSignals({ market, controls }: { market: SignalMarket; controls: ReactNode }) {
  let state: SignalPreviewState
  try { state = { kind: 'ready', data: loadSignalPreview(market) } } catch { state = { kind: 'error' } }
  return <SignalPreview market={market} state={state} controls={controls} />
}
export function SignalMarkets({ cn }: { cn: (controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams()
  const requested = params.get('market'), market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']} onChange={next => setParams(old => {
    const copy = new URLSearchParams(old); copy.set('market', next); return copy
  })} />
  return <div key={market} data-signal-market={market} className="h-full min-h-0">{market === 'CN' ? cn(controls) : <FixtureSignals market={market} controls={controls} />}</div>
}
