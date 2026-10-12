import { useCallback, useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, ChevronDown, ChevronUp, Shield, X } from 'lucide-react'
import { api, type AnomalyEvent } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { ANOMALY_TYPES, EVENT_STATUS, SEVERITY_LABELS, eventTime, filterEvents, monitoringState, percent } from '@/lib/anomalyPresentation'
import { useAnomalyDelivery } from '@/lib/useAnomalyDelivery'
import { marketSessionLabel } from '@/lib/marketSession'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { HistoricalContextEvidence, HistoricalContextSummary } from '@/components/anomalies/HistoricalContext'
import './AnomalyMonitoring.css'

function Evidence({ event }: { event: AnomalyEvent }) {
  const history = useQuery({ queryKey: QK.anomalyHistoricalContext(event.event_id), queryFn: () => api.anomalyHistoricalContext(event.event_id),
    refetchInterval: query => !query.state.data || query.state.data.blocker === 'enrichment_pending' ? 3000 : false })
  const historicalContext = history.data ?? event.evidence.historical_context
  const episode = useQuery({ queryKey: QK.anomalyEpisodes(event.symbol), queryFn: () => api.anomalyEpisodes(event.symbol), refetchInterval: 3000 })
  const matching = episode.data?.rows.find(row => row.episode_id === event.episode_id)
  return <div className="mt-4 border-t border-border pt-4 text-xs text-secondary">
    <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div><dt>基线 / 当前价格</dt><dd className="font-mono">{event.baseline_value} / {event.observed_value}</dd></div>
      <div><dt>阈值 / 变化</dt><dd>{percent(event.threshold)} / {percent(event.change_pct)}</dd></div>
      <div><dt>时间窗口（浏览器本地时间）</dt><dd>{eventTime(event.window_start)} → {eventTime(event.window_end)}</dd></div>
      <div><dt>规则 / 版本</dt><dd className="break-all font-mono">{event.rule_id} / {event.rule_version}</dd></div>
      <div><dt>证据范围</dt><dd>{event.evidence.baseline_scope === 'timestamp_boundary' ? '真实时间边界快照' : '此前日内归档观测价'} · {event.evidence.sample_count} 个样本 · 最大间隔 {event.evidence.maximum_gap_ms / 1000} 秒</dd></div>
      <div><dt>市场 / 质量证据</dt><dd>{event.market} · 事件经后端常规时段门控 · {event.evidence.current.quality_state} · {event.evidence.current.warning_codes.join(' / ') || '无质量警告'}</dd></div>
      <div><dt>Episode</dt><dd className="break-all">{event.episode_id}</dd><dd>{episode.isError ? 'Episode 查询失败' : matching ? `后端状态：${({ first_trigger: '首次触发', sustained: '持续观察', escalation: '严重程度升级', resolved: '已恢复' } as Record<string, string>)[String(matching.status)] ?? '未识别'} · 最高严重程度：${SEVERITY_LABELS[matching.peak_severity as 'high'] ?? '未确认'}` : '当前 episode 记录未返回'}</dd></div>
      <div><dt>成交量</dt><dd>未参与计算 · 单位未确认</dd></div>
    </dl>
    <HistoricalContextEvidence context={historicalContext} />
    <details className="mt-4"><summary className="cursor-pointer">完整后端事件证据（原始字段）</summary><pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-card bg-base p-3">{JSON.stringify({ ...event, evidence: { ...event.evidence, historical_context: historicalContext } }, null, 2)}</pre></details>
  </div>
}

