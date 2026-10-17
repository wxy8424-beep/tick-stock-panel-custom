import { useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadDataPreview } from '../../../../tests/fixtures/data_preview'
import { validateDataPreview, type DataPreviewMarket, type DataPreviewState, type DataSetPreviewRow, type QualityStatus } from './contract'

const card = 'min-w-0 rounded-xl border border-border bg-surface/40 p-4 text-xs space-y-2'
const count = (n: number | null) => n === null ? '—（未测量）' : String(n)
const ratio = (n: number | null) => n === null ? '—（未定义）' : `${(n * 100).toFixed(1)}%`
const kindLabel = (row: DataSetPreviewRow) => row.evidence_kind === 'STATIC_AUDIT' ? '静态审计结果 · 非动态检查' : '合成覆盖样稿 · 非生产统计'
const columns: ColumnConfig[] = [['name', '数据集 / 证据类别'], ['source_id', '来源'], ['data_type', '数据类型'], ['symbol_count', '证券数（仅合成样稿）'], ['date_from', '覆盖起点（仅合成样稿）'], ['quality_status', '限定质量状态']].map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
function Badge({ status }: { status: QualityStatus }) { return <span className={`rounded border px-2 py-0.5 text-[10px] ${status === 'READY' ? 'border-accent/30 text-accent' : 'border-warning/30 text-warning'}`}>{status}</span> }
function Disabled({ children }: { children: ReactNode }) { return <button disabled title="Preview 模式不可执行：不刷新、补数、改配置或写入数据库" className="rounded-btn border border-border px-3 py-1 text-xs text-muted">{children}（Preview 不可执行）</button> }

