import { useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { PreviewNotice, PreviewDisabledAction } from '@/components/preview/ReadOnlyPreview'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadAnalysisPreview } from '../../../../tests/fixtures/stock_analysis_preview'
import { quoteKeys, unknownKeys, validateAnalysisPreview, type AnalysisMarket, type AnalysisPreviewState, type AnalysisSample } from './contract'

const declaration = '演示个股分析｜合成数据｜只读｜非生产研究｜不构成投资建议'
const columns: ColumnConfig[] = [['name', '合成证券 / 代码'], ['last', '样稿参考价'], ['changePercent', '样稿涨跌幅 %']]
  .map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
const labels = { last: '参考价', change: '涨跌额', changePercent: '涨跌幅（百分数 %）', open: '开盘', high: '最高', low: '最低', previousClose: '昨收' }
const actions = ['AI 分析', 'AI 报告生成', '报告保存', '价格提醒', '自选写入', '监控写入', '真实刷新', '实时订阅', '历史下载', '财务同步', '交易 / 模拟交易', '生产评估 / 评分']
const card = 'min-w-0 rounded-card border border-border/60 bg-surface/40 p-4 space-y-2 text-xs break-words'
export function StockAnalysisPreview({ market, state, controls }: { market: AnalysisMarket; state: AnalysisPreviewState; controls?: ReactNode }) {
  const [search, setSearch] = useState(''), [selected, setSelected] = useState<string | null>(null)
  const { sort, toggle, sortRows } = useTableSort<AnalysisSample>((row, col) => col.id === 'name' ? row.name : row.quote[col.id as 'last' | 'changePercent'])
  let data: ReturnType<typeof loadAnalysisPreview> | null = null
  if (state.kind === 'ready') {
    try { const checked = validateAnalysisPreview(state.data); if (checked.market === market) data = checked } catch { /* No production fallback. */ }
  }
  const rows = sortRows((data?.rows ?? []).filter(r => `${r.symbol} ${r.name} ${r.english_name}`.toLowerCase().includes(search.trim().toLowerCase())), columns)
  const detail = rows.find(r => r.id === selected) ?? rows[0]
  const field = (value: number | null, reason: string) => value === null ? `— · ${reason}` : String(value)
  return <div className="min-h-full min-w-0 bg-base" data-analysis-preview>
    <PageHeader title={`${market} 个股分析 · Preview`} subtitle="Synthetic Data · Read-only · Not production research" className="pl-14 md:pl-5" />
    {controls}
    <div className="space-y-4 p-3 lg:p-5">
      <PreviewNotice statement={declaration} description="仅用于界面验收，不读取真实证券、行情、财务或报告。" className="rounded-card border border-warning/30 bg-warning/5 p-4 text-sm text-warning" />
      {state.kind === 'loading' ? <p role="status">个股分析样稿加载中…</p> : !data ? <ErrorState title="个股分析样稿加载失败" hint="拒绝无效契约或市场；不请求真实数据补齐。" /> : <>
        <section className={card} aria-label="个股样稿来源">
          <p>交易日：{data.trading_date} · generated_at：{data.generated_at}（固定样稿编写时间）</p>
          <p>source: synthetic-fixture · PREVIEW · data_mode: preview · is_production: false · is_investment_signal: false</p>
          <p>样稿币种：{market === 'HK' ? 'HKD' : 'USD'} · 不跨市场比较 · 生产执行 BLOCKED</p>
        </section>
        <label className="flex flex-wrap items-center gap-2 text-xs">搜索合成证券<input aria-label="搜索合成证券" value={search} onChange={e => setSearch(e.target.value)} placeholder="样稿代码 / 名称" className="max-w-full rounded-btn border border-border bg-base p-2" /></label>
        {!rows.length ? <EmptyState title="暂无匹配的合成证券" hint="不查询真实证券，不自动恢复生产 symbol。" /> : <StockDataTable columns={columns} rows={rows} rowKey={(r: AnalysisSample) => r.id} sort={sort} onSortToggle={toggle}
          renderCell={(r: AnalysisSample, c) => <td className="p-3 text-xs align-top">{c.id === 'name' ? <button data-analysis-id={r.id} onClick={() => setSelected(r.id)} className="text-left text-accent"><strong className="block">{r.name}</strong><span className="font-mono">{r.symbol}</span></button> : field(r.quote[c.id as 'last' | 'changePercent'], r.missing_reasons[c.id])}</td>} />}
        {detail && <div aria-label="合成证券详情" className="grid min-w-0 gap-4 lg:grid-cols-2">
          <section className={card}><h2 className="font-semibold">{detail.name} · {detail.symbol}</h2><p>{detail.english_name}</p>
            <p>{detail.market} · {detail.currency} · {detail.exchange} · {detail.security_type}</p>
            <p className="break-all">fixture ID: {detail.id} · evidence: {detail.evidence}</p>
            <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">{quoteKeys.map(k => <div key={k}><dt className="text-muted">样稿{labels[k]}</dt><dd data-analysis-field={k}>{field(detail.quote[k], detail.missing_reasons[k])}</dd></div>)}</dl>
          </section>
          <section className={card}><h2 className="font-semibold">技术观察 · 仅固定样稿</h2>
            <p>MA20（{detail.currency}；独立编写，未计算）：{field(detail.technical.ma20, detail.missing_reasons.ma20)}</p>
            <p>volume_ratio_20：{field(detail.technical.volume_ratio_20, detail.missing_reasons.volume_ratio_20)}</p>
            {unknownKeys.map(k => <p key={k} data-analysis-missing={k}>{k}: — · {detail.missing_reasons[k]}</p>)}
            {detail.blockers.map(b => <p key={b} className="text-warning">blocker: {b}</p>)}{detail.warnings.map(w => <p key={w}>warning: {w}</p>)}
          </section>
        </div>}
      </>}
      <section aria-label="Preview 不可执行操作" className="flex flex-wrap gap-2">{actions.map(a => <PreviewDisabledAction key={a} label={a} reason="Preview 模式不可执行；不连接生产分析、报告、监控或交易" />)}</section>
    </div>
  </div>
}
function FixtureAnalysis({ market, controls }: { market: AnalysisMarket; controls: ReactNode }) {
  let state: AnalysisPreviewState
  try { state = { kind: 'ready', data: loadAnalysisPreview(market) } } catch { state = { kind: 'error' } }
  return <StockAnalysisPreview market={market} state={state} controls={controls} />
}
export function StockAnalysisMarkets({ cn }: { cn: (controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams()
  const requested = params.get('market'), market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']} onChange={next => setParams(old => {
    const copy = new URLSearchParams(old); copy.set('market', next); return copy
  })} />
  return <div key={market} data-analysis-market={market} className="min-h-full min-w-0">{market === 'CN' ? cn(controls) : <FixtureAnalysis market={market} controls={controls} />}</div>
}
