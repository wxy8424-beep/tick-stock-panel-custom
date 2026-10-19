import { useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PreviewNotice, PreviewDisabledAction } from '@/components/preview/ReadOnlyPreview'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadBacktestPreview } from '../../../../tests/fixtures/backtest_preview'
import { resultKeys, validateBacktestPreview, type BacktestMarket, type BacktestPreviewState, type BacktestSample } from './contract'

const columns: ColumnConfig[] = [['name', '合成方案 / 身份'], ['kind', '类型'], ['definition_status', '样稿完整性']]
  .map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
const card = 'min-w-0 space-y-3 rounded-xl border border-border bg-surface/40 p-4 text-xs break-words'
export function BacktestPreview({ market, state, controls }: { market: BacktestMarket; state: BacktestPreviewState; controls?: ReactNode }) {
  const [search, setSearch] = useState(''), [kind, setKind] = useState('ALL'), [quality, setQuality] = useState('ALL'), [selected, setSelected] = useState<string | null>(null)
  const { sort, toggle, sortRows } = useTableSort<BacktestSample>((r, col) => r[col.id as 'name' | 'kind' | 'definition_status'])
  let data: ReturnType<typeof loadBacktestPreview> | null = null
  if (state.kind === 'ready') try { const checked = validateBacktestPreview(state.data); if (checked.market === market) data = checked } catch { /* fail closed without API fallback */ }
  const rows = sortRows((data?.rows ?? []).filter(r => `${r.name} ${r.id}`.toLowerCase().includes(search.trim().toLowerCase())
    && (kind === 'ALL' || r.kind === kind) && (quality === 'ALL' || r.definition_status === quality)), columns)
  const detail = rows.find(r => r.id === selected) ?? rows[0]
  return <div className="min-h-full min-w-0 bg-base">
    <PageHeader className="pl-14 md:pl-5" title={`${market} 回测 · Preview`} subtitle="Synthetic Data · Read-only · Not production validation" />
    {controls}
    <div className="space-y-4 p-3 lg:p-5">
      <PreviewNotice statement="演示回测方案｜合成数据｜只读｜不运行回测、不产生交易信号｜不构成投资建议" description="Preview · Synthetic Data · Read-only · Not production validation。未知业绩不是零收益；方案展示不是已验证策略。" />
      {state.kind === 'loading' ? <p role="status">回测样稿加载中…</p> : !data ? <ErrorState title="回测样稿加载失败" hint="错误市场或无效契约；不恢复生产任务、不查询生产数据。" /> : <>
        <section className={card} aria-label="回测样稿概览"><p>固定 Preview 日期：{data.trading_date} · generated_at：{data.generated_at}（样稿编写时间，非运行时间）</p>
          <p>source: synthetic-fixture · PREVIEW · data_mode: preview · is_production: false · is_investment_signal: false</p>
          <p>{data.rows.length} 项合成元数据；生产执行：BLOCKED。日期区间仅供展示，不代表交易日或历史覆盖。</p></section>
        <section className="flex flex-wrap gap-3 text-xs" aria-label="筛选回测样稿">
          <input aria-label="搜索回测样稿" placeholder="名称 / fixture ID" className="max-w-full rounded-btn border border-border bg-base p-2" value={search} onChange={e => setSearch(e.target.value)} />
          <select aria-label="回测样稿类型" value={kind} onChange={e => setKind(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部类型</option><option value="strategy">strategy</option><option value="robustness">robustness</option></select>
          <select aria-label="回测样稿完整性" value={quality} onChange={e => setQuality(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部完整性</option><option>PARTIAL</option><option>BLOCKED</option></select>
        </section>
        {!rows.length ? <EmptyState title="暂无匹配的回测样稿" hint="不表示生产候选为空，不自动补齐或创建任务。" /> : <StockDataTable columns={columns} rows={rows} rowKey={(r: BacktestSample) => r.id} sort={sort} onSortToggle={toggle}
          renderCell={(r: BacktestSample, col) => <td className="p-3 text-xs align-top">{col.id === 'name' ? <button type="button" data-backtest-id={r.id} className="text-left text-accent" onClick={() => setSelected(r.id)}><strong className="block">{r.name}</strong>{r.id}</button> : r[col.id as 'kind' | 'definition_status']}</td>} />}
        <section className={card} aria-label="回测样稿详情">{!detail ? <p>暂无选中样稿</p> : <>
          <h2>{detail.name} · {detail.id}</h2><p>市场：{detail.market} · 币种：{detail.currency} · fixture_version：{detail.fixture_version}</p>
          <p>展示完整性：{detail.definition_status} · 生产执行：{detail.execution_status}</p>
          <dl className="space-y-2" aria-label="合成方案结构">{Object.entries(detail.plan).map(([key, value]) => <div key={key}><dt className="inline">{key}: </dt><dd className="inline">{value ?? `— · ${detail.missing_reasons[key]}`}</dd></div>)}</dl>
          <p>AND 仅为元数据，不编译、不求值；窗口只是合成参数，没有生产默认值、允许范围或优化结论。</p>
          {resultKeys.map(key => <p key={key} data-backtest-missing={key}>{key}: — · {detail.missing_reasons[key]}</p>)}
          <p>source: {detail.source} · evidence: {detail.evidence}</p>
          {detail.blockers.map(b => <p key={b} className="text-warning">blocker: {b}</p>)}{detail.warnings.map(w => <p key={w}>warning: {w}</p>)}
        </>}</section>
      </>}
      <section className="flex flex-wrap gap-2" aria-label="Preview 不可执行操作">{['运行回测', '取消任务', '参数优化', '步进优化', '保存候选', '保存配置', '恢复生产任务', '发布策略'].map(label => <PreviewDisabledAction key={label} label={label} reason="Preview 模式不可执行；不连接回测、配置、任务注册表或交易路径" />)}</section>
    </div>
  </div>
}
function FixtureBacktest({ market, controls }: { market: BacktestMarket; controls: ReactNode }) {
  let state: BacktestPreviewState
  try { state = { kind: 'ready', data: loadBacktestPreview(market) } } catch { state = { kind: 'error' } }
  return <BacktestPreview market={market} state={state} controls={controls} />
}
export function BacktestMarkets({ cn }: { cn: (controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams()
  const requested = params.get('market'), market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']} onChange={next => setParams(old => {
    const copy = new URLSearchParams(old); copy.set('market', next); return copy
  })} />
  return <div key={market} data-backtest-market={market} className="h-full min-h-0">{market === 'CN' ? cn(controls) : <FixtureBacktest market={market} controls={controls} />}</div>
}
