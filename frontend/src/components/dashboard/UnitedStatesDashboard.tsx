import { useEffect, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, Gauge, GripVertical, RefreshCw, RotateCcw, X } from 'lucide-react'
import { api, type MarketSnapshotRow, type USSection, type USSectionKey, type USStats } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { fmtBigNum } from '@/lib/format'
import { calendarLabel, marketSessionLabel } from '@/lib/marketSession'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { DashboardGrid, normalizeDashboardLayout } from './DashboardGrid'
import { AddWidgetPanel } from './AddWidgetPanel'
import { DEFAULT_LAYOUT, widgetDef } from './registry'
import { cloneItems, compactLayout, toBlob, type DashboardItem, type WidgetType } from './layout'
import { ExternalLinkWidget } from './ExternalLinkWidget'
import { BreadthBar, DistributionBars, StockList } from './widgets'
import { fmtPrice, fmtStockPct, KpiCell, MiniMetric, SectionTitle } from './shared'
import { HK_MODE_LABELS, hkError, hkIndustry, hkReason, hkStockName } from './hkLabels'

export const US_LAYOUT_KEY = 'tsp.dashboard.us.layout.v1'
export function normalizeUSLayout(blob: unknown): DashboardItem[] {
  // Reserve space for the metric subtitle and two rows at medium widths.
  return compactLayout(normalizeDashboardLayout(blob).map(item => item.t === 'kpi' ? { ...item, h: Math.max(3, item.h) } : item))
}
export const US_WIDGET_LABELS: Record<WidgetType, string> = {
  indices: '美股指数', kpi: '样本市场指标', distribution: '样本涨跌分布 / 广度', radar: '情绪雷达',
  trend: '趋势强度 / 实用观察', ladder: '期权情绪', 'concept-rank': '主题 / 概念', 'industry-rank': '行业表现',
  monitor: '美股异动 / 原因', gainers: '样本涨幅榜', losers: '样本跌幅榜', turnover: '样本成交额榜', activity: '异动活跃榜', 'ext-link': '外部链接',
}
type Row = MarketSnapshotRow & { timestamp?: number; reason?: string; labels?: string[] }
const stockName = (row: Row) => hkStockName({ symbol: row.symbol, name: row.name ?? undefined, name_cn: row.name_cn, name_en: row.name_en })
const dateTime = (value?: string | number | null) => value ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'America/New_York', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '—'
const indexNames: Record<string, string> = { '.SPX.US': '标普500', '.IXIC.US': '纳斯达克综合', '.DJI.US': '道琼斯工业' }

function Frame({ type, label, section, loading, error, children }: { type: WidgetType; label: string; section?: USSection; loading: boolean; error: boolean; children: ReactNode }) {
  const def = widgetDef(type)!
  return <section data-us-slot={type} className="flex h-full min-h-0 flex-col overflow-hidden rounded-card border border-border bg-surface/80 p-1.5 shadow-[0_1px_2px_hsl(var(--border)/0.4)] backdrop-blur-sm">
    <SectionTitle icon={def.icon} title={label} hint={HK_MODE_LABELS[section?.mode ?? 'UNAVAILABLE']} />
    <p className="mb-1 break-words text-[9px] text-muted" title={section?.source}>数据源：{section?.source || '待获取'} · 更新 {dateTime(section?.updated_at)}</p>
    <div className="min-h-0 flex-1 overflow-auto">
      {loading ? <p className="py-5 text-center text-xs text-muted">加载中…</p> : error ? <p className="py-5 text-xs text-warning">请求失败，请稍后重试</p>
        : !section || section.status === 'unavailable' ? <p className="py-5 text-xs text-muted">暂不可用<br />{section?.error || '暂无可靠数据源'}</p>
          : section.status === 'error' ? <p className="py-5 text-xs text-warning">暂时无法获取 · {hkError(section.error)}</p>
            : section.status === 'empty' ? <p className="py-5 text-xs text-muted">{section.error || '暂无数据'}</p> : children}
    </div>
  </section>
}

