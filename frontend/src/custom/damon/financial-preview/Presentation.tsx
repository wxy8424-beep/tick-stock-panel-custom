import { useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { MarketSwitcherBar, type Market } from '@/components/MarketSwitcher'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StockDataTable } from '@/components/stock-table/StockDataTable'
import type { ColumnConfig } from '@/lib/list-columns'
import { loadFinancialPreview } from '../../../../tests/fixtures/financial_preview'
import { statementFields, validateFinancialPreview, type FinancialMarket, type FinancialField, type FinancialPreviewState, type FinancialReportSample, type FinancialQuality } from './contract'

const card = 'min-w-0 rounded-xl border border-border bg-surface/40 p-4 text-xs space-y-3'
const number = (v: number | null) => v === null ? '—' : v.toFixed(2)
const columns: ColumnConfig[] = [['field', '报表项目'], ['value', '合成数值 / 单位'], ['origin', '输入 / 派生口径'], ['status', '限定质量状态']].map(([id, label]) => ({ id, label, visible: true, source: { type: 'builtin', key: id } }))
function Badge({ status }: { status: FinancialQuality }) { return <span className={`rounded border px-2 py-0.5 text-[10px] ${status === 'READY' ? 'border-accent/30 text-accent' : 'border-warning/30 text-warning'}`}>{status} · 样稿</span> }
function Disabled({ children }: { children: ReactNode }) { return <button disabled title="Preview 模式不可执行：不请求、下载、同步、保存或分析真实财报" className="rounded-btn border border-border px-3 py-1 text-xs text-muted">{children}（Preview 不可执行）</button> }

function TrendChart({ reports, field, currency }: { reports: readonly FinancialReportSample[]; field: FinancialField; currency: string }) {
  const values = reports.map(r => r.values[field].value), known = values.filter((v): v is number => v !== null)
  if (!known.length) return <EmptyState title="暂无该指标的趋势样稿" hint="缺失不插值、不填零。" />
  const low = Math.min(0, ...known), high = Math.max(0, ...known), range = high - low || 1
  const point = (i: number, v: number) => ({ x: 40 + i * 510 / Math.max(1, reports.length - 1), y: 150 - (v - low) / range * 125 })
  return <svg viewBox="0 0 600 195" role="img" aria-label={`${statementFields[field][0]} · ${field === 'net_margin' ? '%' : `百万 ${currency}`} · 合成趋势，缺失不连线`} className="w-full max-w-3xl text-accent">
    <title>{statementFields[field][0]} · 合成趋势；缺失区间保留断点</title>
    <text x="3" y="15" fontSize="10" fill="currentColor">{number(high)}</text><text x="3" y="155" fontSize="10" fill="currentColor">{number(low)}</text>
    {reports.map((r, i) => { const v = values[i]; const a = v === null ? null : point(i, v), previous = i > 0 ? values[i - 1] : null; const b = previous === null ? null : point(i - 1, previous)
      return <g key={r.id}>{a && b && <line data-trend-segment={`${reports[i - 1].period_end}:${r.period_end}`} x1={b.x} y1={b.y} x2={a.x} y2={a.y} stroke="currentColor" strokeWidth="2" />}{a && <circle data-trend-point={r.period_end} cx={a.x} cy={a.y} r="4" fill="currentColor" />}<text x={40 + i * 510 / Math.max(1, reports.length - 1)} y="183" fontSize="10" textAnchor="middle" fill="currentColor">{r.period_end}</text></g> })}
  </svg>
}

