// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Lots } from '@/custom/lots/extension'
import { LotsPreview } from '@/custom/damon/lots-preview/Presentation'
import { loadLotsPreview } from '../../tests/fixtures/lots_preview'
import { validateLotsPreview, type LotsPreviewData } from '@/custom/damon/lots-preview/contract'

const state = vi.hoisted(() => ({ queries: [] as unknown[][], mutate: vi.fn(), apiCall: vi.fn() }))
const cnLots = [{ id: 'fixture-cn-lot', symbol: '600000.SH', qty: 100, cost_price: 10, buy_date: '2026-09-01', target_pct: 10, stop_pct: 5, remind_date: null, lead_days: 1 }]
const cnDaily = { data: { '600000.SH': [{ close: 11 }] } }
vi.mock('@tanstack/react-query', async original => ({ ...await original<typeof import('@tanstack/react-query')>(),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({ mutate: state.mutate, isPending: false }),
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => { state.queries.push(queryKey); return { data: queryKey[0] === 'lots' ? { lots: cnLots } : queryKey[0] === 'lots-kline' ? cnDaily : queryKey[0] === 'instrument-names' ? { names: { '600000.SH': 'CN测试样例' } } : undefined, isLoading: false, refetch: vi.fn() } },
}))
vi.mock('@/lib/api', async original => { const actual = await original<typeof import('@/lib/api')>(); return { ...actual, api: Object.fromEntries(Object.keys(actual.api).map(key => [key, (...args: unknown[]) => state.apiCall(key, args)])) } })
vi.mock('@/components/StockPreviewDialog', () => ({ StockPreviewDialog: () => null }))
let host: HTMLDivElement, root: Root
beforeEach(() => { Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); state.queries = []; vi.clearAllMocks(); host = document.createElement('div'); document.body.append(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })
async function render(path = '/lots', element = <Lots />) {
  function Navigation() { const location = useLocation(), navigate = useNavigate(); return <><output data-location>{location.search}</output><button data-back onClick={() => navigate(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Navigation /></MemoryRouter>))
}
function active() { return host.querySelector<HTMLElement>('[data-lots-market]:not([hidden])')! }
async function market(index: number) { await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[index].click()) }
async function search(value: string) { const input = active().querySelector<HTMLInputElement>('input')!; await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })) }) }
async function filter(value: string) { const input = active().querySelector<HTMLSelectElement>('select')!; await act(async () => { input.value = value; input.dispatchEvent(new Event('change', { bubbles: true })) }) }
it('CN retains lot/name/daily queries, original PnL percent, editing and two-step delete', async () => {
  await render()
  expect(active().querySelector('h1')?.textContent).toBe('持仓提醒')
  expect(state.queries).toContainEqual(['lots']); expect(state.queries).toContainEqual(['lots-kline', '600000.SH'])
  expect(active().querySelector('tbody')?.textContent).toContain('+10.00%')
  await act(async () => active().querySelector<HTMLButtonElement>('[title="编辑"]')!.click())
  expect(active().querySelector('[aria-label="编辑批次"]')).not.toBeNull()
  await market(1); expect(active().querySelector('[aria-label="编辑批次"]')).toBeNull()
  await market(0); expect(active().querySelector('[aria-label="编辑批次"]')).not.toBeNull()
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent === '取消')!.click())
  await act(async () => active().querySelector<HTMLButtonElement>('[title="删除 (同步删除生成的监控规则)"]')!.click())
  expect(state.mutate).not.toHaveBeenCalled()
  await act(async () => active().querySelector<HTMLButtonElement>('[title="再次点击确认删除"]')!.click())
  expect(state.mutate).toHaveBeenCalledWith('fixture-cn-lot')
})
it.each(['HK', 'US'] as const)('direct %s is independent of real lots, accounts, prices, reminders, notifications and storage', async m => {
  const fetch = vi.fn(), write = vi.spyOn(Storage.prototype, 'setItem'), notify = vi.fn(); vi.stubGlobal('fetch', fetch); vi.stubGlobal('Notification', notify)
  await render(`/lots?market=${m}`)
  for (const text of ['演示数据｜非真实账户持仓｜非生产行情｜不构成投资建议', 'synthetic-fixture', 'PREVIEW', '2026-09-16', '2026-09-17T04:00:00Z', '已知样稿子集：2 / 3']) expect(active().textContent).toContain(text)
  expect(active().querySelectorAll('tbody tr')).toHaveLength(3)
  expect(active().textContent).toContain(m === 'HK' ? '0700.HK' : 'AAPL.US')
  expect(active().textContent).not.toContain(m === 'HK' ? 'AAPL.US' : '0700.HK')
  expect(active().textContent).not.toContain('600000.SH')
  await act(async () => active().querySelectorAll<HTMLButtonElement>('button:disabled').forEach(b => b.click()))
  expect(state.queries).toHaveLength(0)
  for (const spy of [state.apiCall, state.mutate, fetch, write, notify]) expect(spy).not.toHaveBeenCalled()
  expect(active().querySelector('a')).toBeNull(); expect(host.querySelector('[data-lots-market="CN"]')).toBeNull()
})
it.each(['HK', 'US'] as const)('%s positions and known-subset PnL are consistent, with unknown whole-portfolio totals', async m => {
  await render(`/lots?market=${m}`)
  const data = loadLotsPreview(m)
  for (const row of data.rows.slice(0, 2)) expect(row.values.pnl_amount).toBeCloseTo(row.values.qty! * (row.values.reference_price! - row.values.cost_price!))
  expect(active().querySelector('[data-lot-overview="known_pnl_amount"]')?.textContent).toContain(m === 'HK' ? '1300.00 HKD' : '60.00 USD')
  expect(active().querySelector('[data-lot-overview="total_pnl_amount"]')?.textContent).toContain('—')
  expect(active().querySelector('tbody')?.textContent).toContain('+5.00%')
  expect(active().querySelector('tbody')?.textContent).toContain('-5.00%')
  expect(active().textContent).toContain('不把已知子集冒充总额')
})
it('search, reminder-state filtering and numeric PnL sorting stay local with nulls last', async () => {
  await render('/lots?market=HK'); await search('腾讯')
  expect(active().querySelectorAll('tbody tr')).toHaveLength(1); expect(active().querySelectorAll('article')).toHaveLength(1)
  await search(''); await filter('BLOCKED_SAMPLE')
  expect(active().querySelector('tbody')?.textContent).toContain('9988.HK')
  await filter('ALL')
  const th = [...active().querySelectorAll('th')].find(th => th.textContent?.startsWith('演示盈亏金额'))!
  await act(async () => th.click())
  expect(active().querySelector('tbody tr')?.textContent).toContain('9988.HK'); expect([...active().querySelectorAll('tbody tr')].at(-1)?.textContent).toContain('3690.HK')
  await act(async () => th.click())
  expect(active().querySelector('tbody tr')?.textContent).toContain('0700.HK'); expect([...active().querySelectorAll('tbody tr')].at(-1)?.textContent).toContain('3690.HK')
})
it('risk and existing rule structure are read-only, with percent units and fixed reminder evidence', async () => {
  await render('/lots?market=US')
  const detail = active().querySelector('[aria-label="持仓样本详情"]')!
  for (const text of ['171.00', '198.00', '+2.00%', '集中度（演示）：—', '完整组合未知', 'fixture:lots:US:position:0:v1']) expect(detail.textContent).toContain(text)
  await act(async () => detail.querySelector<HTMLElement>('summary')!.click())
  expect(detail.querySelector('details')?.open).toBe(true)
  expect(detail.textContent).toContain('target_pct：10 %'); expect(detail.textContent).toContain('stop_pct：5 %')
  expect(detail.textContent).toContain('2026-09-30'); expect(detail.textContent).toContain('lead_days：2')
  expect(active().querySelector('article')?.textContent).toContain('2026-09-17T01:00:00Z')
  expect(active().querySelector('article')?.textContent).toContain('fixture:lots:US:reminder:0:v1')
  expect(state.apiCall).not.toHaveBeenCalled()
})
it('missing values, rule and reminder fields remain null with explicit reasons', async () => {
  await render('/lots?market=US'); await filter('UNKNOWN')
  const detail = active().querySelector('[aria-label="持仓样本详情"]')!
  expect(active().querySelector('tbody')?.textContent).toContain('MSFT.US')
  expect(active().querySelector('tbody')?.textContent).toContain('—')
  for (const text of ['rule_sample.target_pct', 'reminder.checked_at', '均保留 null', '真实账户/持仓未接入']) expect(detail.textContent).toContain(text)
  expect(active().querySelector('article')?.textContent).toContain('—（提醒状态未知）')
  expect(loadLotsPreview('US').rows[2].values.qty).toBeNull()
})
it('market changes and browser back preserve separate filters/details and other URL parameters', async () => {
  await render('/lots?market=HK&keep=1'); await search('3690.HK')
  await market(2); expect(active().querySelector<HTMLInputElement>('input')?.value).toBe('')
  expect(active().querySelectorAll('tbody tr')).toHaveLength(3)
  await filter('BLOCKED_SAMPLE')
  await act(async () => host.querySelector<HTMLButtonElement>('[data-back]')!.click())
  expect(active().dataset.lotsMarket).toBe('HK'); expect(active().querySelector<HTMLInputElement>('input')?.value).toBe('3690.HK')
  expect(active().textContent).not.toContain('NVDA.US'); expect(host.querySelector('[data-location]')?.textContent).toContain('keep=1')
})
it('empty search, loading/error/empty fixture keep the non-account declaration with no fallback', async () => {
  await render('/lots?market=HK'); await search('no-synthetic-lot')
  expect(active().textContent).toContain('暂无匹配的持仓提醒样本')
  const empty = loadLotsPreview('HK'); Object.assign(empty, { rows: [], overview: { position_count: 0, valued_count: 0, known_cost_amount: null, known_reference_amount: null, known_pnl_amount: null, total_pnl_amount: null, missing_reason: '无样稿' } })
  for (const [s, text] of [[{ kind: 'loading' }, '加载中'], [{ kind: 'error' }, '加载失败'], [{ kind: 'ready', data: empty }, '暂无持仓演示样本']] as const) {
    await render('/lots', <LotsPreview market="HK" state={s} />); expect(host.textContent).toContain(text); expect(host.textContent).toContain('非真实账户持仓'); expect(host.querySelector('tbody')).toBeNull()
  }
  expect(state.queries).toHaveLength(0)
})
it('dates, times and nested fixture objects are deterministic without reading the current clock', () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z'))
  const a = loadLotsPreview('HK'), b = loadLotsPreview('HK')
  expect(a).toEqual(b); expect(a.rows[0].reminder).not.toBe(b.rows[0].reminder); expect(a.rows[0].rule_sample).not.toBe(b.rows[0].rule_sample)
  expect(a.trading_date).toBe('2026-09-16'); expect(a.rows[0].reminder.checked_at).toBe('2026-09-17T01:00:00Z')
})
it('rejects mixed markets/currencies, production flags, nonfinite data, unexplained nulls and false complete totals', () => {
  const bad = (edit: (d: LotsPreviewData) => unknown) => { const d = structuredClone(loadLotsPreview('HK')); edit(d); expect(() => validateLotsPreview(d)).toThrow() }
  bad(d => Object.assign(d, { is_production: true }))
  bad(d => Object.assign(d.rows[0], { market: 'US' }))
  bad(d => Object.assign(d.rows[0], { currency: 'USD' }))
  bad(d => Object.assign(d.rows[0].values, { qty: Infinity }))
  bad(d => Object.assign(d.rows[0].values, { pnl_amount: NaN }))
  bad(d => Object.assign(d.rows[2], { reasons: [] }))
  bad(d => Object.assign(d.rows[2].reminder, { sample_state: 'NORMAL' }))
  bad(d => Object.assign(d.overview, { total_pnl_amount: 1300 }))
  bad(d => Object.assign(d.rows[0].reminder, { checked_at: '2026-09-17 01:00:00' }))
})