export function AnomalyMonitoring() {
  const client = useQueryClient()
  const recent = useQuery({ queryKey: QK.anomalyRecent(), queryFn: () => api.anomalyRecent(), enabled: false })
  const [notice, setNotice] = useState<AnomalyEvent[]>([])
  const [arrival, setArrival] = useState(new Map<string, string>())
  const onAttention = useCallback((high: AnomalyEvent[], fresh: AnomalyEvent[]) => {
    if (fresh.length) setArrival(new Map(fresh.map(row => [row.event_id, row.severity])))
    if (high.length) setNotice(previous => [...new Map([...previous, ...high].map(row => [row.event_id, row])).values()])
  }, [])
  const delivery = useAnomalyDelivery(onAttention)
  const health = useQuery({ queryKey: QK.anomalyHealth, queryFn: api.anomalyHealth, refetchInterval: 3000, retry: 1 })
  const [older, setOlder] = useState<AnomalyEvent[]>([])
  const [cursor, setCursor] = useState<number | null | undefined>(undefined)
  const [loading, setLoading] = useState(false)
  const [pageError, setPageError] = useState(false)
  const [market, setMarket] = useState('ALL')
  const [severity, setSeverity] = useState('ALL')
  const [type, setType] = useState('ALL')
  const [symbol, setSymbol] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  useEffect(() => { if (!notice.length) return; const timer = setTimeout(() => setNotice([]), 8000); return () => clearTimeout(timer) }, [notice])
  const rows = [...new Map([...older, ...delivery.rows].map(row => [row.event_id, row])).values()]
  const visible = filterEvents(rows, market, severity, type, symbol)
  const historyIds = visible.slice(0, 100).map(event => event.event_id).sort()
  const histories = useQuery({ queryKey: QK.anomalyHistoricalContexts(historyIds), queryFn: () => api.anomalyHistoricalContexts(historyIds), enabled: historyIds.length > 0,
    refetchInterval: query => !query.state.data || Object.values(query.state.data.contexts).some(context => context.blocker === 'enrichment_pending') ? 3000 : false })
  const state = monitoringState(health.data, delivery.state?.api_reachable === false || health.isError)
  const sessions = health.data?.market_sessions
  const locate = (event: AnomalyEvent) => {
    setMarket('ALL'); setSeverity('ALL'); setType('ALL'); setSymbol(''); setOpen(event.event_id)
    setTimeout(() => document.getElementById(`anomaly-${event.event_id}`)?.scrollIntoView({ block: 'center', behavior: 'auto' }), 0)
  }
  const more = async () => {
    const next = cursor === undefined ? recent.data?.next_before_id : cursor
    if (!next) return
    setLoading(true); setPageError(false)
    try {
      const page = await client.fetchQuery({ queryKey: QK.anomalyRecent(next), queryFn: () => api.anomalyRecent(next), staleTime: 0 })
      setOlder(previous => [...previous, ...page.rows]); setCursor(page.next_before_id)
    } catch { setPageError(true) } finally { setLoading(false) }
  }
  return <main className="mx-auto w-full max-w-[1600px] space-y-5 p-3 sm:p-6">
    <header className="rounded-card border border-border bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-4"><div><h1 className="flex items-center gap-2 text-xl font-semibold"><Activity className="text-amber-300" />异动监控</h1><p className="mt-1 text-xs text-muted">安静观察，有证据才提醒 · 只读市场研究</p></div><span role="status" data-health={state.state} className="rounded-btn border border-border px-3 py-2 text-sm">{state.label}</span></div>
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">{(['high', 'medium', 'low'] as const).map(level => <div key={level} className="rounded-card border border-border bg-base p-3"><div className="text-xs text-muted">{SEVERITY_LABELS[level]} · 已加载事件</div><div className="mt-1 font-mono text-2xl">{rows.filter(row => row.severity === level).length}</div></div>)}<div className="rounded-card border border-border bg-base p-3"><div className="text-xs text-muted">最新事件 · 本地时间</div><div className="mt-2 text-xs">{rows.length ? eventTime(filterEvents(rows, 'ALL', 'ALL', 'ALL', '')[0].detected_at) : '暂无'}</div></div></div>
      <div className="mt-4 flex flex-wrap gap-3 text-xs text-secondary">{(['CN', 'HK', 'US'] as const).map(code => <span key={code}>{code}：{marketSessionLabel(sessions?.[code])}</span>)}</div>
      <p className="mt-3 text-xs text-muted">波动扩张 / 成交量异动暂未启用。盘中真实触发尚未完成验证；连接正常不代表数据已完整。</p>
      <div aria-label="交付诊断" className="mt-3 flex flex-wrap gap-3 text-xs text-secondary">
        <span>交付：{delivery.state?.status === 'caught_up' ? '已追平已读取服务端水位' : delivery.state?.status === 'catching_up' ? '正在分页追赶' : delivery.state?.error ?? '状态未确认'}</span>
        <span>已消费序号 {delivery.state?.cursor?.sequence ?? '—'} / 服务端 {health.data?.delivery?.latest_sequence ?? delivery.state?.latest_sequence ?? '—'}</span>
        <span>最近成功读取：{delivery.state?.last_success_at ? eventTime(delivery.state.last_success_at) : '—'}</span>
        <span>服务端最新事件：{delivery.state?.latest_event_detected_at ? eventTime(delivery.state.latest_event_detected_at) : '暂无'}</span>
        {health.data?.delivery?.latest_sequence != null && delivery.state?.cursor && health.data.delivery.latest_sequence > delivery.state.cursor.sequence && <strong className="text-amber-200">前端落后，正在追赶</strong>}
      </div>
    </header>
    {!!notice.length && <aside role="alert" className="anomaly-notice rounded-card border-2 border-amber-300 bg-amber-400/10 p-4"><div className="mb-2 flex justify-between gap-2"><strong className="text-amber-200">高严重程度新异动 · {notice.length} 条</strong><button aria-label="关闭提醒" onClick={() => setNotice([])}><X size={18} /></button></div>{notice.map(event => <button key={event.event_id} onClick={() => locate(event)} className="mb-1 block text-left text-sm">{event.symbol} · {ANOMALY_TYPES[event.event_type]} · {event.direction === 'up' ? '向上' : '向下'} {percent(event.change_pct)} · HIGH · {EVENT_STATUS[event.status]} · {eventTime(event.detected_at)}</button>)}</aside>}
    <section aria-label="事件筛选" className="flex flex-wrap gap-3 rounded-card border border-border bg-surface p-3">
      <div className="flex gap-1" aria-label="市场筛选">{['ALL', 'CN', 'HK', 'US'].map(code => <button key={code} aria-pressed={market === code} onClick={() => setMarket(code)} className={`rounded-btn px-3 py-2 text-xs ${market === code ? 'bg-amber-300/15 text-amber-200' : 'text-secondary'}`}>{({ ALL: '全部', CN: 'A股', HK: '港股', US: '美股' })[code as 'ALL']}</button>)}</div>
      <select aria-label="严重程度" value={severity} onChange={event => setSeverity(event.target.value)} className="rounded-btn border border-border bg-base p-2 text-xs"><option value="ALL">全部严重程度</option>{Object.entries(SEVERITY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
      <select aria-label="异动类型" value={type} onChange={event => setType(event.target.value)} className="rounded-btn border border-border bg-base p-2 text-xs"><option value="ALL">全部类型</option>{Object.entries(ANOMALY_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
      <input aria-label="搜索股票代码" placeholder="搜索代码，如 AAPL.US" value={symbol} onChange={event => setSymbol(event.target.value)} className="min-w-0 flex-1 rounded-btn border border-border bg-base p-2 text-xs" />
    </section>
    {state.state === 'unavailable' && <p className="rounded-card border border-border p-4 text-sm">连接或引擎暂不可用。历史事件可继续查看，不代表当前正在产生新事件。</p>}
    {market !== 'ALL' && sessions?.[market as 'CN']?.session_state !== 'regular' && <p className="text-sm text-secondary">当前市场关闭或时段未确认，不会产生已确认常规交易时段异动。</p>}
    {!delivery.state ? <p className="p-8 text-center text-muted">正在恢复历史事件…</p> : !visible.length ? <div className="rounded-card border border-border bg-surface p-12 text-center"><Shield className="mx-auto mb-3 text-muted" /><h2>{rows.length ? '当前筛选下暂无事件' : '暂无异动事件'}</h2><p className="mt-2 text-xs text-muted">等待符合条件的后端证据，不生成演示行情。</p></div> : <section aria-label="实时异动流" className="space-y-3">{visible.map(event => <article id={`anomaly-${event.event_id}`} key={event.event_id} data-severity={event.severity} data-arrival={arrival.get(event.event_id)} className={`anomaly-card min-w-0 rounded-card border bg-surface p-4 sm:p-5 ${event.severity === 'high' ? 'border-amber-300/80' : event.severity === 'medium' ? 'border-amber-500/40' : 'border-border'}`}>
      <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><strong className="font-mono text-lg">{event.symbol}</strong><span className="text-xs text-muted">{event.market}</span><span className="rounded-btn bg-elevated px-2 py-1 text-xs">{SEVERITY_LABELS[event.severity]}</span><span className="text-xs text-secondary">{EVENT_STATUS[event.status]}</span></div><h2 className="mt-2 text-sm">{ANOMALY_TYPES[event.event_type]} · {event.direction === 'up' ? '↑ 向上' : '↓ 向下'}</h2></div><div className="text-right"><div className="font-mono text-2xl">{percent(event.change_pct)}</div><div className="text-xs text-muted">观测价 {event.observed_value}</div></div></div>
      <p className="mt-3 break-words text-xs text-secondary">{eventTime(event.detected_at)} · 窗口 {eventTime(event.window_start)} → {eventTime(event.window_end)} · {event.evidence.sample_count} 个证据样本</p>
      <HistoricalContextSummary context={histories.data?.contexts[event.event_id] ?? event.evidence.historical_context} />
      <div className="mt-4 flex flex-wrap gap-3"><button aria-expanded={open === event.event_id} onClick={() => setOpen(open === event.event_id ? null : event.event_id)} className="flex items-center gap-1 text-xs text-amber-200">{open === event.event_id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}查看证据</button>{event.market === 'CN' && <button className="text-xs text-secondary" onClick={() => setPreview(event.symbol)}>查看个股</button>}</div>
      {open === event.event_id && <Evidence event={event} />}
    </article>)}</section>}
    {(cursor === undefined ? recent.data?.next_before_id : cursor) && <button onClick={more} disabled={loading} className="rounded-btn border border-border px-4 py-2 text-sm">{loading ? '加载中…' : '加载更早事件'}</button>}
    {pageError && <p role="status" className="text-sm text-secondary">历史分页读取失败，可以重试。</p>}
    <StockPreviewDialog symbol={preview} onClose={() => setPreview(null)} />
  </main>
}
