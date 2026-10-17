import { useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import { useTableSort } from '@/components/stock-table/useTableSort'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadStrategyPreview } from '../../../../tests/fixtures/strategy_preview'
import { validateStrategyPreview, type StrategyPreviewMarket, type StrategyPreviewQuality, type StrategyPreviewRow, type StrategyPreviewState, type StrategyRuleSample } from './contract'

const card = 'min-w-0 rounded-xl border border-border bg-surface/40 p-4 text-xs space-y-3'
const displayLabels = { DEFINED_SAMPLE: '结构完整样稿', INCOMPLETE_SAMPLE: '不完整样稿', NO_RULE_SAMPLE: '待定义样稿', BLOCKED_SAMPLE: '阻塞样稿' }
const typeLabels = { TREND_SAMPLE: '趋势示例', FILTER_SAMPLE: '过滤示例', VOLUME_SAMPLE: '量能示例' }
const columns: ColumnConfig[] = [['name', '策略名称 / 标识'], ['strategy_type', '类型'], ['version', '样稿版本'], ['definition_status', '定义状态'], ['display_state', '展示状态']].map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
const number = (v: number | null) => v === null ? '—（未定义）' : String(v)
function Badge({ status }: { status: StrategyPreviewQuality }) { return <span className={`rounded border px-2 py-0.5 text-[10px] ${status === 'READY' ? 'border-accent/30 text-accent' : 'border-warning/30 text-warning'}`}>{status} · 限定样稿</span> }
function Disabled({ children }: { children: ReactNode }) { return <button disabled title="Preview 模式不可执行：不保存、计算、监控、回测或产生信号/订单" className="rounded-btn border border-border px-3 py-1 text-xs text-muted">{children}（Preview 不可执行）</button> }
function Rule({ title, rule, reason }: { title: string; rule: StrategyRuleSample | null; reason: string }) {
  return <article className="min-w-0 rounded-lg border border-border p-3 space-y-2"><h3 className="font-semibold">{title} · 结构化合成条件</h3>{!rule ? <p className="text-warning">—（规则未定义） · {reason}</p> : <><p>组合逻辑：{rule.logic} · 仅元数据展示，不执行条件</p><div className="overflow-x-auto"><table className="w-full text-left"><thead><tr>{['左字段', '比较', '右值 / 字段', '左偏移', '右偏移'].map(v => <th key={v}>{v}</th>)}</tr></thead><tbody>{rule.conditions.map((c, i) => <tr key={i}><td className="p-2">{c.left}</td><td>{c.op}</td><td>{c.right}</td><td>{c.leftDays ?? '—（未声明）'}</td><td>{c.rightDays ?? '—（不适用 / 未声明）'}</td></tr>)}</tbody></table></div><p className="break-all">evidence: {rule.evidence}</p><p>{reason}</p></>}</article>
}
export function StrategyPreview({ market, state, controls }: { market: StrategyPreviewMarket; state: StrategyPreviewState; controls?: ReactNode }) {
  const [search, setSearch] = useState(''), [type, setType] = useState('ALL'), [quality, setQuality] = useState('ALL'), [version, setVersion] = useState('ALL'), [selected, setSelected] = useState<string | null>(null)
  const { sort, toggle, sortRows } = useTableSort<StrategyPreviewRow>((r, c) => r[c.id as 'name' | 'strategy_type' | 'version' | 'definition_status' | 'display_state'])
  const data = state.kind === 'ready' ? validateStrategyPreview(state.data) : null
  if (data && data.market !== market) throw new Error('strategy_preview_market_conflict')
  const rows = sortRows((data?.rows ?? []).filter(r => `${r.name} ${r.id} ${r.description}`.toLowerCase().includes(search.trim().toLowerCase()) && (type === 'ALL' || r.strategy_type === type) && (quality === 'ALL' || r.definition_status === quality) && (version === 'ALL' || r.version === version)), columns)
  const detail = rows.find(r => r.id === selected) ?? rows[0]
  return <div data-strategy-preview={market} className="flex min-h-0 flex-col">
    <PageHeader title={`${market} 策略 · Preview`} subtitle={`固定样稿交易日：${data?.trading_date ?? '—'}`} right={<Disabled>创建策略 · AI</Disabled>} />{controls}
    <div className="mx-auto w-full max-w-[1440px] space-y-4 p-5">
      <aside aria-label="策略演示声明" className="rounded-xl border border-warning/30 bg-warning/5 p-4 text-xs text-warning space-y-2"><p>演示策略｜非生产策略配置｜不产生真实交易信号｜不构成投资建议</p><p>PREVIEW · synthetic-fixture。定义、参数、规则和状态都是固定样稿，不注册到策略引擎，不执行信号或订单。</p></aside>
      {state.kind === 'loading' ? <p role="status">策略 Preview 加载中…</p> : state.kind === 'error' ? <ErrorState title="策略 Preview 加载失败" hint="不回退真实策略、参数或执行接口。" /> : data && <>
        <section aria-label="策略样稿概览" className={card}><h2 className="text-sm font-semibold">{market} · {data.rows.length} 项独立合成定义</h2><div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{(['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED'] as const).map(s => <p key={s} data-strategy-count={s}><Badge status={s} /> · {data.rows.filter(r => r.definition_status === s).length} 项定义样稿</p>)}</div><p>上述是样稿结构状态统计，不是正在运行的策略数量。真实运行状态、上次运行时间、信号数：—（未观测）。所有样稿生产验证 / 执行均 BLOCKED。</p></section>
        <section aria-label="策略样稿筛选" className="flex flex-wrap gap-3 text-xs"><input aria-label="搜索策略样稿" value={search} onChange={e => setSearch(e.target.value)} placeholder="策略名称 / 标识 / 描述" className="rounded-btn border border-border bg-base p-2" /><select aria-label="演示策略类型" value={type} onChange={e => setType(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部类型</option>{Object.entries(typeLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><select aria-label="演示定义状态" value={quality} onChange={e => setQuality(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部定义状态</option>{(['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED'] as const).map(s => <option key={s}>{s}</option>)}</select><select aria-label="演示策略版本" value={version} onChange={e => setVersion(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部样稿版本</option>{[...new Set(data.rows.map(r => r.version))].map(v => <option key={v}>{v}</option>)}</select></section>
        {!rows.length ? <EmptyState title="暂无匹配的策略样稿" hint="不表示真实策略为空，不自动导入或创建策略。" /> : <StockDataTable columns={columns} rows={rows} rowKey={(r: StrategyPreviewRow) => r.id} sort={sort} onSortToggle={toggle} renderCell={(r: StrategyPreviewRow, c) => <td className="p-3 text-xs align-top">{c.id === 'name' ? <button data-strategy-id={r.id} onClick={() => setSelected(r.id)} className="text-left text-accent"><strong className="block">{r.name}</strong><span className="font-mono">{r.id}</span></button> : c.id === 'definition_status' ? <Badge status={r.definition_status} /> : c.id === 'strategy_type' ? typeLabels[r.strategy_type] : c.id === 'display_state' ? displayLabels[r.display_state] : r.version}</td>} />}
        <section aria-label="策略样稿详情" className={card}>{!detail ? <p>暂无选中策略样稿</p> : <>
          <h2 className="text-sm font-semibold">{detail.name} · {detail.id}</h2><p>{detail.description}</p><p>市场：{detail.market} · 范围：{detail.symbols.join('、')}（仅样稿范围，非正式 Universe；证券类型未验证）</p><p>策略类型：{typeLabels[detail.strategy_type]} · 样稿版本：{detail.version} · 参数版本：{detail.parameter_version}</p><p className="break-all">配置身份：{detail.configuration_id} · evidence: {detail.evidence}</p><p>展示状态：{displayLabels[detail.display_state]} · 定义：<Badge status={detail.definition_status} /> · 生产验证：{detail.validation_status}</p><p>真实运行状态：—（未观测） · 上次运行时间：—（未知） · 真实信号数：—（未知，不填0）</p><p>input_contract / universe exact identity：—（未绑定，禁止自动选择或 fallback）</p>
          <div className="grid gap-3 lg:grid-cols-2"><Rule title="入场规则" rule={detail.entry} reason={detail.rule_reason} /><Rule title="退出规则" rule={detail.exit} reason={detail.rule_reason} /></div>
          <section aria-label="策略参数样稿" className="space-y-2"><h3 className="font-semibold">只读参数 · 未提供参数编辑或保存</h3>{detail.parameters.map(p => <article key={p.id} data-param-id={p.id} className="rounded-lg border border-border p-3 space-y-1"><p>{p.label} / {p.id}：{number(p.value)} · 单位：{p.unit} · 类型：{p.type} · <Badge status={p.status} /></p><p>正式默认值：{number(p.default_value)} · 允许范围：{number(p.min)} .. {number(p.max)}</p><p>参数版本：{p.version} · 字段来源：{p.contract_reference}</p><p className="text-warning">{p.reason}</p><p className="break-all">source: synthetic-fixture · evidence: {p.evidence}</p></article>)}</section>
          <section aria-label="策略风险样稿" className="space-y-2"><h3 className="font-semibold">风险字段 · 不代表执行引擎已强制实施</h3><div className="grid gap-3 lg:grid-cols-2">{detail.risks.map(r => <article key={r.key} data-risk-key={r.key} className="rounded-lg border border-border p-3"><p>{r.label}：{number(r.value)} · {r.unit} · <Badge status={r.status} /></p><p>强制执行：否（Preview 不执行） · 字段来源：{r.contract_reference ?? '—（缺少契约）'}</p><p className="text-warning">{r.reason}</p></article>)}</div></section>
          <section aria-label="策略依赖样稿" className="space-y-2"><h3 className="font-semibold">验证 / 依赖状态 · 不因定义完整而放行</h3>{detail.dependencies.map(d => <article key={d.key} className="rounded-lg border border-border p-3"><p>{d.key} · <Badge status={d.status} /></p><p className="text-warning">{d.reason}</p><p className="break-all">evidence: {d.evidence}</p></article>)}</section>
          <p>missing_fields: {detail.missing_fields.join('、')}</p>{detail.blockers.map(r => <p key={r} className="text-warning">blocker: {r}</p>)}{detail.warnings.map(r => <p key={r} className="text-muted">warning: {r}</p>)}<div className="flex flex-wrap gap-2"><Disabled>运行策略</Disabled><Disabled>保存配置</Disabled><Disabled>加入监控</Disabled></div>
        </>}</section>
        <p className="text-xs text-muted">source: {data.source} · PREVIEW · data_mode: preview · is_production: false · is_investment_signal: false · 固定交易日：{data.trading_date} · generated_at：{data.generated_at}（样稿编写时间，不是运行记录）</p>
      </>}
    </div>
  </div>
}
function FixtureStrategies({ market, controls }: { market: StrategyPreviewMarket; controls: ReactNode }) {
  let state: StrategyPreviewState
  try { state = { kind: 'ready', data: loadStrategyPreview(market) } } catch { state = { kind: 'error' } }
  return <StrategyPreview market={market} state={state} controls={controls} />
}
export function StrategyMarkets({ cn }: { cn: (controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams(), requested = params.get('market')
  const market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']} onChange={next => setParams(old => { const copy = new URLSearchParams(old); copy.set('market', next); return copy })} />
  return <div key={market} data-strategy-market={market} className="h-full min-h-0">{market === 'CN' ? cn(controls) : <FixtureStrategies market={market} controls={controls} />}</div>
}
