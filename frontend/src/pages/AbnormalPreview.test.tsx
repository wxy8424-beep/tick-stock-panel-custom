// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { AbnormalMoves } from '@/custom/abnormal/extension'
import { AbnormalPreview } from '@/custom/damon/abnormal-preview/Presentation'
import { loadAbnormalPreview } from '../../tests/fixtures/abnormal_preview'
import { validateAbnormalPreview, type AbnormalPreviewData } from '@/custom/damon/abnormal-preview/contract'

const state = vi.hoisted(() => ({ realQueries: false, queries: [] as unknown[][], quote: vi.fn(), apiCall: vi.fn(), refetch: vi.fn() }))
vi.mock('@tanstack/react-query', async original => {
  const actual = await original<typeof import('@tanstack/react-query')>()
  return { ...actual, useQuery: (options: Parameters<typeof actual.useQuery>[0]) => {
    if (state.realQueries) return actual.useQuery(options)
    state.queries.push([...options.queryKey]); return { data: undefined, isLoading: false, refetch: state.refetch }
  } }
})
vi.mock('@/lib/useSharedQueries', () => ({ useQuoteStatus: () => { state.quote(); return { data: { is_trading_hours: state.realQueries } } } }))
vi.mock('@/lib/api', async original => { const actual = await original<typeof import('@/lib/api')>(); return { ...actual, api: Object.fromEntries(Object.keys(actual.api).map(key => [key, (...args: unknown[]) => state.apiCall(key, args)])) } })
vi.mock('@/components/StockPreviewDialog', () => ({ StockPreviewDialog: () => null }))
let host: HTMLDivElement, root: Root
let timingClient: QueryClient | undefined
beforeEach(() => { Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); localStorage.clear(); state.realQueries = false; state.queries = []; vi.clearAllMocks(); state.apiCall.mockReset(); host = document.createElement('div'); document.body.append(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); timingClient?.clear(); timingClient = undefined; host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })
async function render(path = '/abnormal', element = <AbnormalMoves />) {
  function Navigation() { const location = useLocation(), navigate = useNavigate(); return <><output data-location>{location.search}</output><button data-back onClick={() => navigate(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Navigation /></MemoryRouter>))
}
function active() { return host.querySelector<HTMLElement>('[data-abnormal-market]:not([hidden])')! }
it.each(['HK', 'US'])('%s Preview header separates its narrow action and reserves menu space', async m => {
  await render(`/abnormal?market=${m}`)
  const header = active().querySelector('header')!
  expect(header.querySelector('h1')?.textContent).toBe(`${m} 异动监控 · Preview`)
  for (const token of ['pl-14', 'md:pl-5', 'max-md:flex-col', 'max-md:items-stretch', '[&>div>div]:flex-wrap', 'md:[&>div>div]:flex-nowrap']) expect(header.classList.contains(token)).toBe(true)
  const action = header.querySelector<HTMLButtonElement>('button')!
  expect(action.disabled).toBe(true)
  expect(action.title).toContain('Preview 模式不可执行')
  expect(state.apiCall).not.toHaveBeenCalled()
})
async function market(index: number) { await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[index].click()) }
async function search(value: string, selector = 'input') { const input = active().querySelector<HTMLInputElement>(selector)!; await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })) }) }
async function select(label: string, value: string) { const input = active().querySelector<HTMLSelectElement>(`[aria-label="${label}"]`)!; await act(async () => { input.value = value; input.dispatchEvent(new Event('change', { bubbles: true })) }) }
it('CN default retains intraday query, search, original refresh and rule navigation', async () => {
  await render('/abnormal?keep=1')
  const cn = active()
  expect(cn.querySelector('h1')?.textContent).toBe('异动监控')
  expect(state.queries).toContainEqual(['abnormal-intraday', 500])
  expect(cn.querySelector('a')?.getAttribute('href')).toBe('/monitor')
  await search('CN保留搜索', '[placeholder="搜索代码/名称"]')
  await act(async () => cn.querySelector<HTMLButtonElement>('[title="立即刷新"]')!.click())
  expect(state.refetch).toHaveBeenCalledTimes(1)
  await market(1); await market(2); await market(0)
  expect(active()).toBe(cn); expect(cn.querySelector<HTMLInputElement>('[placeholder="搜索代码/名称"]')?.value).toBe('CN保留搜索')
  expect(cn.textContent).not.toContain('演示数据｜非生产行情')
})
it('CN auction/deviation tab query and disabled-by-default calculation semantics remain intact', async () => {
  await render()
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent?.includes('竞价异动'))!.click())
  expect(state.queries).toContainEqual(['auction-benchmark', 'latest'])
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent?.includes('偏移异动'))!.click())
  expect(state.queries).toContainEqual(['abnormal-overview', .5, 300])
  expect(active().textContent).toContain('监控未开启')
  expect([...active().querySelectorAll('button')].some(b => b.textContent?.includes('开启监控'))).toBe(true)
  expect(state.refetch).not.toHaveBeenCalled()
  expect(state.apiCall).not.toHaveBeenCalled()
})
it.each(['HK', 'US'] as const)('direct %s shows its own samples without production queries, requests, notifications or writes', async m => {
  const fetch = vi.fn(), write = vi.spyOn(Storage.prototype, 'setItem'), notify = vi.fn(); vi.stubGlobal('fetch', fetch); vi.stubGlobal('Notification', notify)
  await render(`/abnormal?market=${m}`)
  for (const text of ['演示数据｜非生产行情｜不构成真实异动事件或投资信号', '2026-09-16', 'synthetic-fixture', 'PREVIEW', '2026-09-17T03:00:00Z', '生产检测与时段状态未验证']) expect(active().textContent).toContain(text)
  expect(active().textContent).toContain(m === 'HK' ? '腾讯控股' : 'Apple')
  expect(active().textContent).not.toContain(m === 'HK' ? 'AAPL.US' : '0700.HK')
  expect(active().querySelectorAll('tbody tr')).toHaveLength(m === 'HK' ? 3 : 4)
  await act(async () => active().querySelector<HTMLButtonElement>('button:disabled')!.click())
  expect(active().querySelector('a')).toBeNull()
  expect(host.querySelector('[data-abnormal-market="CN"]')).toBeNull()
  expect(state.queries).toHaveLength(0)
  for (const spy of [state.quote, state.apiCall, state.refetch, fetch, write, notify]) expect(spy).not.toHaveBeenCalled()
})
it('type, severity, name/code search and empty states operate on the selected fixture', async () => {
  await render('/abnormal?market=HK')
  await select('演示异动类型', 'intraday_breakout')
  expect(active().querySelectorAll('tbody tr')).toHaveLength(1); expect(active().querySelector('tbody')?.textContent).toContain('9988.HK')
  await select('演示异动严重程度', 'high'); expect(active().textContent).toContain('暂无匹配的异动样本')
  await select('演示异动类型', 'ALL'); await select('演示异动严重程度', 'ALL'); await search('腾讯')
  expect(active().querySelectorAll('tbody tr')).toHaveLength(1)
  await search('0700.HK'); expect(active().querySelector('tbody')?.textContent).toContain('腾讯控股')
  await search('not-a-sample'); expect(active().textContent).toContain('暂无匹配的异动样本')
  expect(active().textContent).toContain('演示数据｜非生产行情｜不构成真实异动事件或投资信号')
})
it('sorts time, fractional change and severity only on known values with nulls always last', async () => {
  await render('/abnormal?market=US')
  const header = (text: string) => [...active().querySelectorAll('th')].find(th => th.textContent?.startsWith(text))!
  await act(async () => header('演示涨跌幅').click())
  expect(active().querySelector('tbody tr')?.textContent).toContain('NVDA.US')
  expect([...active().querySelectorAll('tbody tr')].at(-1)?.textContent).toContain('MSFT.US')
  await act(async () => header('演示涨跌幅').click())
  expect(active().querySelector('tbody tr')?.textContent).toContain('+3.20%')
  expect(active().querySelector('tbody')?.textContent).toContain('0.00%')
  await act(async () => header('严重程度').click())
  expect(active().querySelector('tbody tr')?.textContent).toContain('MSFT.US')
  await act(async () => header('严重程度').click())
  expect(active().querySelector('tbody tr')?.textContent).toContain('AAPL.US')
  expect([...active().querySelectorAll('tbody tr')].at(-1)?.textContent).toContain('AMZN.US')
  await act(async () => header('固定事件时间').click())
  expect(active().querySelector('tbody tr')?.textContent).toContain('MSFT.US')
  expect([...active().querySelectorAll('tbody tr')].at(-1)?.textContent).toContain('AMZN.US')
})
it('detail exposes null evidence/reasons, fixed conditions and blockers without reusing production event schema', async () => {
  await render('/abnormal?market=US')
  await act(async () => active().querySelector<HTMLButtonElement>('[data-sample-id="fixture-abnormal-US-3"]')!.click())
  const detail = active().querySelector('[aria-label="异动样本详情"]')!
  for (const text of ['AMZN.US', '—（状态未知）', '未编写事件时间', 'sample_state', 'fixture:abnormal:US:2026-09-16:3:v1', 'is_production: false', 'PIT/vintage', '不证明任何真实触发']) expect(detail.textContent).toContain(text)
  await act(async () => active().querySelector<HTMLButtonElement>('[data-sample-id="fixture-abnormal-US-2"]')!.click())
  expect(detail.textContent).toContain('阻塞样例'); expect(detail.textContent).toContain('演示涨跌幅：—'); expect(detail.textContent).toContain('不计算历史波动指标')
  expect(loadAbnormalPreview('US').rows.every(row => !('event_id' in row) && !('rule_id' in row))).toBe(true)
  expect(state.apiCall).not.toHaveBeenCalled()
})
it('market switching and browser back retain separate filters, selected detail and URL parameters', async () => {
  await render('/abnormal?market=HK&keep=fixture'); await search('美团')
  expect(active().querySelector('[aria-label="异动样本详情"]')?.textContent).toContain('3690.HK')
  await market(2)
  expect(active().querySelector<HTMLInputElement>('input')?.value).toBe('')
  expect(active().querySelectorAll('tbody tr')).toHaveLength(4)
  await select('演示异动严重程度', 'UNKNOWN'); expect(active().querySelectorAll('tbody tr')).toHaveLength(1)
  await act(async () => host.querySelector<HTMLButtonElement>('[data-back]')!.click())
  expect(active().dataset.abnormalMarket).toBe('HK'); expect(active().querySelector<HTMLInputElement>('input')?.value).toBe('美团')
  expect(active().textContent).not.toContain('AMZN.US'); expect(host.querySelector('[data-location]')?.textContent).toContain('keep=fixture')
})
it('loading/error/empty fixture preserve declarations and never fall back to production', async () => {
  for (const [value, text] of [[{ kind: 'loading' }, '加载中'], [{ kind: 'error' }, '加载失败'], [{ kind: 'ready', data: { ...loadAbnormalPreview('HK'), rows: [] } }, '暂无异动演示样本']] as const) {
    await render('/abnormal', <AbnormalPreview market="HK" state={value} />)
    expect(host.textContent).toContain(text); expect(host.textContent).toContain('演示数据｜非生产行情｜不构成真实异动事件或投资信号')
    expect(host.querySelector('tbody')).toBeNull()
  }
  expect(state.queries).toHaveLength(0)
})
it('fixtures use fixed timestamps and independent objects with no date-driven event creation', () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z'))
  const a = loadAbnormalPreview('HK'), b = loadAbnormalPreview('HK')
  expect(a).toEqual(b); expect(a.rows[0]).not.toBe(b.rows[0]); expect(a.rows[0].blockers).not.toBe(b.rows[0].blockers)
  expect(a.trading_date).toBe('2026-09-16'); expect(a.rows[0].event_time).toBe('2026-09-16T06:05:00Z')
})
it('multiple synthetic events for one security keep separate sample identities and details', async () => {
  const data = loadAbnormalPreview('HK')
  Object.assign(data.rows[1], { symbol: data.rows[0].symbol, name: data.rows[0].name })
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
  await render('/abnormal', <AbnormalPreview market="HK" state={{ kind: 'ready', data }} />)
  expect(host.querySelectorAll('tbody tr')).toHaveLength(3)
  await act(async () => host.querySelector<HTMLButtonElement>('[data-sample-id="fixture-abnormal-HK-1"]')!.click())
  expect(host.querySelector('[aria-label="异动样本详情"]')?.textContent).toContain('fixture:abnormal:HK:2026-09-16:1:v1')
  expect(errors.mock.calls.flat().join(' ')).not.toContain('same key')
})
it('rejects production flags, mixed identity, nonfinite values, naive time and unexplained nulls', () => {
  const bad = (edit: (d: AbnormalPreviewData) => unknown) => { const d = structuredClone(loadAbnormalPreview('US')); edit(d); expect(() => validateAbnormalPreview(d)).toThrow() }
  bad(d => Object.assign(d, { is_production: true }))
  bad(d => Object.assign(d.rows[0], { market: 'HK' }))
  bad(d => Object.assign(d.rows[0], { change_pct: NaN }))
  bad(d => Object.assign(d.rows[0], { change_pct: Infinity }))
  bad(d => Object.assign(d.rows[0], { event_time: '2026-09-16 14:05:00' }))
  bad(d => Object.assign(d.rows[2], { reasons: [] }))
  bad(d => Object.assign(d.rows[3], { sample_state: 'NORMAL' }))
})

