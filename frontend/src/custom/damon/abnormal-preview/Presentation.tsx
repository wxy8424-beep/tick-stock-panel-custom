import { useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Activity } from 'lucide-react'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import { fmtPct, priceColorClass } from '@/lib/format'
import { ANOMALY_TYPES, SEVERITY_LABELS } from '@/lib/anomalyPresentation'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadAbnormalPreview } from '../../../../tests/fixtures/abnormal_preview'
import { validateAbnormalPreview, type AbnormalPreviewMarket, type AbnormalPreviewRow, type AbnormalPreviewState } from './contract'

const columns: ColumnConfig[] = [['name', '名称 / 代码 / 市场'], ['event_type', '异动类型（样例）'], ['severity', '严重程度（样例）'], ['change_pct', '演示涨跌幅'], ['event_time', '固定事件时间 UTC'], ['source', '状态 / 来源 / 证据']]
  .map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
function sortValue(row: AbnormalPreviewRow, col: ColumnConfig) {
  if (col.id === 'severity') return row.severity === null ? null : ({ low: 1, medium: 2, high: 3 })[row.severity]
  return row[col.id as 'name' | 'event_type' | 'change_pct' | 'event_time' | 'source']
}
function Badge() { return <span className="rounded border border-warning/30 bg-warning/10 px-2 py-0.5 text-[10px] text-warning">PREVIEW · 合成异动样本</span> }
const stateLabel = (row: AbnormalPreviewRow) => row.sample_state === null ? '—（状态未知）' : row.sample_state === 'BLOCKED_SAMPLE' ? '阻塞样例（非真实事件）' : '观察样例（非真实事件）'
export function AbnormalPreview({ market, state, controls }: { market: AbnormalPreviewMarket; state: AbnormalPreviewState; controls?: ReactNode }) {
  const [type, setType] = useState('ALL'), [severity, setSeverity] = useState('ALL'), [search, setSearch] = useState(''), [selected, setSelected] = useState<string | null>(null)
  const { sort, toggle, sortRows } = useTableSort<AbnormalPreviewRow>(sortValue)
  const data = state.kind === 'ready' ? validateAbnormalPreview(state.data) : null
  if (data && data.market !== market) throw new Error('abnormal_preview_market_conflict')
  const rows = sortRows((data?.rows ?? []).filter(row => (type === 'ALL' || type === row.event_type) && (severity === 'ALL' || severity === (row.severity ?? 'UNKNOWN'))
    && `${row.symbol} ${row.name}`.toLowerCase().includes(search.trim().toLowerCase())), columns)
  const detail = rows.find(row => row.sample_id === selected) ?? rows[0]
  return <div data-abnormal-preview={market} className="flex min-h-0 flex-col">
    <PageHeader title={`${market} 异动监控 · Preview`} subtitle={`固定 Preview 交易日：${data?.trading_date ?? '—（未载入样稿）'}`}
      titleExtra={<Badge />} right={<button disabled title="Preview 模式不可执行：不创建真实告警规则" className="rounded-btn border border-border px-3 py-1 text-xs text-muted">告警规则（Preview 不可执行）</button>} />
    {controls}
    <div className="space-y-4 px-5 py-4">
      <aside aria-label="异动演示声明" className="rounded-card border border-warning/30 bg-warning/5 p-4 text-xs leading-relaxed text-warning">
        <p>演示数据｜非生产行情｜不构成真实异动事件或投资信号</p><p>独立固定 synthetic fixture，不运行检测器，不触发提醒或外部通知；生产检测与时段状态未验证。</p>
        <p>快速价格异动、日内观测突破、波动扩张均仅展示预编写样本；不套用 A 股涨停、竞价或交易所累计偏离规则。</p>
      </aside>
      {state.kind === 'loading' ? <p role="status" className="py-8 text-center text-muted">异动 Preview 加载中…</p>
        : state.kind === 'error' ? <ErrorState title="异动 Preview 加载失败" hint="不会回退真实异动、行情或告警接口。" />
          : !data?.rows.length ? <EmptyState icon={Activity} title="暂无异动演示样本" hint="合成 fixture 为空，不表示真实市场没有异动。" />
            : <>
              <section aria-label="演示异动筛选" className="flex flex-wrap items-center gap-3 rounded-card border border-border bg-surface p-3 text-xs">
                <select aria-label="演示异动类型" value={type} onChange={e => setType(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部类型</option>{Object.entries(ANOMALY_TYPES).map(([key, label]) => <option key={key} value={key}>{label}（样例）</option>)}</select>
                <select aria-label="演示异动严重程度" value={severity} onChange={e => setSeverity(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部严重程度</option>{Object.entries(SEVERITY_LABELS).map(([key, label]) => <option key={key} value={key}>{label}（样例）</option>)}<option value="UNKNOWN">未知</option></select>
                <input aria-label="搜索异动样本" placeholder="证券名称 / 代码" value={search} onChange={e => setSearch(e.target.value)} className="rounded-btn border border-border bg-base p-2" />
                <span className="text-muted">{rows.length} 条 · 排序：{columns.find(c => c.id === sort?.key)?.label ?? '样稿顺序'} {sort?.dir === 'asc' ? '↑' : sort?.dir === 'desc' ? '↓' : ''}</span>
              </section>
              {!rows.length ? <EmptyState title="暂无匹配的异动样本" hint="仅筛选当前市场的合成集合。" /> : <StockDataTable columns={columns} rows={rows} rowKey={(row: AbnormalPreviewRow) => row.sample_id} sort={sort} onSortToggle={toggle}
                renderCell={(row: AbnormalPreviewRow, col) => <td data-abnormal-field={col.id} className="px-3 py-3 align-top text-xs text-secondary">
                  {col.id === 'name' ? <button data-sample-id={row.sample_id} aria-pressed={detail?.sample_id === row.sample_id} onClick={() => setSelected(row.sample_id)} className="text-left text-accent"><strong className="block">{row.name}</strong><span className="font-mono">{row.symbol} · {row.market}</span></button>
                    : col.id === 'event_type' ? ANOMALY_TYPES[row.event_type]
                      : col.id === 'severity' ? (row.severity === null ? '—（严重程度未知）' : SEVERITY_LABELS[row.severity])
                        : col.id === 'change_pct' ? <><span className={`font-mono ${priceColorClass(row.change_pct)}`}>{fmtPct(row.change_pct)}</span>{row.change_pct === null && row.reasons.map(reason => <p key={reason} className="text-warning">{reason}</p>)}</>
                          : col.id === 'event_time' ? <>{row.event_time ?? '—（样稿时间未提供）'}{row.event_time === null && row.reasons.map(reason => <p key={reason} className="text-warning">{reason}</p>)}</>
                            : <><Badge /><p>{stateLabel(row)}</p><p>{row.source}</p><p className="break-all text-[10px] text-muted">{row.evidence}</p></>}
                </td>} />}
              <section aria-label="异动样本详情" className="space-y-2 rounded-card border border-border bg-surface p-4 text-xs text-secondary">
                <h2 className="text-sm font-semibold">事件详情 · 只读合成样本</h2>
                {!detail ? <p>暂无选中的异动样本</p> : <>
                  <p>{detail.name} · {detail.symbol} · {detail.market} · {ANOMALY_TYPES[detail.event_type]}</p><p>{stateLabel(detail)} · <Badge /></p>
                  <p>演示触发条件：{detail.condition_description}</p><p>固定事件时间 UTC：{detail.event_time ?? '—'} · 演示涨跌幅：{fmtPct(detail.change_pct)}</p>
                  <p>source: {detail.source} · data_mode: preview · is_production: false · is_investment_signal: false</p><p className="break-all">evidence: {detail.evidence}</p>
                  <p>missing_fields: {detail.missing_fields.join('、') || '无（仅此样稿）'}</p>{detail.reasons.map(reason => <p key={reason} className="text-warning">{reason}</p>)}
                  {detail.blockers.map(reason => <p key={reason} className="text-warning">blocker: {reason}</p>)}{detail.warnings.map(reason => <p key={reason} className="text-muted">warning: {reason}</p>)}
                </>}
              </section>
              <p className="text-xs text-muted">source: {data.source} · PREVIEW · trading_date: {data.trading_date} · generated_at: {data.generated_at}（固定样稿时间）</p>
            </>}
    </div>
  </div>
}
function FixtureAbnormal({ market, controls }: { market: AbnormalPreviewMarket; controls: ReactNode }) {
  let state: AbnormalPreviewState
  try { state = { kind: 'ready', data: loadAbnormalPreview(market) } } catch { state = { kind: 'error' } }
  return <AbnormalPreview market={market} state={state} controls={controls} />
}
export function AbnormalMarkets({ cn }: { cn: (active: boolean, controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams(), requested = params.get('market')
  const market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const [visited, setVisited] = useState<readonly Market[]>([market])
  useEffect(() => { setVisited(old => old.includes(market) ? old : [...old, market]) }, [market])
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']} onChange={next => setParams(old => { const copy = new URLSearchParams(old); copy.set('market', next); return copy })} />
  return <div className="h-full min-h-0">{(['CN', 'HK', 'US'] as const).filter(m => visited.includes(m) || m === market).map(m => <div key={m} hidden={market !== m} data-abnormal-market={m} className="h-full min-h-0">{m === 'CN' ? cn(market === 'CN', controls) : <FixtureAbnormal market={m} controls={controls} />}</div>)}</div>
}
