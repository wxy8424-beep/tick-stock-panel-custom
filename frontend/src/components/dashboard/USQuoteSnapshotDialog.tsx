import { useId } from 'react'
import type { MarketSnapshotRow, USFocusQuoteMetadata } from '@/lib/api'
import { Modal } from '@/components/Modal'

export interface USQuoteSnapshotDialogProps {
  symbol: string
  quote: MarketSnapshotRow | null
  responseTime?: string
  metadata?: USFocusQuoteMetadata | null
  loading: boolean
  fetching: boolean
  failed: boolean
  invalid: boolean
  previous?: string
  next?: string
  onClose: () => void
  onRetry: () => void
  onNavigate: (symbol: string) => void
}

const missing = '— · 接口未提供或无效'
const numeric = (value: unknown, percent = false) => typeof value === 'number' && Number.isFinite(value) && Number.isFinite(percent ? value * 100 : value)
  ? `${(percent ? value * 100 : value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${percent ? '%' : ''}` : missing
const text = (value: unknown) => typeof value === 'string' && value.trim() ? value : missing
const zonedTime = (value: unknown) => typeof value === 'string' && /T.*(?:Z|[+-]\d\d:\d\d)$/.test(value) ? Date.parse(value) : NaN
function time(value: unknown) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0 || !Number.isFinite(new Date(value).getTime())) return missing
  return `${new Intl.DateTimeFormat('zh-CN', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(new Date(value))} · America/New_York`
}

/** Read-only rendering only; URL, requests and cache ownership stay in the US dashboard. */
export function USQuoteSnapshotDialog(p: USQuoteSnapshotDialogProps) {
  const title = useId()
  const quote = !p.invalid && p.quote?.symbol === p.symbol && (p.quote.market == null || p.quote.market === 'US') ? p.quote : null
  const responseTime = zonedTime(p.responseTime)
  const metadata = p.metadata
  const metadataValid = metadata != null && metadata.symbol === p.symbol && ['available', 'empty', 'error', 'unavailable'].includes(metadata.status)
    && (metadata.status !== 'available' || quote !== null)
  const metadataProblem = metadata == null ? '旧接口未提供独立元数据' : '元数据证券身份或状态不一致，未采用'
  const acquiredTime = zonedTime(metadataValid && metadata?.status === 'available' ? metadata.acquired_at : null)
  const statusLabels = { available: '已取得匹配报价（不代表实时）', empty: '未取得匹配报价', error: '报价获取失败', unavailable: '报价获取不可用' }
  const fields = quote ? [
    ['名称', text(quote.name)], ['市场', text(quote.market)], ['币种', text(quote.currency)],
    ['报价快照价', numeric(quote.close)], ['涨跌幅', numeric(quote.change_pct, true)],
    ['今开', numeric(quote.open)], ['最高', numeric(quote.high)], ['最低', numeric(quote.low)],
    ['成交额（币种见上）', numeric(quote.amount)],
  ] : []
  return <Modal onClose={p.onClose} labelledBy={title} panelClassName="w-[calc(100vw-24px)] max-w-xl max-h-[calc(100dvh-24px)] overflow-y-auto rounded-card border border-border bg-surface p-4 shadow-xl">
    <div className="flex items-start justify-between gap-3">
      <h2 id={title} className="min-w-0 break-words text-sm font-semibold">美股报价快照 · {p.symbol || '无有效代码'}</h2>
      <button type="button" aria-label="关闭快照" className="shrink-0 rounded-btn border border-border px-2 py-1 text-xs" onClick={p.onClose}>关闭</button>
    </div>
    <p className="my-3 text-xs text-muted">只读报价 · 非完整个股技术分析 · 不提供投资建议</p>
    <div aria-live="polite" className="space-y-3 text-xs">
      {p.invalid ? <p role="alert">报价链接参数错误：仅接受一个合法美股证券代码；不回退其他市场或默认证券。</p>
        : p.loading ? <p role="status">正在获取 {p.symbol} 报价…</p>
          : <>
            {p.failed && <p role="alert" className="text-warning">{quote ? '刷新失败，保留同证券缓存报价（可能过期）；请核对报价时间。' : '报价请求失败，请重试；失败原因不代表证券不存在。'}</p>}
            {!quote && !p.failed && <p>接口未返回该证券报价；具体原因接口未提供。</p>}
            {quote && <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">{fields.map(([label, value]) => <div key={label} className="min-w-0 break-words rounded-lg border border-border p-2"><dt className="text-muted">{label}</dt><dd className="mt-1 font-mono">{value}</dd></div>)}</dl>}
            {quote && <p>报价时间：{time(quote.timestamp)}（不是聚合批次时间或日线定版时间）</p>}
            <p>聚合响应时间：{time(responseTime)}（不能替代报价时间）</p>
            <p>报价获取状态：{metadataValid ? statusLabels[metadata!.status] : `— · ${metadataProblem}`}{metadataValid && metadata?.reason ? ` · ${metadata.reason}` : ''}</p>
            <p>报价来源：{metadataValid && metadata?.status === 'available' ? (typeof metadata.source === 'string' && metadata.source.trim() ? metadata.source : `— · ${metadata.source_reason || '接口未提供来源原因'}`) : `— · ${metadataValid ? metadata?.source_reason || metadata?.reason || '未取得匹配报价来源' : metadataProblem}`}</p>
            <p>报价区段获取时间：{metadataValid && Number.isFinite(acquiredTime) ? time(acquiredTime) : `— · ${metadataValid ? metadata?.acquired_at_reason || '接口未提供或时间无效/缺少时区' : metadataProblem}`}（成功获取完成时间；缓存命中保留原时间，不能替代报价时间）</p>
            <p>延迟等级：— · 接口未提供独立元数据。</p>
            <p>新鲜度无法判定；市场休市、查询缓存新鲜或覆盖批次正常均不能证明该报价实时或未过期。</p>
            <p>昨收原值、涨跌额、成交量及其单位、买卖盘、单证券交易状态：— · 当前接口未提供，不反推或补算。</p>
            <button type="button" disabled={p.fetching} onClick={p.onRetry} className="rounded-btn border border-border px-3 py-1.5 disabled:opacity-50">{p.fetching ? '正在刷新报价' : '重试报价'}</button>
          </>}
    </div>
    <div className="mt-4 flex flex-wrap gap-2">{([['上一只', p.previous], ['下一只', p.next]] as const).map(([label, symbol]) => <button key={label} type="button" disabled={p.invalid || !symbol} title={symbol ? `${label} ${symbol}` : '没有可用的来源榜单导航上下文'} onClick={() => { if (!p.invalid && symbol) p.onNavigate(symbol) }} className="rounded-btn border border-border px-3 py-1.5 text-xs disabled:opacity-50">{label}</button>)}</div>
  </Modal>
}
