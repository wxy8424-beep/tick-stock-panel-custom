import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type HKRow, type HKSection, type HKSectionKey } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { cn } from '@/lib/cn'
import { calendarLabel, marketSessionLabel } from '@/lib/marketSession'
import { HK_MODE_LABELS, hkError, hkIndustry, hkReason, hkStockName } from './hkLabels'

const sections: { key: HKSectionKey; title: string; span: string; hint?: string }[] = [
  { key: 'daily_stocks', title: '每日股票数据', span: 'xl:col-span-8', hint: '当前榜单 / 已获取标的 · 非全港股' },
  { key: 'daily_etfs', title: '每日 ETF 数据', span: 'xl:col-span-4' },
  { key: 'capital_flow', title: '股票资金流向', span: 'xl:col-span-6', hint: '当前焦点股票 · 官方资金流序列' },
  { key: 'morning_accumulation', title: '早盘抢筹', span: 'xl:col-span-3', hint: '派生指标 · 09:30–10:00 · 基于资金流序列计算' },
  { key: 'closing_accumulation', title: '尾盘抢筹', span: 'xl:col-span-3', hint: '派生指标 · 15:30–16:00 · 基于资金流序列计算' },
  { key: 'industry_flow', title: '行业资金流向', span: 'xl:col-span-6' },
  { key: 'concept_flow', title: '概念资金流向', span: 'xl:col-span-6' },
  { key: 'fundamentals', title: '股票基本面数据', span: 'xl:col-span-6' },
  { key: 'dividends', title: '股票分红配送', span: 'xl:col-span-6' },
  { key: 'movers', title: '港股异动榜', span: 'xl:col-span-4' },
  { key: 'block_trades', title: '股票大宗交易', span: 'xl:col-span-4' },
  { key: 'move_reasons', title: '异动原因揭秘', span: 'xl:col-span-4' },
]
const fields = { name: '公司名称', exchange: '交易所', currency: '币种', lot_size: '每手股数', total_shares: '总股本', circulating_shares: '流通股本', eps: 'EPS', eps_ttm: 'EPS TTM', bps: 'BPS', market_cap: '市值', pe: 'PE', pb: 'PB', roe: 'ROE', revenue: '营收', net_profit: '净利润', dividend_yield: '股息率' }
const fmt = (value: unknown, ratio = false) => typeof value === 'number' && Number.isFinite(value) ? (ratio ? `${(value * 100).toFixed(2)}%` : value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })) : typeof value === 'string' && value ? value : '—'
const time = (value: number | string | undefined | null) => value ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Hong_Kong', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '—'

function Card({ title, hint, section, loading, requestError, children, span }: { title: string; hint?: string; section?: HKSection; loading: boolean; requestError: boolean; children: ReactNode; span: string }) {
  const unavailable = section?.status === 'unavailable'
  return <section className={cn('min-w-0 overflow-hidden rounded-card border border-border bg-surface', span, unavailable && 'bg-base/60')}>
    <div className="border-b border-border px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-1">
        <h2 className={cn('text-xs font-semibold', unavailable ? 'text-secondary' : 'text-foreground')}>{title}</h2>
        <span className={cn('rounded border border-border px-1.5 py-0.5 font-mono text-[9px]', unavailable ? 'text-muted' : 'text-accent')}>{HK_MODE_LABELS[section?.mode ?? 'UNAVAILABLE']}</span>
      </div>
      {hint && <p className="mt-1 text-[10px] leading-relaxed text-muted">{hint}</p>}
      {section && <p className="mt-1 break-words text-[9px] text-muted">{section.source} · 更新 {time(section.updated_at)}</p>}
    </div>
    <div className="min-w-0 p-3">
      {loading ? <p className="py-5 text-center text-xs text-muted">加载中…</p>
        : requestError ? <p className="py-5 text-xs text-warning">请求失败，请稍后重试</p>
          : !section || unavailable ? <p className="py-5 text-xs leading-relaxed text-muted">暂无可靠数据源<br />{section?.error}</p>
            : section.status === 'error' ? <p className="py-5 text-xs text-warning">暂时无法获取 · {hkError(section.error)}</p>
              : section.status === 'empty' ? <p className="py-5 text-xs text-muted">{section.error || '暂无数据'}</p>
                : children}
    </div>
  </section>
}