function SharedQueryProbe() {
  useQuery({ queryKey: ['a14-shared'], queryFn: () => state.apiCall('shared', []), refetchInterval: 5000 })
  return null
}
const calls = (name: string) => state.apiCall.mock.calls.filter(call => call[0] === name).length
async function tick(ms = 20) { await act(async () => { await vi.advanceTimersByTimeAsync(ms) }) }
async function renderTiming() {
  vi.useFakeTimers(); state.realQueries = true
  timingClient = new QueryClient()
  await render('/abnormal', <QueryClientProvider client={timingClient}><AbnormalMoves /><SharedQueryProbe /></QueryClientProvider>)
  await tick()
}
async function tab(text: string) {
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent?.includes(text))!.click())
  await tick()
}
const result = { rows: [], counts: {}, bench_rt_pct: 0, asof: '2026-10-19T02:00:00Z', cache_date: '2026-10-16', includes_today: false }
const answer = (name: string) => name === 'auctionBenchmark' ? { state: 'source_unavailable' } : name === 'watchlistList' ? { symbols: [] } : result
it.each([1, 2])('hidden CN intraday stops polling and invalidation for market %s, retaining search', async target => {
  state.apiCall.mockImplementation(async name => answer(name))
  await renderTiming(); const cn = active()
  await search('A14 retained', '[placeholder="搜索代码/名称"]')
  const before = calls('abnormalIntraday')
  await tick(60_100); expect(calls('abnormalIntraday')).toBeGreaterThan(before)
  await market(target); await tick()
  const page = calls('abnormalIntraday'), shared = calls('shared')
  await act(async () => { await timingClient!.invalidateQueries() }); await tick(180_100)
  expect(calls('abnormalIntraday')).toBe(page); expect(calls('shared')).toBeGreaterThan(shared)
  await act(async () => cn.querySelector<HTMLButtonElement>('[title="立即刷新"]')!.click())
  expect(calls('abnormalIntraday')).toBe(page)
  await market(0); await tick()
  expect(active()).toBe(cn)
  expect(cn.querySelector<HTMLInputElement>('[placeholder="搜索代码/名称"]')?.value).toBe('A14 retained')
  expect(calls('abnormalIntraday')).toBeGreaterThan(page)
})
it('hidden auction cannot refetch on invalidation and preserves the selected view', async () => {
  state.apiCall.mockImplementation(async name => answer(name))
  await renderTiming(); await tab('竞价异动')
  const key = ['auction-benchmark', 'latest']
  expect(timingClient!.getQueryState(key)?.status).toBe('success')
  const before = state.apiCall.mock.calls.length
  await market(1)
  await act(async () => { await timingClient!.invalidateQueries({ queryKey: key }) }); await tick()
  expect(state.apiCall.mock.calls.length).toBe(before)
  await market(0); await tick()
  expect(timingClient!.getQueryState(key)?.fetchStatus).toBe('idle')
  expect(active().textContent).toContain('竞价')
  expect(state.apiCall.mock.calls.length).toBeGreaterThan(before)
})
it.each([1, 2])('late deviation response is cached but not persisted in market %s; CN return resumes', async target => {
  localStorage.setItem('abnormal_enabled', 'true')
  let resolve!: (value: unknown) => void
  const pending = new Promise(r => { resolve = r })
  state.apiCall.mockImplementation(name => name === 'abnormalOverview' ? pending : Promise.resolve(answer(name)))
  const write = vi.spyOn(Storage.prototype, 'setItem')
  await renderTiming(); await tab('偏移异动')
  await search('A14 deviation', '[placeholder="搜索代码/名称"]')
  expect(calls('abnormalOverview')).toBe(1)
  await market(target)
  await act(async () => resolve(result)); await tick()
  expect(timingClient!.getQueryData(['abnormal-overview', .5, 300])).toEqual(result)
  expect(write.mock.calls.filter(call => call[0] === 'abnormal_last_result')).toHaveLength(0)
  const shared = calls('shared')
  await act(async () => { await timingClient!.invalidateQueries({ queryKey: ['abnormal-overview'] }) })
  await tick(180_100)
  expect(calls('abnormalOverview')).toBe(1); expect(calls('shared')).toBeGreaterThan(shared)
  expect(write.mock.calls.filter(call => call[0] === 'abnormal_last_result')).toHaveLength(0)
  await market(0); await tick()
  expect(active().querySelector<HTMLInputElement>('[placeholder="搜索代码/名称"]')?.value).toBe('A14 deviation')
  expect(calls('abnormalOverview')).toBeGreaterThan(1)
  expect(write.mock.calls.filter(call => call[0] === 'abnormal_last_result').length).toBeGreaterThan(0)
})
it.each([1, 2])('deviation polling and watchlist filtering pause in market %s without losing CN state', async target => {
  localStorage.setItem('abnormal_enabled', 'true')
  state.apiCall.mockImplementation(async name => answer(name))
  await renderTiming(); await tab('偏移异动')
  const cn = active(), checkbox = cn.querySelector<HTMLInputElement>('[title="只看自选列表中的标的"] input')!
  await act(async () => checkbox.click()); await tick()
  expect(calls('watchlistList')).toBe(1)
  const initial = calls('abnormalOverview')
  await tick(60_100); expect(calls('abnormalOverview')).toBeGreaterThan(initial)
  await market(target); await tick()
  const overview = calls('abnormalOverview'), watchlist = calls('watchlistList')
  const write = vi.spyOn(Storage.prototype, 'setItem')
  await act(async () => { await timingClient!.invalidateQueries() }); await tick(180_100)
  expect(calls('abnormalOverview')).toBe(overview); expect(calls('watchlistList')).toBe(watchlist)
  expect(write).not.toHaveBeenCalled()
  await market(0); await tick()
  expect(active()).toBe(cn); expect(checkbox.checked).toBe(true)
  expect(calls('abnormalOverview')).toBeGreaterThan(overview)
  expect(calls('watchlistList')).toBeGreaterThan(watchlist)
})
