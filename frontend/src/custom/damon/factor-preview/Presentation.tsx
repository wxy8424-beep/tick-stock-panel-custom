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
import { loadFactorPreview } from '../../../../tests/fixtures/factor_preview'
import { FACTOR_VIEWS, FACTOR_VIEW_LABELS, validateFactorPreview, type FactorPreviewMarket,
  type FactorPreviewQuality, type FactorPreviewRow, type FactorPreviewState, type FactorPreviewView } from './contract'

const disclaimer = '演示因子｜合成数据｜非生产因子配置｜不产生真实信号｜不构成投资建议'
const disabledReason = 'Preview 模式不可执行：不计算、保存、注册、发布或生成策略/信号'
const card = 'min-w-0 rounded-xl border border-border bg-surface/40 p-4 text-xs space-y-3'
const kinds = { base: '基础', virtual: '虚拟', composite: '复合', custom: '自定义' }
const columns: ColumnConfig[] = [
  ['label', '因子名称 / 标识'], ['kind', '类型'], ['group', '分组'], ['version', '样稿版本'],
  ['definition_status', '定义状态'], ['sample_value', '合成展示值'],
].map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
const qualities: FactorPreviewQuality[] = ['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED']
function Badge({ status }: { status: FactorPreviewQuality }) {
  return <span className="rounded border border-warning/30 px-2 py-0.5 text-[10px] text-warning">{status} · 限定样稿</span>
}
export function FactorPreview({ market, state, view = 'inspect', onView, controls }: {
  market: FactorPreviewMarket; state: FactorPreviewState; view?: FactorPreviewView
  onView?: (view: FactorPreviewView) => void; controls?: ReactNode
}) {
  const [search, setSearch] = useState(''), [kind, setKind] = useState('ALL'), [quality, setQuality] = useState('ALL')
  const [group, setGroup] = useState('ALL'), [selected, setSelected] = useState<string | null>(null)
  const { sort, toggle, sortRows } = useTableSort<FactorPreviewRow>((r, c) => r[c.id as keyof FactorPreviewRow])
  let data: ReturnType<typeof loadFactorPreview> | null = null
  if (state.kind === 'ready') {
    try { const checked = validateFactorPreview(state.data); if (checked.market === market) data = checked } catch { /* Fail closed to the existing error view. */ }
  }
  const rows = sortRows((data?.rows ?? []).filter(r => (kind === 'ALL' || r.kind === kind)
    && (quality === 'ALL' || r.definition_status === quality) && (group === 'ALL' || r.group === group)
    && `${r.id} ${r.label} ${r.description} ${r.formula ?? ''}`.toLowerCase().includes(search.trim().toLowerCase())), columns)
  const detail = rows.find(r => r.id === selected) ?? rows[0]
  const missing = (row: FactorPreviewRow, key: keyof FactorPreviewRow) => <span>— · {row.missing_reasons[key]}</span>
  return <div className="min-h-full bg-base">
    <PageHeader className="pl-14 md:pl-5" title={`${market} 因子 · Preview`} subtitle="固定样稿，只读展示，不注册到 Factor Engine" />
    {controls}
    <div className="space-y-4 p-3 lg:p-5">
      <PreviewNotice statement={disclaimer} description="仅用于界面验收，不是实际因子检验、FactorSnapshot、回测业绩或生产能力证明。" />
      <nav aria-label="因子样稿视图" className="flex flex-wrap gap-2">
        {FACTOR_VIEWS.map(v => <button key={v} onClick={() => onView?.(v)} aria-current={v === view ? 'page' : undefined} disabled={!onView}
          className={`rounded-btn border border-border px-3 py-1.5 text-xs ${v === view ? 'bg-accent text-white' : 'text-secondary'}`}>{FACTOR_VIEW_LABELS[v]}</button>)}
      </nav>
      {state.kind === 'loading' ? <p role="status">因子样稿加载中…</p> : !data ? <ErrorState title="因子样稿加载失败" hint="仅接受本市场独立 fixture，不回退生产因子或检验接口。" /> : <>
        <section aria-label="因子样稿概览" className={card}>
          <p>交易日：{data.trading_date} · generated_at：{data.generated_at}（固定编写时间，非运行时间）</p>
          <p>source: {data.source} · PREVIEW · data_mode: preview · is_production: false · is_investment_signal: false</p>
          <div className="flex flex-wrap gap-3">{qualities.map(s => <p key={s} data-factor-count={s}>{s}：{data!.rows.filter(r => r.definition_status === s).length} 项定义样稿</p>)}</div>
          <p>样稿行数不代表市场证券覆盖；生产覆盖数：—（未测量） · 生产验证 / 执行：BLOCKED</p>
        </section>
        <section aria-label="筛选因子样稿" className="flex flex-wrap gap-3 text-xs">
          <input aria-label="搜索因子样稿" value={search} onChange={e => setSearch(e.target.value)} placeholder="名称 / 标识 / 公式 / 描述" className="rounded-btn border border-border bg-base p-2" />
          <select aria-label="演示因子类型" value={kind} onChange={e => setKind(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部类型</option>{Object.entries(kinds).map(([k, label]) => <option key={k} value={k}>{label}</option>)}</select>
          <select aria-label="演示因子分组" value={group} onChange={e => setGroup(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部分组</option>{[...new Set(data.rows.map(r => r.group))].map(g => <option key={g}>{g}</option>)}</select>
          <select aria-label="演示因子定义状态" value={quality} onChange={e => setQuality(e.target.value)} className="rounded-btn border border-border bg-base p-2"><option value="ALL">全部定义状态</option>{qualities.map(s => <option key={s}>{s}</option>)}</select>
        </section>
        {!rows.length ? <EmptyState title="暂无匹配的因子样稿" hint="不表示生产因子库为空，不自动下载、生成或导入。" /> : <StockDataTable columns={columns} rows={rows} rowKey={(r: FactorPreviewRow) => r.id} sort={sort} onSortToggle={toggle}
          renderCell={(r: FactorPreviewRow, c) => <td className="p-3 text-xs align-top">{c.id === 'label'
            ? <button data-factor-id={r.id} onClick={() => setSelected(r.id)} className="text-left text-accent"><strong className="block">{r.label}</strong><span className="font-mono">{r.id}</span></button>
            : c.id === 'kind' ? kinds[r.kind] : c.id === 'definition_status' ? <Badge status={r.definition_status} />
              : c.id === 'sample_value' ? r.sample_value === null ? missing(r, 'sample_value') : String(r.sample_value)
                : String(r[c.id as 'version' | 'group'])}</td>} />}
        <section aria-label="因子样稿详情" className={card}>{!detail ? <p>暂无选中因子样稿</p> : <>
          <h2 className="text-sm font-semibold">{detail.label} · {detail.id}</h2><p>{detail.description}</p>
          <p>市场：{detail.market} · 类型：{kinds[detail.kind]} · 版本：{detail.version} · 分组：{detail.group}</p>
          <p>展示证券：{detail.sample_symbols.join('、')}（仅样稿范围，非正式 Universe）</p>
          <p>定义：<Badge status={detail.definition_status} /> · 生产验证：{detail.validation_status} · 生产执行：{detail.execution_status}</p>
          <p>方向元数据：{detail.direction}（仅样稿偏好，不是投资结论） · 单位：{detail.unit ?? missing(detail, 'unit')}</p>
          <p>只读公式：{detail.formula ?? missing(detail, 'formula')}</p>
          <p>历史预热 bars：{detail.warmup_bars ?? missing(detail, 'warmup_bars')} · 依赖：{detail.dependencies?.join('、') ?? missing(detail, 'dependencies')}</p>
          <p>合成展示值：{detail.sample_value ?? missing(detail, 'sample_value')}（不执行计算）</p>
          <p className="break-all">source: {detail.source} · evidence: {detail.evidence}</p>
          <section aria-label="因子检验证据" className="space-y-2 rounded-lg border border-border p-3"><h3>检验证据 · 不构造历史结果</h3>
            {(['ic_mean', 'ic_ir', 'coverage_count', 'evaluated_at', 'pit', 'universe_identity', 'input_contract_identity'] as const).map(k => <p key={k} data-factor-missing={k}>{k}: {missing(detail, k)}</p>)}
          </section>
          <section aria-label="当前因子样稿视图" className="space-y-2 rounded-lg border border-border p-3">
            <h3>{FACTOR_VIEW_LABELS[view]} · 只读 Preview</h3>
            {view === 'inspect' ? <><p>合成值仅演示展示格式，无实际 IC / Rank IC / IR 或收益结果。</p><PreviewDisabledAction label="运行检验" reason={disabledReason} /></>
              : view === 'library' ? <><p>样稿身份未加入注册表；不允许修改真实生命周期或删除定义。</p><PreviewDisabledAction label="更改因子状态" reason={disabledReason} /><PreviewDisabledAction label="生成策略 / 信号" reason={disabledReason} /></>
                : view === 'editor' ? <><p>仅查看上方公式元数据，不加载 edit 参数指定的真实因子，不运行 DSL。</p><PreviewDisabledAction label="验证 / 试算公式" reason={disabledReason} /><PreviewDisabledAction label="保存因子" reason={disabledReason} /></>
                  : view === 'composite' ? <><p>组合权重：—（没有本样稿组合定义，不自动等权或重分配）</p><PreviewDisabledAction label="保存组合" reason={disabledReason} /></>
                    : <><p>挖掘任务：—（未创建） · 任务结果：—（不可用）；不加载 URL run / candidate 指向的真实任务。</p><PreviewDisabledAction label="启动挖掘 / 发布候选" reason={disabledReason} /></>}
          </section>
          <p>missing_fields: {Object.entries(detail.missing_reasons).filter(([key]) => detail[key as keyof FactorPreviewRow] === null).map(([key]) => key).join('、')}</p>
          {detail.blockers.map(reason => <p key={reason} className="text-warning">blocker: {reason}</p>)}
          {detail.warnings.map(reason => <p key={reason} className="text-muted">warning: {reason}</p>)}
          <p>静态契约依据：docs/custom/longbridge-historical-vendor-evidence-closure-v1.md · docs/custom/momentum-universe-foundation-v1.md；不是动态健康检查。</p>
        </>}</section>
      </>}
    </div>
  </div>
}

function FixtureFactors({ market, controls }: { market: FactorPreviewMarket; controls: ReactNode }) {
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab')
  const view = FACTOR_VIEWS.includes(requested as FactorPreviewView) ? requested as FactorPreviewView : 'inspect'
  let state: FactorPreviewState
  try { state = { kind: 'ready', data: loadFactorPreview(market) } } catch { state = { kind: 'error' } }
  return <FactorPreview market={market} controls={controls} view={view} state={state} onView={next => setParams(old => {
    const copy = new URLSearchParams(old); copy.set('tab', next); copy.delete('focus'); copy.delete('edit'); return copy
  }, { replace: true })} />
}

export function FactorMarkets({ cn }: { cn: (controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams(), requested = params.get('market')
  const market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']}
    onChange={next => setParams(old => { const copy = new URLSearchParams(old); copy.set('market', next); return copy })} />
  return <div key={market} data-factor-market={market} className="h-full min-h-0">{market === 'CN' ? cn(controls) : <FixtureFactors market={market} controls={controls} />}</div>
}