export function HongKongDashboard({ onMarketChange }: { onMarketChange: (market: Market) => void }) {
  const [focus, setFocus] = useState<string>()
  const [sort, setSort] = useState<'change_pct' | 'amount'>('change_pct')
  const query = useQuery({ queryKey: QK.hkDashboard(focus), queryFn: () => api.hkDashboard(focus), staleTime: 30000, refetchInterval: 30000, retry: false })
  const data = query.data
  const rows = (key: HKSectionKey): HKRow[] => Array.isArray(data?.[key].data) ? data[key].data as HKRow[] : []
  const effectiveFocus = focus || data?.focus_symbol
  const stockMetadata = new Map(rows('daily_stocks').map(row => [row.symbol, row]))
  const stockName = (row: HKRow) => hkStockName(row, stockMetadata.get(row.symbol))
  const content = (key: HKSectionKey) => {
    if (key === 'daily_stocks') {
      const sorted = [...rows(key)].sort((a, b) => (Number(b[sort] ?? -Infinity)) - (Number(a[sort] ?? -Infinity)))
      return <>
        <label className="mb-2 flex items-center gap-2 text-[10px] text-muted">排序<select aria-label="股票排序" value={sort} onChange={event => setSort(event.target.value as typeof sort)} className="rounded-btn border border-border bg-base px-2 py-1 text-secondary"><option value="change_pct">涨跌幅</option><option value="amount">成交额</option></select></label>
        <div className="max-h-72 max-w-full overflow-auto">
          <table className="w-full whitespace-nowrap text-[10px] tabular-nums">
            <thead className="text-muted"><tr>{['股票 / 代码', '最新价', '涨跌幅', '今开', '最高', '最低', '成交额', '更新时间'].map(label => <th key={label} className="px-2 py-2 text-left font-normal">{label}</th>)}</tr></thead>
            <tbody>{sorted.map(row => <tr key={row.symbol} className={cn('border-t border-border', row.symbol === effectiveFocus && 'bg-accent/10')}>
              <td className="px-2 py-2"><button type="button" onClick={() => setFocus(row.symbol)} aria-pressed={row.symbol === effectiveFocus} className="text-left text-accent hover:underline"><span className="block">{stockName(row)}</span><span className="font-mono text-muted">{row.symbol}</span></button></td>
              {[row.last_price, row.change_pct, row.open, row.high, row.low, row.amount].map((value, index) => <td key={index} className="px-2 py-2">{fmt(value, index === 1)}</td>)}<td className="px-2 py-2 text-muted">{time(row.timestamp)}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </>
    }
    if (key === 'fundamentals') {
      const values = data?.fundamentals.data as HKRow | null
      return <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px] sm:grid-cols-3">{Object.entries(fields).map(([field, label]) => <div key={field} className="min-w-0"><dt className="text-[10px] text-muted">{label}</dt><dd className="break-words text-secondary">{field === 'name' && values ? stockName(values) : fmt(values?.[field])}</dd></div>)}</dl>
    }
    if (key === 'capital_flow') {
      const lines = rows(key)
      const values = lines.map(row => row.inflow).filter((value): value is number => typeof value === 'number')
      const max = Math.max(...values.map(Math.abs), 1)
      const points = lines.map((row, index) => `${(index / Math.max(lines.length - 1, 1)) * 500},${65 - Number(row.inflow ?? 0) / max * 50}`).join(' ')
      return <div><p className="text-[11px] text-secondary">焦点 {effectiveFocus || '—'} · 分钟净流入序列（以源数据时间为准）</p><svg role="img" aria-label="官方资金流序列" viewBox="0 0 500 130" className="mt-3 h-32 w-full"><line x1="0" y1="65" x2="500" y2="65" className="stroke-border" /><polyline points={points} fill="none" className="stroke-accent" strokeWidth="2" /></svg><p className="text-[10px] text-muted">序列 {time(lines[0]?.timestamp)} — {time(lines.at(-1)?.timestamp)} · 流入/流出拆分未由本接口提供</p></div>
    }
    return <div className="max-h-64 space-y-2 overflow-auto text-[11px]">{rows(key).map((row, index) => <div key={`${row.symbol}-${index}`} className="border-b border-border pb-2 last:border-0">
      <div className="flex flex-wrap justify-between gap-1"><span className="font-mono text-accent">{stockName(row)}</span><span>{row.net_inflow !== undefined ? fmt(row.net_inflow) : fmt(row.change_pct, true)}</span></div>
      {key === 'movers' && <p className="mt-1 text-[10px] text-muted">{row.symbol} · 最新价 {fmt(row.last_price)} · 类型 {fmt(row.alert_type)}</p>}
      {row.description && <p className="mt-1 break-words text-secondary">{row.description}</p>}
      {row.reason && <p className="mt-1 break-words text-secondary">{hkReason(row.reason)}</p>}
      {row.ex_date && <p className="mt-1 text-[10px] text-muted">除净 {row.ex_date} · 派息 {row.payment_date || '—'} · 登记 {row.record_date || '—'}</p>}
      {row.timestamp && <p className="mt-1 text-[10px] text-muted">{time(row.timestamp)} · {row.labels?.map(label => hkIndustry(label)).join(' / ')}</p>}
    </div>)}</div>
  }
  const label = marketSessionLabel(data?.market)
  return <div className="min-h-full min-w-0 bg-base p-3">
    <header className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-card border border-border bg-surface px-3 py-2">
      <h1 className="text-lg font-semibold text-foreground">港股市场</h1>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-secondary"><span className="text-accent">{label}</span><span>香港本地时间 {time(data?.market.local_time)}</span><span>Longbridge</span><span>最后更新 {time(data?.updated_at)}</span><span>焦点股票 {effectiveFocus || '—'}</span><button type="button" onClick={() => query.refetch()} disabled={query.isFetching} className="rounded-btn border border-border px-2 py-1 disabled:opacity-50">刷新</button></div>
    </header>
    <MarketSwitcherBar value="HK" enabledMarkets={['CN', 'HK', 'US']} onChange={onMarketChange} className="mb-3 rounded-card border px-3" />
    <p className="mb-3 text-[10px] text-muted">{calendarLabel(data?.market)}。行情可能为最近交易日快照，请查看数据时间。</p>
    <div className="grid min-w-0 grid-cols-1 gap-3 xl:grid-cols-12">{sections.map(({ key, ...item }) => <Card key={key} {...item} section={data?.[key]} loading={query.isLoading} requestError={query.isError}>{content(key)}</Card>)}</div>
  </div>
}