export function UnitedStatesDashboard({ onMarketChange }: { onMarketChange: (market: Market) => void }) {
  const [focus, setFocus] = useState<string>()
  const [preview, setPreview] = useState(false)
  const [navigation, setNavigation] = useState<Row[]>([])
  const [editing, setEditing] = useState(false)
  const [items, setStoredItems] = useState<DashboardItem[]>(() => {
    try { return normalizeUSLayout(JSON.parse(localStorage.getItem(US_LAYOUT_KEY) || 'null')) } catch { return normalizeUSLayout(null) }
  })
  const setItems = (next: DashboardItem[]) => setStoredItems(normalizeUSLayout(toBlob(next)))
  useEffect(() => {
    try { localStorage.setItem(US_LAYOUT_KEY, JSON.stringify(toBlob(items))) } catch { /* Session layout still works when storage is unavailable. */ }
  }, [items])
  const query = useQuery({ queryKey: QK.usDashboard(focus), queryFn: () => api.usDashboard(focus), staleTime: 30000, refetchInterval: 30000, retry: false })
  const data = query.data
  const universe = data?.sample.scope === 'provider_universe'
  const prefix = universe ? '覆盖证券' : '样本'
  const labels = universe ? { ...US_WIDGET_LABELS, kpi: '覆盖证券指标', distribution: '覆盖证券涨跌分布 / 广度', gainers: '覆盖证券涨幅榜', losers: '覆盖证券跌幅榜', turnover: '覆盖证券成交额榜' } : US_WIDGET_LABELS
  const coverageStatus = { loading: '首次采集中', refreshing: '后台刷新中', ready: '本轮全部获取', partial: '部分获取', stale: '保留上轮快照（刷新失败）', unavailable: '采集不可用' }[data?.sample.status ?? 'loading']
  const rows = (key: USSectionKey): Row[] => Array.isArray(data?.[key].data) ? data[key].data as Row[] : []
  const open = (row: Row, source: Row[]) => { setFocus(row.symbol); setNavigation(source); setPreview(true) }
  const add = (type: WidgetType, props?: Record<string, string>) => {
    if (type !== 'ext-link' && items.some(item => item.t === type)) return
    const def = widgetDef(type)!
    setItems([...items, { i: type === 'ext-link' ? `ext-link-${Date.now()}` : type, t: type, x: 0, y: Math.max(0, ...items.map(item => item.y + item.h)), w: def.defW, h: def.defH, p: props }])
  }
  const metrics = data?.kpi.data as USStats | null | undefined
  const content = (type: USSectionKey) => {
    if (type === 'indices') return <div className="grid grid-cols-2 gap-1 md:grid-cols-4">{rows(type).map(row => <div key={row.symbol} className="grid min-w-0 grid-cols-[1fr_auto] items-center gap-x-2 gap-y-0.5 rounded-lg border border-border bg-elevated/45 px-1.5 py-1">
      <span className="truncate text-xs font-medium">{indexNames[row.symbol] || row.symbol}</span><span className="font-mono text-xs">{fmtStockPct(row.change_pct)}</span><span className="font-mono text-[10px] text-muted">{row.symbol}</span><span className="font-mono text-[11px]">{fmtPrice(row.close)}</span>
    </div>)}</div>
    if (type === 'kpi' && metrics) return <div className="grid h-full grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6 [&>div>div:nth-child(2)]:whitespace-normal [&>div>div:nth-child(2)]:break-words [&>div>div:nth-child(2)]:text-sm [&>div>div:last-child]:whitespace-normal">
      <KpiCell label={`${prefix}涨 / 平 / 跌`} value={`${metrics.up}/${metrics.flat}/${metrics.down}`} sub={`${metrics.total}只有效涨跌快照`} />
      <KpiCell label={`${prefix}强势 / 弱势`} value={`${metrics.strong_up}/${metrics.strong_down}`} sub="涨跌 ≥3%" />
      <KpiCell label={`${prefix}上涨率`} value={metrics.up_pct === null ? '—' : `${metrics.up_pct.toFixed(1)}%`} sub="统计范围见覆盖信息" />
      <KpiCell label={`${prefix}平均涨跌`} value={fmtStockPct(metrics.avg_pct)} sub="有效快照均值" />
      <KpiCell label={`${prefix}成交额`} value={metrics.amount_total === null ? '—' : fmtBigNum(metrics.amount_total)} sub={`${metrics.amount_count}只 · 已确认美元币种`} />
      <KpiCell label={`${prefix}中位涨跌`} value={fmtStockPct(metrics.median_pct)} sub="含ETF等证券" />
    </div>
    if (type === 'distribution') {
      const value = data?.distribution.data as { breadth: USStats; bins: { label: string; count: number }[] } | null
      return value && <><DistributionBars rows={value.bins.map(bin => ({ ...bin, pct: value.breadth.total > 0 ? bin.count / value.breadth.total * 100 : 0 }))} /><BreadthBar data={{ ...value.breadth, down_pct: value.breadth.total > 0 ? value.breadth.down / value.breadth.total * 100 : 0, up_pct: value.breadth.up_pct ?? 0, avg_pct: value.breadth.avg_pct ?? 0, median_pct: value.breadth.median_pct ?? 0 }} /><div className="mt-2 grid grid-cols-2 gap-1.5"><MiniMetric label={`${prefix}平均涨跌`} value={fmtStockPct(value.breadth.avg_pct)} /><MiniMetric label={`${prefix}中位涨跌`} value={fmtStockPct(value.breadth.median_pct)} /></div></>
    }
    if (type === 'ladder') {
      const value = data?.ladder.data as { symbol: string; call_volume: number | null; put_volume: number | null; put_call_ratio: number | null } | null
      return value && <><p className="mb-2 text-[10px] text-muted">焦点 {value.symbol} · 未提供OI，未计算情绪评分</p><div className="grid grid-cols-2 gap-1.5"><MiniMetric label="看涨期权成交量" value={fmtPrice(value.call_volume, 0)} /><MiniMetric label="看跌期权成交量" value={fmtPrice(value.put_volume, 0)} /><MiniMetric label="看跌/看涨成交比" value={fmtPrice(value.put_call_ratio)} /></div><p className="mt-2 text-[9px] text-muted">比率为派生；看涨成交量为0时显示 —</p></>
    }
    if (type === 'gainers' || type === 'losers' || type === 'turnover') return <StockList title={labels[type]} rows={rows(type)} mode={type === 'gainers' ? 'gain' : type === 'losers' ? 'loss' : 'amount'} activeSymbol={preview ? focus : undefined} onStockClick={symbol => { const source = rows(type).slice(0, 8); const row = source.find(item => item.symbol === symbol); if (row) open(row, source) }} />
    if (type === 'monitor' || type === 'activity') return <div className="space-y-1.5">{rows(type).map((row, index) => <button key={`${row.symbol}-${index}`} type="button" className="block w-full rounded-md border border-border/40 bg-elevated/40 p-1.5 text-left text-[10px] hover:border-accent/40" onClick={() => open(row, rows(type))}>
      <div className="flex items-center justify-between gap-1"><span className="truncate">{stockName(row)} · {row.symbol}</span><span className="shrink-0 font-mono">{fmtStockPct(row.change_pct)}</span></div><p className="mt-1 text-secondary">{hkReason(row.reason)}</p><p className="mt-1 text-muted">{dateTime(row.timestamp)} · {row.labels?.map(label => hkIndustry(label)).join(' / ')}</p>
    </button>)}</div>
    return null
  }
  const render = (item: DashboardItem) => {
    if (item.t === 'ext-link') return <ExternalLinkWidget title={item.p?.title || '外部链接'} url={item.p?.url || 'about:blank'} />
    const section = data?.[item.t]
    // The two top rows retain CN's individual ticker/KPI cells without a card wrapper.
    if ((item.t === 'kpi' || item.t === 'indices') && section?.status === 'ok') return <div data-us-slot={item.t} className="flex h-full min-h-0 flex-col"><div className="mb-0.5 text-[9px] text-muted">{labels[item.t]} · {HK_MODE_LABELS[section.mode]} · {dateTime(section.updated_at)}</div><div className="min-h-0 flex-1 overflow-auto">{content(item.t)}</div></div>
    return <Frame type={item.t} label={labels[item.t]} section={section} loading={query.isLoading} error={query.isError}>{content(item.t)}</Frame>
  }
  const sessionLabel = marketSessionLabel(data?.market)
  const focused = data && focus && data.focus_symbol === focus ? data.focus_quote as Row | null : null
  return <div className="min-h-full min-w-0 bg-base p-1.5">
    <header className="relative mb-1.5 flex flex-wrap items-center justify-between gap-2 overflow-hidden rounded-card border border-border bg-gradient-to-r from-surface/90 to-surface/70 px-3 py-1.5 shadow-[0_1px_3px_hsl(var(--border)/0.4)] backdrop-blur-sm">
      <div className="pointer-events-none absolute left-0 top-0 h-full w-1 bg-gradient-to-b from-accent to-accent/20" /><div className="flex items-center gap-2"><Gauge className="h-4 w-4 text-accent" /><h1 className="text-[16px] font-semibold leading-6">美股市场看板</h1><span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-accent">{sessionLabel}</span></div>
      <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-secondary"><span>纽约 {dateTime(data?.market.local_time)}</span><span>Longbridge</span><button type="button" onClick={() => query.refetch()} disabled={query.isFetching} className="inline-flex items-center gap-1 rounded-btn border border-border bg-elevated px-2 py-1 text-[11px] disabled:opacity-50"><RefreshCw className="h-3 w-3" />重载</button>{!editing ? <button type="button" onClick={() => setEditing(true)} className="inline-flex items-center gap-1 rounded-btn border border-border bg-elevated px-2 py-1 text-[11px]"><GripVertical className="h-3 w-3" />自定义布局</button> : <><AddWidgetPanel placedTypes={new Set(items.map(item => item.t))} onAdd={add} widgetLabels={US_WIDGET_LABELS} /><button type="button" onClick={() => setItems(cloneItems(DEFAULT_LAYOUT))} className="inline-flex items-center gap-1 rounded-btn border border-border px-2 py-1"><RotateCcw className="h-3 w-3" />恢复默认</button><button type="button" onClick={() => setEditing(false)} className="inline-flex items-center gap-1 rounded-btn bg-accent px-2 py-1 text-white"><Check className="h-3 w-3" />完成</button></>}</div>
    </header>
    <MarketSwitcherBar value="US" enabledMarkets={['CN', 'HK', 'US']} onChange={onMarketChange} className="mb-1.5 rounded-card border px-3" />
    <p className="mb-1.5 break-words text-[10px] text-muted">{data?.sample.coverage || '当前可获取美股样本，非全市场'} · 成功 {data?.sample.received ?? '—'}/{data?.sample.requested ?? '—'}{universe && <> · {coverageStatus} · 缺失 {data?.sample.failed ?? 0} · 失败批次 {data?.sample.failed_batches ?? 0} · 拒绝代码 {data?.sample.rejected_symbols ?? 0} · 统计日期 {data?.sample.statistics_date || '—'}（纽约） · 纳入统计 {data?.sample.statistics_received ?? '—'} · 排除旧日报价 {data?.sample.stale_quote_count ?? 0} · 完成 {dateTime(data?.sample.completed_at)} · 逐批快照，非同一瞬间；常规时段每轮后30秒刷新，其余时段5分钟。{data?.sample.error && ` 原因：${hkError(data.sample.error)}`}</>} · 报价可能停留在标的最近交易时刻；历史日期暂不可用；{calendarLabel(data?.market)}。未启用盘前/盘后行情。</p>
    <DashboardGrid items={items} onItemsChange={next => setItems(normalizeUSLayout(toBlob(next)))} editing={editing} renderItem={render} widgetLabels={labels} rowHeight={48} gap={10} />
    {preview && <div role="dialog" aria-modal="true" aria-label="美股股票快照" className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3" onClick={() => setPreview(false)} onKeyDown={event => { if (event.key === 'Escape') setPreview(false) }}>
      <div className="w-full max-w-lg rounded-card border border-border bg-surface p-4" onClick={event => event.stopPropagation()}><div className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold">{focused ? stockName(focused) : focus} · {focus}</h2><button type="button" aria-label="关闭快照" onClick={() => setPreview(false)}><X className="h-4 w-4" /></button></div>{focused ? <div className="grid grid-cols-3 gap-2"><MiniMetric label="最新价" value={fmtPrice(focused.close)} /><MiniMetric label="涨跌幅" value={fmtStockPct(focused.change_pct)} /><MiniMetric label="今开" value={fmtPrice(focused.open)} /><MiniMetric label="最高" value={fmtPrice(focused.high)} /><MiniMetric label="最低" value={fmtPrice(focused.low)} /><MiniMetric label="币种" value={focused.currency || '—'} /></div> : <p className="text-xs text-muted">{query.isFetching ? '加载中…' : '暂无该股票可靠快照'}</p>}<p className="mt-3 text-[10px] text-muted">更新 {dateTime(focused?.timestamp)} · 只读报价，未启用美股个股分析或交易</p><div className="mt-3 flex gap-2">{['上一只', '下一只'].map((label, offset) => { const index = navigation.findIndex(row => row.symbol === focus) + (offset ? 1 : -1); return <button key={label} type="button" disabled={!navigation[index]} onClick={() => setFocus(navigation[index].symbol)} className="rounded-btn border border-border px-2 py-1 text-xs disabled:opacity-40">{label}</button> })}</div></div>
    </div>}
  </div>
}
