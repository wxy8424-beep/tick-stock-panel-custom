import { useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CalendarClock } from 'lucide-react'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import { fmtPct, priceColorClass } from '@/lib/format'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadLotsPreview } from '../../../../tests/fixtures/lots_preview'
import { lotValueLabels, validateLotsPreview, type LotPreviewRow, type LotSampleValue, type LotsPreviewMarket, type LotsPreviewState } from './contract'

const card = 'min-w-0 rounded-xl border border-border bg-surface/40 p-4'
const numeric = (v: number | null) => v === null ? '—' : v.toFixed(2)
const reminderLabel = (row: LotPreviewRow) => row.reminder.sample_state === null ? '—（提醒状态未知）' : row.reminder.sample_state === 'PENDING_SAMPLE' ? '待观察样例（非真实提醒）' : '阻塞样例（非真实风险结论）'
const columns: ColumnConfig[] = [['name', '标的 / 市场'], ['qty', '数量（合成股数）'], ['cost_price', '成本价（演示）'], ['reference_price', '参考价格（演示）'], ['pnl_amount', '演示盈亏金额'], ['pnl_pct', '演示盈亏比例'], ['sample_state', '提醒状态（样例）'], ['source', '来源 / 证据']]
  .map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
function sortValue(row: LotPreviewRow, col: ColumnConfig) {
  if (col.id === 'name' || col.id === 'source') return row[col.id]
  if (col.id === 'sample_state') return row.reminder.sample_state
  return row.values[col.id as LotSampleValue]
}
function Badge() { return <span className="rounded border border-warning/30 bg-warning/10 px-2 py-0.5 text-[10px] text-warning">PREVIEW · 非真实账户</span> }
function Disabled({ children }: { children: ReactNode }) { return <button disabled title="Preview 模式不可执行：不修改真实批次或提醒规则" className="rounded-btn border border-border px-3 py-1.5 text-xs text-muted">{children}（Preview 不可执行）</button> }
export function LotsPreview({ market, state, controls }: { market: LotsPreviewMarket; state: LotsPreviewState; controls?: ReactNode }) {
  const [search, setSearch] = useState(''), [filter, setFilter] = useState('ALL'), [selected, setSelected] = useState<string | null>(null)
  const { sort, toggle, sortRows } = useTableSort<LotPreviewRow>(sortValue)
  const data = state.kind === 'ready' ? validateLotsPreview(state.data) : null
  if (data && data.market !== market) throw new Error('lots_preview_market_conflict')
  const rows = sortRows((data?.rows ?? []).filter(row => `${row.symbol} ${row.name} ${row.reminder.name}`.toLowerCase().includes(search.trim().toLowerCase())
    && (filter === 'ALL' || filter === (row.reminder.sample_state ?? 'UNKNOWN'))), columns)
  const detail = rows.find(row => row.sample_id === selected) ?? rows[0]
  return <div data-lots-preview={market} className="flex min-h-0 flex-col">
    <PageHeader title={`${market} 持仓提醒 · Preview`} subtitle={`固定演示交易日：${data?.trading_date ?? '—（未载入样稿）'}`} titleExtra={<Badge />} right={<Disabled>新增批次</Disabled>} />
    {controls}
    <div className="mx-auto w-full max-w-[1440px] space-y-4 px-5 py-4">
      <aside aria-label="持仓演示声明" className="rounded-xl border border-warning/30 bg-warning/5 p-4 text-xs leading-relaxed text-warning">
        <p>演示数据｜非真实账户持仓｜非生产行情｜不构成投资建议</p><p>持仓、数量、价格、盈亏和风险提示均为固定 synthetic fixture，不来自券商账户，不判定真实触发。</p>
        <p>不发送通知、不执行交易、不生成真实提醒规则。固定检查时间不是当前账户检查时间。</p>
      </aside>
      {state.kind === 'loading' ? <p role="status" className="py-8 text-center text-muted">持仓 Preview 加载中…</p>
        : state.kind === 'error' ? <ErrorState title="持仓 Preview 加载失败" hint="不回退真实账户、批次、行情或提醒接口。" />
          : !data?.rows.length ? <EmptyState icon={CalendarClock} title="暂无持仓演示样本" hint="fixture 为空，不表示真实账户没有持仓。" />
            : <>
              <section aria-label="演示持仓概览" className={`${card} space-y-3 text-xs`}>
                <h2 className="text-sm font-semibold">{market} · {data.overview.position_count} 个合成批次 · {data.currency}（演示币种）</h2>
                <p className="text-warning">以下金额仅为已知样稿子集：{data.overview.valued_count} / {data.overview.position_count} 个批次，不是全部持仓或真实账户净值。</p>
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[['known_cost_amount', '已知子集成本'], ['known_reference_amount', '已知子集参考市值'], ['known_pnl_amount', '已知子集演示盈亏'], ['total_pnl_amount', '全部批次演示盈亏']] .map(([key, label]) => <div key={key} data-lot-overview={key} className="rounded-btn bg-elevated/30 p-3"><p className="text-muted">{label}</p><p className="mt-1 font-mono text-lg">{numeric(data.overview[key as 'known_cost_amount'])} {data.currency}</p></div>)}</div>
                <p className="text-warning">{data.overview.missing_reason}</p>
              </section>
              <section aria-label="演示持仓筛选" className="flex flex-wrap items-center gap-3 text-xs">
                <input aria-label="搜索持仓样稿" placeholder="代码 / 名称 / 提醒" value={search} onChange={e => setSearch(e.target.value)} className="rounded-btn border border-border bg-base p-2" />
                <select aria-label="演示提醒状态" value={filter} onChange={e => setFilter(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部样稿</option><option value="PENDING_SAMPLE">待观察样例</option><option value="BLOCKED_SAMPLE">阻塞样例</option><option value="UNKNOWN">未知状态</option></select>
                <span className="text-muted">{rows.length} 条 · 排序：{columns.find(c => c.id === sort?.key)?.label ?? '样稿顺序'} {sort?.dir === 'asc' ? '↑' : sort?.dir === 'desc' ? '↓' : ''}</span>
              </section>
              {!rows.length ? <EmptyState title="暂无匹配的持仓提醒样本" /> : <StockDataTable columns={columns} rows={rows} rowKey={(row: LotPreviewRow) => row.sample_id} sort={sort} onSortToggle={toggle}
                renderCell={(row: LotPreviewRow, col) => <td data-lot-field={col.id} className="px-3 py-3 align-top text-xs text-secondary">
                  {col.id === 'name' ? <button data-lot-id={row.sample_id} aria-pressed={detail?.sample_id === row.sample_id} onClick={() => setSelected(row.sample_id)} className="text-left text-accent"><strong className="block">{row.name}</strong><span className="font-mono">{row.symbol} · {row.market} · {row.currency}</span></button>
                    : col.id === 'sample_state' ? reminderLabel(row)
                      : col.id === 'source' ? <><Badge /><p>{row.source}</p><p className="break-all text-[10px] text-muted">{row.evidence}</p></>
                        : <><span className={`font-mono ${col.id.startsWith('pnl') ? priceColorClass(row.values[col.id as LotSampleValue]) : ''}`}>{col.id === 'pnl_pct' ? fmtPct(row.values.pnl_pct) : numeric(row.values[col.id as LotSampleValue])}</span>{row.values[col.id as LotSampleValue] === null && row.reasons.map(r => <p key={r} className="text-warning">{r}</p>)}</>}
                </td>} />}
              <section aria-label="演示提醒列表" className={`${card} space-y-3 text-xs`}>
                <h2 className="text-sm font-semibold">提醒样本（随当前筛选展示）</h2>
                {!rows.length ? <p className="text-muted">暂无匹配的提醒样本</p> : rows.map(row => <article key={row.sample_id} className="rounded-lg border border-border p-3">
                  <h3 className="font-semibold">{row.reminder.name} · {row.symbol}</h3><p>{reminderLabel(row)}</p><p className="mt-1">{row.reminder.condition_description}</p>
                  <p>固定检查时间 UTC：{row.reminder.checked_at ?? '—（样稿未提供）'}</p><p>source: {row.reminder.source} · {row.reminder.status}</p><p className="break-all">evidence: {row.reminder.evidence}</p>
                  {row.reasons.map(r => <p key={r} className="text-warning">{r}</p>)}
                </article>)}
              </section>
              <section aria-label="持仓样本详情" className={`${card} space-y-2 text-xs text-secondary`}>
                <h2 className="text-sm font-semibold">详情 / 风险提示 / 规则查看 · 只读演示</h2>
                {!detail ? <p>暂无选中的样稿</p> : <>
                  <p>{detail.name} · {detail.symbol} · {detail.market} · {detail.currency}（演示币种）</p><Badge />
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{(['stop_price', 'target_price', 'drawdown_pct', 'concentration_pct'] as const).map(key => <div key={key} className="rounded-btn bg-elevated/30 p-2">{lotValueLabels[key]}（演示）：{key.endsWith('_pct') ? fmtPct(detail.values[key]) : numeric(detail.values[key])}</div>)}</div>
                  <p>风险线 / 回撤为预编写样稿，不从历史或盘中数据计算，不表示实际止损/止盈建议。</p>
                  <details><summary className="cursor-pointer text-accent">查看提醒规则结构（现有 Lot 字段，仅样稿）</summary>
                    <p>target_pct：{detail.rule_sample.target_pct ?? '—'} % · stop_pct：{detail.rule_sample.stop_pct ?? '—'} %（百分数值，非小数）</p>
                    <p>remind_date：{detail.rule_sample.remind_date ?? '—'} · lead_days：{detail.rule_sample.lead_days ?? '—'}</p><p>只读字段，不保存或生成任何 MonitorRule，不以系统日期计算剩余天数。</p>
                  </details>
                  <p>missing_fields: {detail.missing_fields.join('、') || '无（仅样稿）'}</p>{detail.reasons.map(r => <p key={r} className="text-warning">{r}</p>)}
                  <p className="break-all">source: {detail.source} · evidence: {detail.evidence}</p>{detail.blockers.map(r => <p key={r} className="text-warning">blocker: {r}</p>)}{detail.warnings.map(r => <p key={r} className="text-muted">warning: {r}</p>)}
                  <div className="flex flex-wrap gap-2"><Disabled>编辑批次</Disabled><Disabled>删除批次</Disabled></div>
                </>}
              </section>
              <p className="text-xs text-muted">source: {data.source} · PREVIEW · trading_date: {data.trading_date} · generated_at: {data.generated_at}（固定样稿时间） · data_mode: preview · is_production: false · is_investment_signal: false</p>
            </>}
    </div>
  </div>
}
function FixtureLots({ market, controls }: { market: LotsPreviewMarket; controls: ReactNode }) {
  let state: LotsPreviewState
  try { state = { kind: 'ready', data: loadLotsPreview(market) } } catch { state = { kind: 'error' } }
  return <LotsPreview market={market} state={state} controls={controls} />
}
export function LotsMarkets({ cn }: { cn: (active: boolean, controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams(), requested = params.get('market')
  const market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const [visited, setVisited] = useState<readonly Market[]>([market])
  useEffect(() => { setVisited(old => old.includes(market) ? old : [...old, market]) }, [market])
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']} onChange={next => setParams(old => { const copy = new URLSearchParams(old); copy.set('market', next); return copy })} />
  return <div className="h-full min-h-0">{(['CN', 'HK', 'US'] as const).filter(m => visited.includes(m) || m === market).map(m => <div key={m} hidden={market !== m} data-lots-market={m} className="h-full min-h-0">{m === 'CN' ? cn(market === 'CN', controls) : <FixtureLots market={m} controls={controls} />}</div>)}</div>
}
