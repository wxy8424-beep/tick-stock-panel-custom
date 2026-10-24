import { useId, useState, type FormEvent } from 'react'
import type { MarketSnapshotRow, USSection } from '@/lib/api'
import type { ColumnConfig } from '@/lib/list-columns'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'

const columns: ColumnConfig[] = [
  ['symbol', '证券代码'], ['name', '名称'], ['close', '快照价'], ['change_pct', '涨跌幅'],
  ['amount', '成交额'], ['currency', '币种'], ['timestamp', '报价时间'],
].map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
const numeric = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value : null
const emptyDraft = () => ({ currency: '', priceMin: '', priceMax: '', changeMin: '', changeMax: '' })
type AppliedConditions = { currency: string; priceMin: number | null; priceMax: number | null; changeMin: number | null; changeMax: number | null }
const emptyConditions = (): AppliedConditions => ({ currency: '', priceMin: null, priceMax: null, changeMin: null, changeMax: null })
const bound = (value: string) => {
  const trimmed = value.trim()
  if (!trimmed) return null
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(trimmed) || !Number.isFinite(Number(trimmed))) throw new Error('边界必须为有限十进制数值')
  return Number(trimmed)
}
const inRange = (value: unknown, lower: number | null, upper: number | null) => {
  if (lower === null && upper === null) return true
  const number = numeric(value)
  return number !== null && (lower === null || number >= lower) && (upper === null || number <= upper)
}
const currencyOf = (row: MarketSnapshotRow) => typeof row.currency === 'string' ? row.currency.trim() : ''
const numberText = (value: unknown, percent = false) => {
  const number = numeric(value), scaled = number === null ? null : number * (percent ? 100 : 1)
  return scaled !== null && Number.isFinite(scaled) ? `${scaled.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}${percent ? '%' : ''}` : '— · 未提供或无效'
}
const text = (value: unknown) => typeof value === 'string' && value.trim() ? value : '— · 未提供'
const time = (value: unknown) => {
  const number = numeric(value)
  return number !== null && number > 0 && Number.isFinite(new Date(number).getTime())
    ? new Intl.DateTimeFormat('zh-CN', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(new Date(number))
    : '— · 未提供或无效'
}

/** Format/market consistency only, not proof of listing. No requests or persistence. */
function validRows(section?: USSection): MarketSnapshotRow[] {
  if (section?.status !== 'ok' || !Array.isArray(section.data)) return []
  const seen = new Set<string>()
  return section.data.filter((row): row is MarketSnapshotRow => {
    if (!row || typeof row !== 'object' || typeof row.symbol !== 'string'
      || !/^[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*-?\.US$/.test(row.symbol)
      || (row.market != null && row.market !== 'US') || seen.has(row.symbol)) return false
    seen.add(row.symbol)
    return true
  })
}

export function USRankingPanel({ title, section, loading, failed, retained = false, href, onOpen, onClose }: {
  title: string; section?: USSection; loading: boolean; failed: boolean; retained?: boolean
  href: (symbol: string) => string
  onOpen: (row: MarketSnapshotRow, rows: MarketSnapshotRow[]) => void
  onClose: () => void
}) {
  const id = useId(), [search, setSearch] = useState('')
  const [draft, setDraft] = useState(emptyDraft), [conditions, setConditions] = useState(emptyConditions), [conditionError, setConditionError] = useState('')
  const { sort, toggle, sortRows } = useTableSort<MarketSnapshotRow>((row, col) => ['close', 'change_pct', 'amount', 'timestamp'].includes(col.id) ? numeric(row[col.id]) : typeof row[col.id] === 'string' ? row[col.id] : null)
  const rows = validRows(section)
  const currencies = [...new Set(rows.map(currencyOf).filter(Boolean))].sort()
  const apply = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    try {
      const next: AppliedConditions = { currency: draft.currency, priceMin: bound(draft.priceMin), priceMax: bound(draft.priceMax), changeMin: bound(draft.changeMin), changeMax: bound(draft.changeMax) }
      if ((next.priceMin !== null || next.priceMax !== null) && !next.currency) throw new Error('价格范围请先选择明确币种')
      if ((next.priceMin !== null && next.priceMax !== null && next.priceMin > next.priceMax) || (next.changeMin !== null && next.changeMax !== null && next.changeMin > next.changeMax)) throw new Error('下限不能大于上限')
      setConditions(next); setConditionError('')
    } catch (error) { setConditionError(`条件未应用：${(error as Error).message}；仍显示上次有效条件。`) }
  }
  const filtered = sortRows(rows.filter(row => `${row.symbol} ${typeof row.name === 'string' ? row.name : ''}`.toLowerCase().includes(search.trim().toLowerCase()))
    .filter(row => (!conditions.currency || currencyOf(row) === conditions.currency)
      && inRange(row.close, conditions.priceMin, conditions.priceMax)
      && inRange(row.change_pct, conditions.changeMin === null ? null : conditions.changeMin / 100, conditions.changeMax === null ? null : conditions.changeMax / 100)), columns)
  const appliedText = [conditions.currency && `币种 ${conditions.currency}`,
    (conditions.priceMin !== null || conditions.priceMax !== null) && `价格 ${conditions.priceMin ?? '不限'} 至 ${conditions.priceMax ?? '不限'}（原币）`,
    (conditions.changeMin !== null || conditions.changeMax !== null) && `涨跌幅 ${conditions.changeMin ?? '不限'} 至 ${conditions.changeMax ?? '不限'}%`].filter(Boolean).join(' · ') || '无条件（仍按搜索文本过滤）'
  const malformed = section?.status === 'ok' && !Array.isArray(section.data)
  const countsKnown = section?.status === 'empty' || (section?.status === 'ok' && Array.isArray(section.data))
  const sectionTime = typeof section?.updated_at === 'string' && /T.*(?:Z|[+-]\d\d:\d\d)$/.test(section.updated_at) ? Date.parse(section.updated_at) : NaN
  return <section aria-label="美股已返回榜单" className="mb-2 min-w-0 space-y-2 rounded-card border border-border bg-surface p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="min-w-0 break-words text-sm font-semibold">{title} · 已返回记录</h2><button type="button" aria-label="关闭已返回榜单" onClick={onClose} className="rounded-btn border border-border px-3 py-1 text-xs">关闭榜单</button></div>
    <p role="note" className="break-words text-xs text-muted">仅查看本次接口已返回的榜单记录，不是全市场筛选，不补抓证券或运行策略。原榜单卡片仍显示前 8 条。仅检查代码格式与市场一致性，不证明上市身份。成交额为原币数值，不换汇或计算跨币种总额。</p>
    <p className="break-words text-xs">榜单来源：{text(section?.source)} · 区段获取/生成时间：{time(sectionTime)}（America/New_York，不能替代报价时间或证明实时）</p>
    <p className="text-xs">{countsKnown ? <>有效 {rows.length} 条 · 匹配 {filtered.length} 条{Array.isArray(section?.data) && section?.status === 'ok' ? ` · 原始 ${section.data.length} 条，排除格式/市场冲突或重复 ${section.data.length - rows.length} 条` : ''}</> : '记录数量：— · 接口未提供有效榜单'}</p>
    <label htmlFor={id} className="block text-xs">搜索已返回证券</label>
    <input id={id} aria-label="搜索已返回证券" autoFocus value={search} onChange={event => setSearch(event.target.value)} placeholder="代码或名称" className="w-full min-w-0 max-w-md rounded-btn border border-border bg-base px-2 py-1.5 text-sm" />
    <form aria-label="已返回记录条件" onSubmit={apply} onReset={event => { event.preventDefault(); setDraft(emptyDraft()); setConditions(emptyConditions()); setConditionError('') }}>
      <fieldset className="min-w-0 rounded border border-border p-2">
        <legend className="px-1 text-xs">已返回记录条件 · 仅本地过滤</legend>
        <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-5">
          <label className="min-w-0 text-xs">币种（接口值）<select aria-label="按接口币种过滤" value={draft.currency} onChange={event => { setDraft({ ...draft, currency: event.target.value }); setConditionError('') }} className="mt-1 w-full min-w-0 rounded-btn border border-border bg-base p-2">
            <option value="">全部（含未知币种）</option>{currencies.map(currency => <option key={currency} value={currency}>{currency}</option>)}
            {draft.currency && !currencies.includes(draft.currency) && <option value={draft.currency}>{draft.currency}（本次未返回）</option>}
          </select></label>
          {([['priceMin', '价格下限（原币）'], ['priceMax', '价格上限（原币）'], ['changeMin', '涨跌幅下限（%）'], ['changeMax', '涨跌幅上限（%）']] as const).map(([key, label]) => <label key={key} className="min-w-0 text-xs">{label}<input aria-label={label} inputMode="decimal" autoComplete="off" value={draft[key]} onChange={event => { setDraft({ ...draft, [key]: event.target.value }); setConditionError('') }} aria-describedby={`${id}-condition-hint${conditionError ? ` ${id}-condition-error` : ''}`} aria-invalid={!!conditionError} className="mt-1 w-full min-w-0 rounded-btn border border-border bg-base p-2" /></label>)}
        </div>
        <p id={`${id}-condition-hint`} className="mt-2 text-xs text-muted">修改后点击应用；输入 2 表示 2%。价格范围须先选择币种；启用范围时排除该字段未知的记录，不把未知值当零。重置条件保留搜索和排序。</p>
        <div className="mt-2 flex flex-wrap gap-2"><button type="submit" className="rounded-btn border border-border px-3 py-1 text-xs">应用条件</button><button type="reset" className="rounded-btn border border-border px-3 py-1 text-xs">重置条件</button></div>
        {conditionError && <p id={`${id}-condition-error`} role="alert" className="mt-2 text-xs text-warning">{conditionError}</p>}
        <p role="status" className="mt-2 break-words text-xs">已应用条件：{appliedText}</p>
      </fieldset>
    </form>
    {failed && <p role="alert" className="text-xs text-warning">榜单请求失败；如有下表，为保留的缓存记录，不能视为实时行情。</p>}
    {retained && <p role="status" className="text-xs text-muted">正在切换报价，榜单暂保留前次接口已返回记录。</p>}
    {loading ? <p role="status">榜单加载中…</p> : malformed || !section || !['ok', 'empty'].includes(section.status)
      ? <ErrorState title="榜单暂不可用" hint={typeof section?.error === 'string' && section.error ? section.error : '接口未提供有效榜单；可使用看板原有重载操作重试。'} />
      : !filtered.length ? <EmptyState title={rows.length ? '没有匹配的已返回证券' : '接口没有返回可展示记录'} hint="搜索只作用于本榜单，不查询真实证券库或其他市场。" />
        : <div role="region" aria-label="榜单表格，可横向滚动" tabIndex={0} className="min-w-0 max-w-full overflow-x-auto">
          <StockDataTable columns={columns} rows={filtered} minWidth={760} sort={sort} onSortToggle={toggle} className="rounded-card border border-border"
            renderCell={(row: MarketSnapshotRow, col) => <td className="break-words p-2 text-xs">{col.id === 'symbol'
              ? <a className="text-accent underline" href={href(row.symbol)} onClick={event => { if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); onOpen(row, filtered) }}>{row.symbol}</a>
              : col.id === 'timestamp' ? time(row.timestamp) : ['close', 'change_pct', 'amount'].includes(col.id) ? numberText(row[col.id], col.id === 'change_pct') : text(row[col.id])}</td>} />
        </div>}
  </section>
}
