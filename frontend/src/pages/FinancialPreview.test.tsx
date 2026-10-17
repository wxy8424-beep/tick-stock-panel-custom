// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Financials } from '@/custom/financials/extension'
import { FinancialPreview } from '@/custom/damon/financial-preview/Presentation'
import { validateFinancialPreview } from '@/custom/damon/financial-preview/contract'
import { loadFinancialPreview } from '../../tests/fixtures/financial_preview'

const state = vi.hoisted(() => ({ queries: [] as unknown[][], mutate: vi.fn(), api: vi.fn(), ai: vi.fn(), history: vi.fn(), available: true }))
vi.mock('@tanstack/react-query', async original => ({ ...await original<typeof import('@tanstack/react-query')>(), useQueryClient: () => ({ invalidateQueries: vi.fn() }), useMutation: () => ({ mutate: state.mutate, isPending: false }), useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
  state.queries.push(queryKey)
  return { data: queryKey[0] === 'financials' ? queryKey[1] === 'status' ? { available: state.available, tables: {}, last_sync: {}, syncing: false } : { data: [{ period_end: '2025-12-31', announce_date: '2026-04-01', revenue: 1000, net_income: 100 }] } : queryKey[0] === 'instrument-search' ? { results: [{ symbol: '600000.SH', name: 'CN测试样例' }] } : undefined, isLoading: false, refetch: vi.fn() }
} }))
vi.mock('@/lib/api', async original => { const actual = await original<typeof import('@/lib/api')>(); return { ...actual, api: Object.fromEntries(Object.keys(actual.api).map(k => [k, (...args: unknown[]) => state.api(k, args)])) } })
vi.mock('@/lib/aiReportStore', () => ({ startAnalysis: state.ai, findLatestHistoryReport: vi.fn(async () => null), openHistoryReport: vi.fn(), useHistoryReports: () => ({ reports: [], loaded: true }), useActiveTasks: () => [], loadHistory: state.history, deleteReport: vi.fn() }))
let host: HTMLDivElement, root: Root
beforeEach(() => { Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.clearAllMocks(); state.queries = []; state.available = true; host = document.createElement('div'); document.body.append(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })
async function render(path = '/financials', element = <Financials />) {
  function Nav() { const l = useLocation(), navigate = useNavigate(); return <><output data-location>{l.search}</output><button data-back onClick={() => navigate(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Nav /></MemoryRouter>))
}
function active() { return host.querySelector<HTMLElement>('[data-financial-market]')! }
async function market(i: number) { await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[i].click()) }
async function input(label: string, v: string) { const el = active().querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!; await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })) }) }
async function select(label: string, v: string) { const el = active().querySelector<HTMLSelectElement>(`select[aria-label="${label}"]`)!; await act(async () => { el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })) }) }
async function clickText(t: string) { await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent?.trim() === t)!.click()) }
it('CN retains status, sync handler, real search, selection and report tabs/queries', async () => {
  await render(); expect(active().querySelector('h1')?.textContent).toBe('财务分析'); expect(state.queries).toContainEqual(['financials', 'status']); expect(state.history).toHaveBeenCalled()
  await clickText('全部同步'); expect(state.mutate.mock.calls[0][0]).toBe('all')
  const el = active().querySelector<HTMLInputElement>('input')!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, '600000'); el.dispatchEvent(new Event('input', { bubbles: true })) })
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent?.includes('CN测试样例'))!.click())
  expect(state.queries).toContainEqual(['financials', 'income', '600000.SH']); await clickText('利润表'); expect(active().textContent).toContain('营业收入')
  await market(1); expect(active().dataset.financialMarket).toBe('HK'); expect(active().textContent).not.toContain('CN测试样例')
})
it('CN unavailable-source gate retains its behavior while allowing Preview market switching', async () => {
  state.available = false; await render(); expect(active().textContent).toContain('财务数据不可用'); expect(active().textContent).toContain('前往数据源配置')
  await market(2); expect(active().dataset.financialMarket).toBe('US'); expect(active().textContent).toContain('演示财务数据')
})
it.each(['HK', 'US'] as const)('direct %s uses independent synthetic financials without production/AI/storage calls', async m => {
  const fetch = vi.fn(), write = vi.spyOn(Storage.prototype, 'setItem'), notify = vi.fn(); vi.stubGlobal('fetch', fetch); vi.stubGlobal('Notification', notify)
  await render(`/financials?market=${m}`)
  for (const t of ['演示财务数据｜非真实公司财报｜估值仅用于界面演示｜不构成投资建议', 'synthetic-fixture', 'PREVIEW', '2026-09-16', '2026-09-17T07:00:00Z', '虚构财报', m === 'HK' ? 'HKD' : 'USD']) expect(active().textContent).toContain(t)
  expect(active().textContent).toContain(m === 'HK' ? '0700.HK' : 'AAPL.US'); expect(active().textContent).not.toContain(m === 'HK' ? 'AAPL.US' : '0700.HK')
  await act(async () => active().querySelectorAll<HTMLButtonElement>('button:disabled').forEach(b => b.click()))
  expect(state.queries).toHaveLength(0); for (const spy of [state.mutate, state.api, state.ai, state.history, fetch, write, notify]) expect(spy).not.toHaveBeenCalled()
})
it('annual and single-quarter selection use explicit start/end, announcement, availability and period-end balances', async () => {
  await render('/financials?market=HK'); let overview = active().querySelector('[aria-label="公司财务样稿概览"]')!
  for (const t of ['2025-01-01 .. 2025-12-31', 'FULL_YEAR', 'PERIOD_END', '2026-04-15T08:00:00Z', '百万 HKD']) expect(overview.textContent).toContain(t)
  await select('演示报告期', 'fixture-report-HK-0-2023'); expect(overview.textContent).toContain('2023-01-01 .. 2023-12-31')
  await select('演示报告类型', 'QUARTER'); overview = active().querySelector('[aria-label="公司财务样稿概览"]')!
  expect(overview.textContent).toContain('2026-04-01 .. 2026-06-30'); expect(overview.textContent).toContain('SINGLE_QUARTER')
  expect(active().querySelectorAll('[data-trend-row]')).toHaveLength(2); expect(active().querySelector('[aria-label="演示财务趋势"]')?.textContent).not.toContain('2025-12-31')
})
it('statement tabs, field search, derived FCF/margin and evidence details use matching report inputs', async () => {
  await render('/financials?market=US'); const c = loadFinancialPreview('US').companies[0], r = c.reports[2]
  expect(r.values.free_cash_flow.value).toBe(r.values.operating_cash_flow.value! - r.values.capex.value!)
  expect(r.values.net_margin.value).toBe(100 * r.values.net_income.value! / r.values.revenue.value!)
  await clickText('现金流量表'); await input('搜索演示财务项目', 'free_cash_flow'); expect(active().querySelectorAll('[data-financial-field]')).toHaveLength(1)
  await act(async () => active().querySelector<HTMLButtonElement>('[data-financial-field="free_cash_flow"]')!.click())
  expect(active().querySelector('[aria-label="财务字段样稿详情"]')?.textContent).toContain('FCF = 同期经营现金流 - 同期资本开支')
  expect(active().querySelector('[aria-label="财务字段样稿详情"]')?.textContent).toContain('fixture:financial:US:0:2025:free_cash_flow')
  await input('搜索演示财务项目', 'not-a-field'); expect(active().textContent).toContain('暂无匹配的报表项目')
  await clickText('资产负债表'); expect(active().querySelectorAll('[data-financial-field]')).toHaveLength(3)
})
it('valuation discloses exact sample price/report time, currencies, formulas and blocked input semantics', async () => {
  await render('/financials?market=HK'); const pe = active().querySelector('[data-valuation="PE"]')!
  for (const t of ['倍', '不是 TTM', '2025-12-31', '2026-09-16T08:00:00Z', '24.00 HKD', 'synthetic-fixture']) expect(pe.textContent).toContain(t)
  const annual = loadFinancialPreview('HK').companies[0].reports[2], v = loadFinancialPreview('HK').companies[0].valuations[0]
  expect(v.value).toBe(24 / (annual.values.net_income.value! / 100)); expect(annual.available_at! < v.price_at!).toBe(true)
  expect(active().querySelector('[data-valuation="DIVIDEND_YIELD"]')?.textContent).toContain('BLOCKED'); expect(active().querySelector('[data-valuation="DIVIDEND_YIELD"]')?.textContent).toContain('—')
  await select('演示报告类型', 'QUARTER'); expect(pe.textContent).toContain('2025-12-31'); expect(active().querySelector('[aria-label="演示估值指标"]')?.textContent).toContain('不随上方报表选择重算')
})
it('trend dates map one-to-one; missing annual cash flow stays a gap without zero/interpolation', async () => {
  await render('/financials?market=US'); await select('演示趋势指标', 'operating_cash_flow')
  const trend = active().querySelector('[aria-label="演示财务趋势"]')!
  expect([...trend.querySelectorAll('[data-trend-row]')].map(r => r.getAttribute('data-trend-row'))).toEqual(['2023-12-31', '2024-12-31', '2025-12-31'])
  expect(trend.querySelector('[data-trend-row="2024-12-31"]')?.textContent).toContain('—'); expect(trend.querySelector('[data-trend-row="2024-12-31"]')?.textContent).toContain('不填零')
  expect(trend.querySelectorAll('circle')).toHaveLength(2); expect(trend.querySelectorAll('[data-trend-segment]')).toHaveLength(0)
  await select('演示趋势指标', 'revenue'); expect(trend.querySelectorAll('[data-trend-segment]')).toHaveLength(2)
  expect(trend.querySelector('svg')?.getAttribute('aria-label')).toContain('百万 USD')
})
it('missing report values/times remain null with independent reasons; PB cannot borrow another share basis', async () => {
  await render('/financials?market=HK'); await act(async () => active().querySelector<HTMLButtonElement>('[data-financial-symbol="9988.HK"]')!.click()); await select('演示报告类型', 'QUARTER')
  const overview = active().querySelector('[aria-label="公司财务样稿概览"]')!
  expect(overview.textContent).toContain('公告时间 UTC：—'); expect(overview.textContent).toContain('不以报告期或 generated_at 代替')
  expect(overview.querySelector('[data-financial-overview="net_income"]')?.textContent).toContain('—')
  expect(active().querySelector('[data-valuation="PB"]')?.textContent).toContain('BLOCKED'); expect(active().querySelector('[data-valuation="PB"]')?.textContent).toContain('不用当期市值股数或 EPS 加权股数替代')
})
it('market and browser navigation reset securities, report selection, field searches and details', async () => {
  await render('/financials?market=HK&keep=1'); await input('搜索财务样稿证券', '9988'); await select('演示报告类型', 'QUARTER'); await clickText('现金流量表'); await input('搜索演示财务项目', 'capex')
  await market(2); expect(active().textContent).not.toContain('9988.HK'); expect(active().querySelector<HTMLInputElement>('[aria-label="搜索财务样稿证券"]')?.value).toBe(''); expect(active().querySelector<HTMLSelectElement>('[aria-label="演示报告类型"]')?.value).toBe('ANNUAL')
  await act(async () => host.querySelector<HTMLButtonElement>('[data-back]')!.click())
  expect(active().dataset.financialMarket).toBe('HK'); expect(active().querySelector<HTMLInputElement>('[aria-label="搜索演示财务项目"]')?.value).toBe(''); expect(active().querySelector('[aria-label="公司财务样稿概览"]')?.textContent).toContain('0700.HK')
  expect(active().querySelector('[aria-label="财务字段样稿详情"]')?.textContent).toContain('营业收入'); expect(host.querySelector('[data-location]')?.textContent).toContain('keep=1')
})
it('fixture dates and values are deterministic; malformed basis, mixed identities and unproven timing are rejected', async () => {
  const d = loadFinancialPreview('US'); vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z')); expect(loadFinancialPreview('US')).toEqual(d); vi.useRealTimers()
  expect(loadFinancialPreview('US').companies).not.toBe(d.companies)
  type D = ReturnType<typeof loadFinancialPreview>
  for (const mutate of [(x: D) => { x.companies[0].reports[0].values.revenue.value = NaN }, (x: D) => { Object.assign(x.companies[0].reports[3], { flow_basis: 'YTD' }) }, (x: D) => { x.companies[0].market = 'HK' }, (x: D) => { x.companies[0].valuations[0].price_at = '2025-01-01T00:00:00Z' }, (x: D) => { x.companies[0].reports[2].values.net_income.value = null }, (x: D) => { x.companies[0].valuations[0].currency = 'HKD' }]) { const copy = loadFinancialPreview('US'); mutate(copy); expect(() => validateFinancialPreview(copy)).toThrow() }
  await render('/financials?market=US'); await input('搜索财务样稿证券', 'not-found'); expect(active().textContent).toContain('暂无匹配的财务样稿企业')
})
it('loading, error and empty fixtures retain the financial disclaimer without fallback', async () => {
  const empty = loadFinancialPreview('HK'); empty.companies = []
  for (const [s, text] of [[{ kind: 'loading' }, '加载中'], [{ kind: 'error' }, '加载失败'], [{ kind: 'ready', data: empty }, '暂无匹配的财务样稿企业']] as const) { await render('/financials', <FinancialPreview market="HK" state={s} />); expect(host.textContent).toContain(text); expect(host.textContent).toContain('非真实公司财报'); expect(host.querySelector('svg[role="img"]')).toBeNull() }
  expect(state.queries).toHaveLength(0); expect(state.api).not.toHaveBeenCalled()
})
