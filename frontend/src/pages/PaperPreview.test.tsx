// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Paper } from '@/custom/paper/extension'
import { PaperPreview } from '@/custom/damon/paper-preview/Presentation'
import { validatePaperPreview } from '@/custom/damon/paper-preview/contract'
import { loadPaperPreview } from '../../tests/fixtures/paper_preview'

const state = vi.hoisted(() => ({ queries: [] as unknown[][], mutate: vi.fn(), api: vi.fn(), refetch: vi.fn(), quote: vi.fn() }))
vi.mock('@tanstack/react-query', async original => ({ ...await original<typeof import('@tanstack/react-query')>(), useQueryClient: () => ({ invalidateQueries: vi.fn() }), useMutation: () => ({ mutate: state.mutate, isPending: false }), useQuery: ({ queryKey }: { queryKey: unknown[] }) => { state.queries.push(queryKey); return { data: queryKey[1] === 'compare' ? { accounts: [] } : undefined, isLoading: false, refetch: state.refetch } } }))
vi.mock('@/lib/useSharedQueries', () => ({ useQuoteStatus: () => { state.quote(); return { data: { is_trading_hours: false } } } }))
vi.mock('@/lib/api', async original => { const actual = await original<typeof import('@/lib/api')>(); return { ...actual, api: Object.fromEntries(Object.keys(actual.api).map(k => [k, (...args: unknown[]) => state.api(k, args)])) } })
vi.mock('echarts', () => ({ init: vi.fn() }))
let host: HTMLDivElement, root: Root
beforeEach(() => { Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.clearAllMocks(); state.queries = []; host = document.createElement('div'); document.body.append(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })
async function render(path = '/paper', element = <Paper />) {
  function Navigation() { const l = useLocation(), navigate = useNavigate(); return <><output data-location>{l.search}</output><button data-back onClick={() => navigate(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Navigation /></MemoryRouter>))
}
function active() { return host.querySelector<HTMLElement>('[data-paper-market]:not([hidden])')! }
async function market(i: number) { await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[i].click()) }
async function search(v: string) { const input = active().querySelector<HTMLInputElement>('input')!; await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, v); input.dispatchEvent(new Event('input', { bubbles: true })) }) }
async function filter(v: string) { const select = active().querySelector('select')!; await act(async () => { select.value = v; select.dispatchEvent(new Event('change', { bubbles: true })) }) }
it('CN preserves default comparison query, empty account, refresh and creation; leaving closes CN dialogs', async () => {
  await render(); expect(active().querySelector('h1')?.textContent).toBe('模拟盘'); expect(state.queries).toContainEqual(['paper', 'compare']); expect(state.quote).toHaveBeenCalled()
  expect(active().textContent).toContain('还没有对比账户')
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent?.trim() === '刷新')!.click()); expect(state.refetch).toHaveBeenCalledTimes(1)
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent?.trim() === '单账户')!.click())
  expect(host.querySelector('[aria-labelledby="setup-card-title"]')).not.toBeNull()
  await market(1); expect(host.querySelector('[aria-labelledby="setup-card-title"]')).toBeNull(); expect(host.querySelector('[data-paper-market="CN"]')).toBeNull()
  await market(0); expect(active().querySelector('h1')?.textContent).toBe('模拟盘'); expect(host.querySelector('[aria-labelledby="setup-card-title"]')).toBeNull(); expect(state.mutate).not.toHaveBeenCalled()
})
it.each(['HK', 'US'] as const)('direct %s is read-only, with independent fixtures and no production consumers', async m => {
  const fetch = vi.fn(), write = vi.spyOn(Storage.prototype, 'setItem'), notify = vi.fn(); vi.stubGlobal('fetch', fetch); vi.stubGlobal('Notification', notify)
  await render(`/paper?market=${m}`)
  for (const t of ['演示账户｜合成订单与成交｜非真实交易记录｜不构成投资建议', 'synthetic-fixture', 'PREVIEW', '2026-09-16', '2026-09-17T05:00:00Z', `fixture-paper-${m}`]) expect(active().textContent).toContain(t)
  expect(active().textContent).toContain(m === 'HK' ? '0700.HK' : 'AAPL.US'); expect(active().textContent).not.toContain(m === 'HK' ? 'AAPL.US' : '0700.HK')
  await act(async () => active().querySelectorAll<HTMLButtonElement>('button:disabled').forEach(b => b.click()))
  expect(state.queries).toHaveLength(0); for (const spy of [state.quote, state.mutate, state.api, fetch, write, notify]) expect(spy).not.toHaveBeenCalled()
  expect(host.querySelector('[data-paper-market="CN"]')).toBeNull()
})
it.each(['HK', 'US'] as const)('%s accounting separates gross PnL, fee and net return; cash derives only from fills', async m => {
  await render(`/paper?market=${m}`); const d = loadPaperPreview(m)
  expect(d.cash).toBe(d.initial_cash - d.fills.reduce((n, f) => n + f.qty * f.price + f.fee, 0))
  expect(d.total_assets).toBe(d.cash + d.market_value); expect(d.total_pnl_net).toBe(d.realized_pnl_gross + d.unrealized_pnl_gross - d.fees)
  expect(d.return_pct).toBe(d.total_pnl_net / d.initial_cash)
  for (const k of ['initial_cash', 'cash', 'market_value', 'total_assets', 'realized_pnl_gross', 'unrealized_pnl_gross', 'fees', 'total_pnl_net'] as const) expect(active().querySelector(`[data-paper-value="${k}"]`)?.textContent).toContain(d[k].toFixed(2))
  expect(active().querySelector('[aria-label="合成持仓"] tbody')?.textContent).toContain('+5.00%'); expect(active().textContent).toContain('已实现盈亏为 0：样稿无卖出成交')
  expect(active().textContent).toContain(m === 'HK' ? '+1.28%' : '+0.58%')
})
it('order search, state filter, reference-price sorting and detail remain local; pending never becomes a fill', async () => {
  await render('/paper?market=US'); await search('Apple'); expect(active().querySelector('[aria-label="合成订单"] tbody')?.querySelectorAll('tr')).toHaveLength(1)
  await search(''); await filter('pending'); const details = active().querySelector('[aria-label="订单样本详情"]')!
  expect(details.textContent).toContain('MSFT.US'); expect(details.textContent).toContain('关联成交样本数：0'); expect(details.textContent).toContain('未提供委托参考价格')
  expect(active().querySelector('[aria-label="合成成交"]')?.querySelectorAll('article')).toHaveLength(2)
  await filter('ALL'); const th = [...active().querySelector('[aria-label="合成订单"]')!.querySelectorAll('th')].find(h => h.textContent?.startsWith('委托参考价'))!
  await act(async () => th.click()); let rows = active().querySelectorAll<HTMLButtonElement>('[data-paper-order]'); expect(rows[0].textContent).toBe('NVDA.US'); expect(rows[2].textContent).toBe('MSFT.US')
  await act(async () => th.click()); rows = active().querySelectorAll<HTMLButtonElement>('[data-paper-order]'); expect(rows[0].textContent).toBe('AAPL.US'); expect(rows[2].textContent).toBe('MSFT.US')
  await act(async () => rows[1].click()); expect(active().querySelector('[aria-label="订单样本详情"]')?.textContent).toContain('fixture-order-US-1')
  await search('nonexistent'); expect(active().textContent).toContain('暂无匹配的订单样本'); expect(active().textContent).toContain('暂无匹配的持仓样本'); expect(active().textContent).toContain('暂无匹配的成交样本')
})
it('fill evidence uses explicit fill price/time rather than submission or latest reference', async () => {
  await render('/paper?market=HK'); const d = loadPaperPreview('HK'), f = d.fills[0], o = d.orders[0]
  expect(o.ref_price).not.toBe(f.price); expect(o.submitted_at).not.toBe(f.filled_at); expect(d.positions[0].reference_price).not.toBe(f.price)
  const t = active().querySelector('[aria-label="合成成交"] article')!.textContent!
  for (const v of [f.sample_id, f.order_sample_id, f.filled_at, f.evidence, '成交价：300.00', '费用：10.00']) expect(t).toContain(v)
  expect(t).not.toContain(o.submitted_at)
})
it('missing sellable quantity, reference price and win rate retain null and reasons', async () => {
  await render('/paper?market=HK'); await filter('pending'); const d = loadPaperPreview('HK')
  expect(d.positions.every(p => p.available_qty === null)).toBe(true); expect(d.orders[2].ref_price).toBeNull(); expect(d.win_rate).toBeNull()
  for (const t of ['可卖数量未知', '不套用 CN T+1', '未提供委托参考价格', '胜率：—', '无已平仓回合', 'PIT/vintage']) expect(active().textContent).toContain(t)
})
it('URL navigation keeps independent HK/US filters, preserving unrelated params and browser back', async () => {
  await render('/paper?market=HK&keep=1'); await search('腾讯'); await market(2)
  expect(active().querySelector<HTMLInputElement>('input')?.value).toBe(''); await filter('pending')
  await act(async () => host.querySelector<HTMLButtonElement>('[data-back]')!.click())
  expect(active().dataset.paperMarket).toBe('HK'); expect(active().querySelector<HTMLInputElement>('input')?.value).toBe('腾讯'); expect(active().textContent).not.toContain('AAPL.US'); expect(host.querySelector('[data-location]')?.textContent).toContain('keep=1')
  await market(2); expect(active().querySelector('select')?.value).toBe('pending'); expect(active().querySelector('[aria-label="合成订单"] tbody')?.textContent).toContain('MSFT.US')
})
it('fixed dates and fresh fixtures do not depend on system date; malformed ledger/provenance is rejected', async () => {
  const before = loadPaperPreview('US'); vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z')); expect(loadPaperPreview('US')).toEqual(before); vi.useRealTimers()
  const other = loadPaperPreview('US'); expect(other.positions).not.toBe(before.positions)
  for (const mutate of [(d: typeof before) => { d.cash += 1 }, (d: typeof before) => { d.fills[0].order_sample_id = d.orders[2].sample_id }, (d: typeof before) => { d.positions[0].market = 'HK' }, (d: typeof before) => { d.orders[0].ref_price = Infinity }, (d: typeof before) => { d.total_assets = NaN }]) { const d = loadPaperPreview('US'); mutate(d); expect(() => validatePaperPreview(d)).toThrow() }
  await render('/paper?market=US'); const history = active().querySelector('[aria-label="演示资产历史"]')!
  for (const t of ['2026-09-14', '2026-09-15', '2026-09-16', '非回测']) expect(history.textContent).toContain(t)
})
it('loading/error retain declaration and never fallback to production', async () => {
  for (const kind of ['loading', 'error'] as const) { await render('/paper', <PaperPreview market="HK" state={{ kind }} />); expect(host.textContent).toContain('非真实交易记录'); expect(host.textContent).toContain(kind === 'loading' ? '加载中' : '加载失败'); expect(host.querySelector('table')).toBeNull() }
  expect(state.queries).toHaveLength(0); expect(state.api).not.toHaveBeenCalled()
})