export function FinancialPreview({ market, state, controls }: { market: FinancialMarket; state: FinancialPreviewState; controls?: ReactNode }) {
  const [securitySearch, setSecuritySearch] = useState(''), [selected, setSelected] = useState(''), [frequency, setFrequency] = useState<'ANNUAL' | 'QUARTER'>('ANNUAL'), [period, setPeriod] = useState('')
  const [table, setTable] = useState('income'), [fieldSearch, setFieldSearch] = useState(''), [detailField, setDetailField] = useState<FinancialField>('revenue'), [trendField, setTrendField] = useState<FinancialField>('revenue')
  const data = state.kind === 'ready' ? validateFinancialPreview(state.data) : null
  if (data && data.market !== market) throw new Error('financial_preview_market_conflict')
  const companies = (data?.companies ?? []).filter(c => `${c.symbol} ${c.name}`.toLowerCase().includes(securitySearch.trim().toLowerCase()))
  const company = companies.find(c => c.symbol === selected) ?? companies[0]
  const reports = [...(company?.reports ?? [])].filter(r => r.report_type === frequency).sort((a, b) => b.period_end.localeCompare(a.period_end))
  const report = reports.find(r => r.id === period) ?? reports[0]
  const fields = (Object.keys(statementFields) as FinancialField[]).filter(k => statementFields[k][1] === table && `${k} ${statementFields[k][0]}`.toLowerCase().includes(fieldSearch.trim().toLowerCase()))
  const detail = report?.values[detailField]
  return <div data-financial-preview={market} className="flex min-h-0 flex-col">
    <PageHeader title={`${market} 财务分析 · Preview`} subtitle={`固定样稿交易日：${data?.trading_date ?? '—'}`} right={<Disabled>全部同步</Disabled>} />{controls}
    <div className="mx-auto w-full max-w-[1440px] space-y-4 p-5">
      <aside aria-label="财务演示声明" className="rounded-xl border border-warning/30 bg-warning/5 p-4 text-xs text-warning space-y-2"><p>演示财务数据｜非真实公司财报｜估值仅用于界面演示｜不构成投资建议</p><p>PREVIEW · synthetic-fixture。所有企业数值、报告、公告时间和价格均为独立合成样稿，不是对应证券的真实最新财报。</p></aside>
      {state.kind === 'loading' ? <p role="status">财务 Preview 加载中…</p> : state.kind === 'error' ? <ErrorState title="财务 Preview 加载失败" hint="不回退真实财报、同步或 AI 分析接口。" /> : data && <>
        <section aria-label="演示证券选择" className={`${card} flex flex-wrap items-center gap-3`}><input aria-label="搜索财务样稿证券" value={securitySearch} onChange={e => { setSecuritySearch(e.target.value); setSelected(''); setPeriod('') }} placeholder="代码 / 演示企业名称" className="rounded-btn border border-border bg-base p-2" />{companies.map(c => <button key={c.symbol} data-financial-symbol={c.symbol} aria-pressed={company?.symbol === c.symbol} onClick={() => { setSelected(c.symbol); setFrequency('ANNUAL'); setPeriod(''); setFieldSearch(''); setDetailField('revenue') }} className="rounded-btn border border-border px-3 py-2 text-accent">{c.symbol} · {c.name}</button>)}</section>
        {!company ? <EmptyState title="暂无匹配的财务样稿企业" /> : <>
          <section aria-label="演示财报筛选" className="flex flex-wrap gap-3 text-xs">
            <select aria-label="演示报告类型" value={frequency} onChange={e => { setFrequency(e.target.value as 'ANNUAL' | 'QUARTER'); setPeriod('') }} className="rounded-btn border border-border bg-base p-2"><option value="ANNUAL">年度 · FULL_YEAR</option><option value="QUARTER">季度 · SINGLE_QUARTER</option></select>
            <select aria-label="演示报告期" value={report?.id ?? ''} onChange={e => setPeriod(e.target.value)} className="rounded-btn border border-border bg-base p-2">{reports.map(r => <option key={r.id} value={r.id}>{r.period_start} .. {r.period_end}</option>)}</select>
          </section>
          {!report ? <EmptyState title="暂无该类型的财报样稿" /> : <>
            <section aria-label="公司财务样稿概览" className={card}><h2 className="text-sm font-semibold">{company.name} · {company.symbol} · {market}</h2><p>报表币种：{company.currency} · 金额单位：百万 {company.currency}（合成）</p><p>报告期：{report.period_start} .. {report.period_end} · {report.flow_basis}；资产负债表为期末余额 PERIOD_END</p><p>固定公告时间 UTC：{report.announce_at ?? '—（未提供）'} · 固定可得时间 UTC：{report.available_at ?? '—（未提供）'}</p>{report.time_reason && <p className="text-warning">{report.time_reason}</p>}<p>年度/单季度单独选择，不使用 YTD 拆季，不换汇；不是生产财报可得性证明。</p>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{(Object.keys(statementFields) as FinancialField[]).map(k => <div key={k} data-financial-overview={k} className="rounded-btn bg-elevated/30 p-3"><p>{statementFields[k][0]}</p><p className="font-mono text-lg">{number(report.values[k].value)} {k === 'net_margin' ? '%' : `百万 ${company.currency}`}</p>{report.values[k].reason && <p className="text-warning">{report.values[k].reason}</p>}</div>)}</div>
            </section>
            <section aria-label="演示财务报表" className={card}><div className="flex flex-wrap gap-2">{[['income', '利润表'], ['balance', '资产负债表'], ['cash', '现金流量表']].map(([key, label]) => <button key={key} aria-pressed={table === key} onClick={() => { setTable(key); setFieldSearch('') }} className="rounded-btn border border-border px-3 py-2 text-accent">{label}</button>)}<input aria-label="搜索演示财务项目" value={fieldSearch} onChange={e => setFieldSearch(e.target.value)} placeholder="项目名称 / 字段" className="rounded-btn border border-border bg-base p-2" /></div>
              {!fields.length ? <EmptyState title="暂无匹配的报表项目" /> : <StockDataTable columns={columns} rows={fields} rowKey={(k: FinancialField) => k} renderCell={(k: FinancialField, c) => <td className="p-3 text-xs align-top">{c.id === 'field' ? <button data-financial-field={k} className="text-accent" onClick={() => setDetailField(k)}>{statementFields[k][0]}</button> : c.id === 'value' ? <>{number(report.values[k].value)} {k === 'net_margin' ? '%' : `百万 ${company.currency}`}<p className="text-warning">{report.values[k].reason}</p></> : c.id === 'origin' ? <>{report.values[k].origin === 'SYNTHETIC_INPUT' ? '合成输入（非供应商字段）' : '样稿派生'}<p>{report.values[k].formula}</p></> : <Badge status={report.values[k].status} />}</td>} />}
            </section>
            <section aria-label="财务字段样稿详情" className={card}><h2 className="text-sm font-semibold">字段详情 · {statementFields[detailField][0]}</h2><p>{report.id} · {company.currency} · {report.flow_basis}</p><p>{detail?.formula}</p><p className="break-all">source: synthetic-fixture · evidence: {detail?.evidence}</p>{detail?.reason && <p className="text-warning">{detail.reason}</p>}</section>
          </>}
          <section aria-label="演示估值指标" className={card}><h2 className="text-sm font-semibold">固定估值样稿 · FY2025，非 TTM、非实时估值</h2><p>估值各自绑定固定价格和明确财报期，不随上方报表选择重算或拼接。单位与币种均为样稿声明。</p><div className="grid gap-3 lg:grid-cols-2">{company.valuations.map(v => <article key={v.key} data-valuation={v.key} className="min-w-0 rounded-lg border border-border p-3 space-y-2"><h3>{v.key}：{number(v.value)} {v.unit} · <Badge status={v.status} /></h3><p>{v.formula}</p><p>币种：{v.currency} · 财报期：{v.financial_period} · report: {v.report_id}</p><p>固定价格：{number(v.price)} {v.currency} · 价格时点 UTC：{v.price_at ?? '—（纯财务指标，不使用价格）'}</p><p>{v.inputs}</p>{v.reason && <p className="text-warning">{v.reason}</p>}<p className="break-all">source: {v.input_source} · evidence: {v.evidence}</p></article>)}</div></section>
          <section aria-label="演示财务趋势" className={card}><h2 className="text-sm font-semibold">{frequency === 'ANNUAL' ? '年度' : '单季度'}合成财务趋势 · {company.currency}</h2><p>金额为百万 {company.currency}，净利率为百分点；不混合年度/季度，不插值缺失区间。</p><select aria-label="演示趋势指标" value={trendField} onChange={e => setTrendField(e.target.value as FinancialField)} className="rounded-btn border border-border bg-base p-2">{(['revenue', 'net_income', 'operating_cash_flow', 'net_margin'] as const).map(k => <option key={k} value={k}>{statementFields[k][0]}</option>)}</select><TrendChart reports={[...reports].reverse()} field={trendField} currency={company.currency} />
            <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr><th>报告期 / 口径</th>{(['revenue', 'net_income', 'operating_cash_flow', 'net_margin'] as const).map(k => <th key={k}>{statementFields[k][0]}（{k === 'net_margin' ? '%' : `百万 ${company.currency}`}）</th>)}</tr></thead><tbody>{[...reports].reverse().map(r => <tr key={r.id} data-trend-row={r.period_end}><td className="p-2">{r.period_end} · {r.flow_basis}</td>{(['revenue', 'net_income', 'operating_cash_flow', 'net_margin'] as const).map(k => <td key={k} className="p-2">{number(r.values[k].value)}{r.values[k].reason && <p className="text-warning">{r.values[k].reason}</p>}</td>)}</tr>)}</tbody></table></div>
          </section>
          <section aria-label="描述性财务观察" className={card}><h2 className="text-sm font-semibold">描述性观察（合成样稿，不是真实预警）</h2><p>营收、净利润、经营现金流、负债与利润率按上方同口径报告期逐项对照，不采用未经验证的“财务健康”阈值或评级。</p><p>缺失现金流保留断点，缺少必要输入时不判断现金流与利润差异。股息率及部分 PB 因输入口径未知保持 BLOCKED，不以0替代。</p></section>
        </>}
        <section aria-label="财务演示质量" className={card}>{data.blockers.map(r => <p key={r} className="text-warning">blocker: {r}</p>)}{data.warnings.map(r => <p key={r} className="text-muted">warning: {r}</p>)}<p>source: {data.source} · PREVIEW · data_mode: preview · is_production: false · is_investment_signal: false</p><p>固定交易日：{data.trading_date} · 固定样稿 generated_at：{data.generated_at}（不是供应商更新时间）</p><Disabled>AI 财务分析</Disabled></section>
      </>}
    </div>
  </div>
}
function FixtureFinancials({ market, controls }: { market: FinancialMarket; controls: ReactNode }) {
  let state: FinancialPreviewState
  try { state = { kind: 'ready', data: loadFinancialPreview(market) } } catch { state = { kind: 'error' } }
  return <FinancialPreview market={market} state={state} controls={controls} />
}
export function FinancialMarkets({ cn }: { cn: (controls: ReactNode) => ReactNode }) {
  const [params, setParams] = useSearchParams(), requested = params.get('market')
  const market: Market = requested === 'HK' || requested === 'US' ? requested : 'CN'
  const controls = <MarketSwitcherBar value={market} enabledMarkets={['CN', 'HK', 'US']} onChange={next => setParams(old => { const copy = new URLSearchParams(old); copy.set('market', next); return copy })} />
  return <div key={market} data-financial-market={market} className="h-full min-h-0">{market === 'CN' ? cn(controls) : <FixtureFinancials market={market} controls={controls} />}</div>
}
