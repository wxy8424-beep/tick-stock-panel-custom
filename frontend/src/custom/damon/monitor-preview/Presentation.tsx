import { useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BellRing, ListChecks } from 'lucide-react'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadMonitorPreview } from '../../../../tests/fixtures/monitor_preview'
import { sampleStateLabel, validateMonitorPreview, type MonitorMarket, type MonitorPreviewState, type MonitorTaskSample } from './contract'

const card = 'min-w-0 rounded-xl border border-border bg-surface/40 p-4 shadow-lg shadow-black/5'
const columns: ColumnConfig[] = [['name', '监控项 / 标的'], ['sample_state', '状态（样例）'], ['severity', '严重程度（样例）'], ['checked_at', '检查时间（固定样稿 UTC）'], ['source', '来源 / 证据']]
  .map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
const sortValue = (row: MonitorTaskSample, col: ColumnConfig) => row[col.id as 'name' | 'sample_state' | 'severity' | 'checked_at' | 'source']
function Badge() { return <span className="rounded border border-warning/30 bg-warning/10 px-2 py-0.5 text-[10px] text-warning">PREVIEW · 合成样本</span> }
function Disabled({ children }: { children: ReactNode }) {
  return <button disabled title="Preview 模式不可执行" className="rounded-btn border border-border px-2 py-1 text-xs text-muted disabled:cursor-not-allowed">{children}（Preview 模式不可执行）</button>
}
export function MonitorPreview({ market, state, controls }: { market: MonitorMarket; state: MonitorPreviewState; controls?: ReactNode }) {
  const [search, setSearch] = useState('')
  const [severity, setSeverity] = useState('ALL')
  const [taskState, setTaskState] = useState('ALL')
  const [selected, setSelected] = useState<string | null>(null)
  const { sort, toggle, sortRows } = useTableSort<MonitorTaskSample>(sortValue)
  const data = state.kind === 'ready' ? validateMonitorPreview(state.data) : null
  if (data && data.market !== market) throw new Error('monitor_preview_market_conflict')
  const matches = (symbol: string, name: string, level: string | null) => `${symbol} ${name}`.toLowerCase().includes(search.trim().toLowerCase()) && (severity === 'ALL' || severity === (level ?? 'UNKNOWN'))
  const tasks = sortRows((data?.tasks ?? []).filter(t => matches(t.symbol, t.name, t.severity) && (taskState === 'ALL' || taskState === t.sample_state)), columns)
  const alerts = (data?.alerts ?? []).filter(a => matches(a.symbol, a.title, a.severity))
  const detail = tasks.find(t => t.id === selected) ?? tasks[0]
  return <div data-monitor-preview={market} className="flex min-h-0 flex-col">
    <PageHeader className="pl-14 md:pl-5 [&>div>div]:flex-wrap md:[&>div>div]:flex-nowrap"
      title={`${market} 监控中心 · Preview`} subtitle="只读合成任务与告警样本" titleExtra={<Badge />} />
    {controls}
    <div className="space-y-4 px-5 py-4">
      <aside aria-label="监控演示声明" className="rounded-xl border border-warning/30 bg-warning/5 p-4 text-xs leading-relaxed text-warning">
        <p>演示数据｜非生产状态｜不构成真实告警或投资信号</p>
        <p>真实 Worker 状态：未观测；真实服务健康：未观测。下列状态仅为预编写样稿，不表示任何任务正在运行。</p>
        <p>无真实通知、订单、持仓或告警确认操作。固定样稿时间不表示当前或最近真实检查。</p>
      </aside>
      {state.kind === 'loading' ? <p role="status" className="py-8 text-center text-muted">监控 Preview 加载中…</p>
        : state.kind === 'error' ? <ErrorState title="监控 Preview 加载失败" hint="不回退真实任务、Worker 或告警接口。" />
          : !data || (!data.tasks.length && !data.alerts.length) ? <EmptyState icon={ListChecks} title="暂无监控演示样本" hint="fixture 为空，不代表真实监控系统没有任务。" />
            : <>
              <section aria-label="监控演示概览" className={`${card} space-y-3`}>
                <h2 className="text-sm font-semibold">{market} · 交易日：{data.trading_date} · 固定 Preview 日期</h2>
                <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">{(['total', 'NORMAL', 'WARNING', 'ERROR', 'UNAVAILABLE'] as const).map(key => <div key={key} data-monitor-count={key} className="rounded-btn bg-elevated/40 p-3">
                  <p className="text-xs text-muted">{key === 'total' ? '监控项总数（样稿）' : sampleStateLabel[key]}</p><p className="mt-1 font-mono text-xl">{data.counts[key].value ?? '—'}</p>
                  {data.counts[key].reason && <p className="text-xs text-warning">{data.counts[key].reason}</p>}
                </div>)}</div>
                <p className="text-xs text-muted">样稿更新时间（固定 UTC）：{data.updated_at ?? '—'} {data.updated_reason}</p>
                <p className="break-all text-xs text-muted">{data.status} · source: {data.source} · evidence: {data.evidence}</p>
              </section>
              <div className="flex flex-wrap items-center gap-3 text-xs">
                <input aria-label="搜索监控样稿" placeholder="证券 / 任务 / 告警名称" value={search} onChange={e => setSearch(e.target.value)} className="rounded-btn border border-border bg-elevated px-3 py-1.5" />
                <label>严重程度（任务及告警）：<select aria-label="演示严重程度" value={severity} onChange={e => setSeverity(e.target.value)} className="rounded-btn border border-border bg-elevated px-2 py-1">
                  <option value="ALL">全部</option><option value="INFO">INFO 样例</option><option value="WARN">WARN 样例</option><option value="CRITICAL">CRITICAL 样例</option><option value="UNKNOWN">未知</option>
                </select></label>
                <label>任务状态：<select aria-label="演示任务状态" value={taskState} onChange={e => setTaskState(e.target.value)} className="rounded-btn border border-border bg-elevated px-2 py-1">
                  <option value="ALL">全部</option>{Object.entries(sampleStateLabel).map(([key, text]) => <option key={key} value={key}>{text}</option>)}
                </select></label>
              </div>
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
                <section aria-label="合成告警列表" className={`${card} space-y-3`}>
                  <div className="flex flex-wrap items-center gap-2"><BellRing className="h-4 w-4 text-accent" /><h2 className="text-sm font-semibold">合成告警样本 · {alerts.length}</h2><Badge /></div>
                  {!alerts.length ? <EmptyState title="暂无匹配的合成告警" /> : alerts.map(a => <article key={a.id} className="rounded-lg border border-border bg-elevated/30 p-3 text-xs">
                    <h3 className="font-semibold">{a.title}</h3><p className="my-1 font-mono">{a.symbol} · {a.severity ?? '—（未知严重程度）'}</p>
                    <p>{a.category} · {a.sample_alert_state === null ? '—（告警状态未知）' : a.sample_alert_state === 'OPEN_SAMPLE' ? '未确认样例（非真实待处理告警）' : '已确认样例（未执行真实确认）'}</p>
                    <p className="mt-1 text-muted">固定发生时间（合成样本 UTC）：{a.occurred_at}</p>
                    <details className="mt-2"><summary className="cursor-pointer text-accent">查看合成告警详情</summary>
                      <p className="mt-2">{a.condition_description}</p><p>source: {a.source} · {a.status}</p><p className="break-all">evidence: {a.evidence}</p>
                      <p>missing_fields: {a.missing_fields.join('、') || '无（仅样稿）'}</p>{a.reasons.map(reason => <p key={reason} className="text-warning">{reason}</p>)}
                    </details>
                  </article>)}
                </section>
                <section aria-label="合成监控任务" className={`${card} space-y-3`}>
                  <div className="flex flex-wrap items-center gap-2"><ListChecks className="h-4 w-4 text-accent" /><h2 className="text-sm font-semibold">监控任务样本 · {tasks.length}</h2><Disabled>新建规则</Disabled></div>
                  <p className="text-xs text-muted">点击任务查看详情。排序：{columns.find(c => c.id === sort?.key)?.label ?? '样稿顺序'} {sort?.dir === 'asc' ? '↑' : sort?.dir === 'desc' ? '↓' : ''}</p>
                  {!tasks.length ? <EmptyState title="暂无匹配的监控样本" /> : <StockDataTable columns={columns} rows={tasks} sort={sort} onSortToggle={toggle}
                    renderCell={(row: MonitorTaskSample, col) => <td className="px-3 py-3 align-top text-xs text-secondary" data-monitor-field={col.id}>
                      {col.id === 'name' ? <button aria-pressed={detail?.id === row.id} data-task-id={row.id} onClick={() => setSelected(row.id)} className="text-left text-accent"><span className="block">{row.name}</span><span className="font-mono">{row.symbol}</span><span className="block text-muted">{row.type}</span></button>
                        : col.id === 'sample_state' ? sampleStateLabel[row.sample_state]
                          : col.id === 'severity' ? (row.severity ?? '—（未知）')
                            : col.id === 'checked_at' ? <>{row.checked_at ?? '—'}{row.reasons.map(r => <p key={r} className="text-warning">{r}</p>)}</>
                              : <><Badge /><p>{row.source}</p><p className="break-all text-[10px] text-muted">{row.evidence}</p></>}
                    </td>} />}
                </section>
              </div>
              <section aria-label="监控样本详情" className={`${card} space-y-2 text-xs text-secondary`}>
                <h2 className="text-sm font-semibold">监控详情 · 只读样稿</h2>
                {!detail ? <EmptyState title="暂无选中的监控样本" /> : <>
                  <p>{detail.name} · {detail.symbol} · {detail.type} · {sampleStateLabel[detail.sample_state]}</p>
                  <p>监控条件（演示说明）：{detail.condition_description}</p><p>固定演示检查时间（UTC）：{detail.checked_at ?? '—（样稿未提供）'}</p>
                  <p>数据完整性：{detail.completeness === 'SAMPLE_COMPLETE' ? '仅样稿字段完整' : '样稿部分缺失'}；不表示生产输入 READY 或服务健康</p>
                  <p>source: {detail.source} · {detail.status}</p><p className="break-all">evidence: {detail.evidence}</p>
                  <p>missing_fields: {detail.missing_fields.join('、') || '无（仅样稿）'}</p>{detail.reasons.map(r => <p key={r} className="text-warning">{r}</p>)}
                  {detail.blockers.map(r => <p key={r} className="text-warning">blocker: {r}</p>)}{detail.warnings.map(r => <p key={r} className="text-muted">warning: {r}</p>)}
                  <div className="flex flex-wrap gap-2"><Disabled>启停监控</Disabled><Disabled>修改规则</Disabled></div>
                </>}
              </section>
              <p className="break-all text-xs text-muted">generated_at: {data.generated_at}（固定样稿时间） · trading_date: {data.trading_date} · data_mode: preview · is_production: false · is_investment_signal: false</p>
            </>}
    </div>
  </div>
}
function FixtureMonitor({ market, controls }: { market: MonitorMarket; controls: ReactNode }) {
  let state: MonitorPreviewState
  try { state = { kind: 'ready', data: loadMonitorPreview(market) } } catch { state = { kind: 'error' } }
  return <MonitorPreview market={market} state={state} controls={controls} />
}
export function MonitorMarkets({ cn }: { cn: (active: boolean, controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams()
  const requested = params.get('market')
  const market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const [visited, setVisited] = useState<readonly Market[]>([market])
  useEffect(() => { setVisited(old => old.includes(market) ? old : [...old, market]) }, [market])
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']}
    onChange={next => setParams(old => { const copy = new URLSearchParams(old); copy.set('market', next); return copy })} />
  return <div className="h-full min-h-0">{(['CN', 'HK', 'US'] as const).filter(m => visited.includes(m) || m === market).map(m =>
    <div key={m} hidden={market !== m} data-monitor-market={m} className="h-full min-h-0">{m === 'CN' ? cn(market === 'CN', controls) : <FixtureMonitor market={m} controls={controls} />}</div>)}</div>
}