export function DataPreview({ market, state, controls }: { market: DataPreviewMarket; state: DataPreviewState; controls?: ReactNode }) {
  const [search, setSearch] = useState(''), [type, setType] = useState('ALL'), [source, setSource] = useState('ALL'), [quality, setQuality] = useState('ALL'), [selected, setSelected] = useState<string | null>(null)
  const { sort, toggle, sortRows } = useTableSort<DataSetPreviewRow>((row, col) => col.id === 'symbol_count' ? row.coverage.symbol_count : col.id === 'date_from' ? row.coverage.date_from : row[col.id as 'name' | 'source_id' | 'quality_status' | 'data_type'])
  const data = state.kind === 'ready' ? validateDataPreview(state.data) : null
  if (data && data.market !== market) throw new Error('data_preview_market_conflict')
  const rows = sortRows((data?.rows ?? []).filter(r => `${r.name} ${r.symbols.join(' ')} ${r.fields.join(' ')}`.toLowerCase().includes(search.trim().toLowerCase()) && (type === 'ALL' || type === r.data_type) && (source === 'ALL' || source === r.source_id) && (quality === 'ALL' || quality === r.quality_status)), columns)
  const detail = rows.find(r => r.id === selected) ?? rows[0]
  return <div data-data-preview={market} className="flex min-h-0 flex-col">
    <PageHeader title={`${market} 数据 · Preview`} subtitle={`固定样稿交易日：${data?.trading_date ?? '—'}`} right={<Disabled>立即同步</Disabled>} />{controls}
    <div className="mx-auto w-full max-w-[1440px] space-y-4 p-5">
      <aside aria-label="数据演示声明" className="rounded-xl border border-warning/30 bg-warning/5 p-4 text-xs text-warning space-y-2">
        <p>Preview 数据｜非实时数据源状态｜不代表生产覆盖率</p><p>演示数据｜非生产行情｜不构成投资信号。合成覆盖样稿与静态审计结果独立标注；没有实时 Provider Health 检查。</p>
      </aside>
      {state.kind === 'loading' ? <p role="status">数据 Preview 加载中…</p> : state.kind === 'error' ? <ErrorState title="数据 Preview 加载失败" hint="不回退真实数据状态、刷新或供应商接口。" /> : data && <>
        <section aria-label="生产覆盖边界" className={card}><h2 className="text-sm font-semibold">{market} 当前生产覆盖：—（未测量）</h2><p>真实证券数、Daily 日期范围、覆盖/缺失交易日、OHLC/成交量/成交额覆盖率均为未知；本页不查询生产库。</p><p>SDK 支持 ≠ 只读样本验证 ≠ 生产集成 ≠ 当前生产数据观测。历史 Snapshot Archive 行数不是 Daily OHLCV 覆盖。</p></section>
        <section aria-label="静态数据源证据" className="space-y-3"><h2 className="text-sm font-semibold">数据来源 · 静态证据，不是 Provider Health</h2><div className="grid gap-3 lg:grid-cols-2">{data.sources.map(s => <article key={s.id} className={card}>
          <h3 className="font-semibold">{s.name} · {market}</h3><p>数据类型：{s.data_type}</p><p>接入方式：{s.access}</p><p>SDK / 接口能力：{s.sdk_capability}</p><p>只读验证：{s.readonly_validation}</p><p>生产集成：{s.integration}</p><p>当前生产观测：— · 实时健康：—</p><p className="text-warning">{s.reason}</p><p className="break-all text-muted">evidence: {s.evidence}</p>
        </article>)}</div></section>
        <section aria-label="数据集筛选" className="flex flex-wrap items-center gap-3 text-xs">
          <input aria-label="搜索数据样稿" placeholder="证券 / 数据集 / 字段" value={search} onChange={e => setSearch(e.target.value)} className="rounded-btn border border-border bg-base p-2" />
          <select aria-label="演示数据类型" value={type} onChange={e => setType(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部数据类型</option><option value="DAILY">Daily</option><option value="UNIVERSE">Universe</option></select>
          <select aria-label="演示数据源" value={source} onChange={e => setSource(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部来源</option>{data.sources.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
          <select aria-label="限定质量状态" value={quality} onChange={e => setQuality(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部状态</option>{(['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED'] as const).map(s => <option key={s}>{s}</option>)}</select>
          <span>筛选仅作用数据集与详情，不改变下方静态契约结论。</span>
        </section>
        {!rows.length ? <EmptyState title="暂无匹配的数据集样稿" hint="不代表生产数据为空，不自动下载或补数。" /> : <StockDataTable columns={columns} rows={rows} rowKey={(r: DataSetPreviewRow) => r.id} sort={sort} onSortToggle={toggle} renderCell={(r: DataSetPreviewRow, c) => <td className="p-3 text-xs align-top">{c.id === 'name' ? <button data-dataset-id={r.id} onClick={() => setSelected(r.id)} className="text-left text-accent"><strong className="block">{r.name}</strong><span className="text-muted">{kindLabel(r)}</span></button> : c.id === 'quality_status' ? <><Badge status={r.quality_status} /><p className="mt-1">{r.evidence_kind === 'SYNTHETIC_SAMPLE' ? '仅样稿字段状态，不代表生产就绪' : '仅静态证据限定能力'}</p></> : c.id === 'symbol_count' ? count(r.coverage.symbol_count) : c.id === 'date_from' ? r.coverage.date_from ?? '—（未测量）' : r[c.id as 'source_id' | 'data_type']}</td>} />}
        <section aria-label="数据集样稿详情" className={card}><h2 className="text-sm font-semibold">数据集 / 字段 / 覆盖详情</h2>{detail ? <>
          <p>{detail.name} · {market} · {kindLabel(detail)} · <Badge status={detail.quality_status} /></p><p>source: {detail.source_id} · evidence: <span className="break-all">{detail.evidence}</span></p><p>证券：{detail.symbols.join('、') || '—（无当前覆盖证据）'}</p><p>字段：{detail.fields.join('、')}</p>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">{[['symbol_count', '证券数'], ['covered_sessions', '已覆盖交易日'], ['missing_sessions', '缺失交易日']].map(([key, label]) => <p key={key} data-coverage-field={key}>{label}：{count(detail.coverage[key as 'symbol_count'])}</p>)}<p>范围：{detail.coverage.date_from ?? '—'} .. {detail.coverage.date_to ?? '—'}</p>{(['ohlc_ratio', 'volume_ratio', 'turnover_ratio'] as const).map(k => <p key={k} data-coverage-field={k}>{({ ohlc_ratio: 'OHLC 字段比例', volume_ratio: '成交量字段比例', turnover_ratio: '成交额字段比例' })[k]}：{ratio(detail.coverage[k])}</p>)}</div>
          <p>调整方式：{detail.adjustment ?? '—（未定义 / 不适用，见原因）'}</p><p>样稿更新时间 UTC：{detail.updated_at ?? '—（当前更新时间未知）'} · historical available_at：—（未知）</p><p>missing_fields: {detail.missing_fields.join('、')}</p>{detail.reasons.map(r => <p key={r} className="text-warning">{r}</p>)}
        </> : <p>暂无选中的数据集样稿</p>}</section>
        <section aria-label="静态质量契约" className={card}><h2 className="text-sm font-semibold">数据质量 / 输入契约 · 静态审计快照</h2><p>供应商审计日期：{data.audit_date}；以下为仓库材料的有限结论，不是实时诊断。READY 仅对该行所述能力有效。</p><div className="grid gap-3 md:grid-cols-2">{data.checks.map(c => <article key={c.key} data-quality-key={c.key} className="min-w-0 rounded-lg border border-border p-3 space-y-1"><h3>{c.label} · <Badge status={c.status} /></h3><p className="break-all">{c.value ?? '—（证据未知 / 不足）'}</p><p className="text-warning">{c.reason}</p><p className="break-all text-muted">evidence: {c.evidence}</p></article>)}</div></section>
        <section aria-label="数据演示限制" className={card}>{data.blockers.map(r => <p key={r} className="text-warning">blocker: {r}</p>)}{data.warnings.map(r => <p key={r} className="text-muted">warning: {r}</p>)}<p>PREVIEW · source: {data.source} · data_mode: preview · is_production: false · is_investment_signal: false</p><p>固定样稿交易日：{data.trading_date} · 固定页面样稿 generated_at：{data.generated_at}（不是供应商更新时间）</p><div className="flex flex-wrap gap-2"><Disabled>修正 / 补数据</Disabled><Disabled>清除数据</Disabled><Disabled>切换数据源</Disabled></div></section>
      </>}
    </div>
  </div>
}
function FixtureData({ market, controls }: { market: DataPreviewMarket; controls: ReactNode }) {
  let state: DataPreviewState
  try { state = { kind: 'ready', data: loadDataPreview(market) } } catch { state = { kind: 'error' } }
  return <DataPreview market={market} state={state} controls={controls} />
}
export function DataMarkets({ cn }: { cn: (controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams(), requested = params.get('market')
  const market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const [visited, setVisited] = useState<readonly DataPreviewMarket[]>(market === 'CN' ? [] : [market])
  useEffect(() => { if (market !== 'CN') setVisited(old => old.includes(market) ? old : [...old, market]) }, [market])
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']} onChange={next => setParams(old => { const copy = new URLSearchParams(old); copy.set('market', next); return copy })} />
  return <div className="h-full min-h-0">{market === 'CN' && <div data-data-market="CN">{cn(controls)}</div>}{(['HK', 'US'] as const).filter(m => visited.includes(m) || market === m).map(m => <div key={m} hidden={market !== m} data-data-market={m}><FixtureData market={m} controls={controls} /></div>)}</div>
}
