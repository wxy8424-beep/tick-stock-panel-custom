// @vitest-environment jsdom
import { act, StrictMode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { BUILTIN_COLUMNS } from '@/lib/watchlist-columns'
import { api } from '@/lib/api'
import { watchlistGroupsQueryFn, watchlistQueryFn } from '@/lib/watchlist-query-options'
import { Watchlist } from './Watchlist'
import { WatchlistPreview } from '@/custom/damon/watchlist-preview/Presentation'
import { loadWatchlistPreview } from '../../tests/fixtures/watchlist_preview'
import { validateWatchlistPreview, type WatchlistPreviewData } from '@/custom/damon/watchlist-preview/contract'

const state = vi.hoisted(() => ({ real: false, queries: [] as unknown[][], mutate: vi.fn(), apiCall: vi.fn(), visible: [0], refresh: undefined as undefined | (() => unknown) }))
vi.mock('@tanstack/react-query', async original => {
 const actual = await original<typeof import('@tanstack/react-query')>()
 return { ...actual,
  useQueryClient: () => state.real ? actual.useQueryClient() : { invalidateQueries: vi.fn(), setQueryData: vi.fn() },
  useMutation: (options: Parameters<typeof actual.useMutation>[0]) => state.real ? actual.useMutation(options) : { mutate: state.mutate, mutateAsync: state.mutate, isPending: false },
  useQuery: (options: Parameters<typeof actual.useQuery>[0]) => {
    if (state.real) return actual.useQuery(options)
    const { queryKey } = options; state.queries.push([...queryKey])
    return { data: queryKey[0] === 'watchlist' ? { symbols: [] } : queryKey[0] === 'watchlist-groups' ? { groups: [] } : undefined,
      isLoading: false, isSuccess: true, refetch: vi.fn() }
  },
 }
})

const cnRows = Array.from({ length: 120 }, (_, i) => ({ symbol: `${600000 + i}.SH`, name: `A20标的${i}`, asset_type: 'stock', close: 10, change_pct: .01, group_ids: ['g1'] }))
const columns = BUILTIN_COLUMNS.map(c => ({ ...c, visible: c.visible || c.id === 'builtin:intraday' || c.id === 'builtin:candle' }))
function answer(name: string) {
  if (name === 'watchlistColumns') return { columns }
  if (name === 'watchlistList') return { symbols: cnRows.map(r => ({ symbol: r.symbol, group_ids: ['g1'] })) }
  if (name === 'watchlistGroups') return { groups: [{ id: 'g1', name: 'A20分组', color: 'blue' }] }
  if (name === 'watchlistEnriched') return { rows: cnRows, as_of: '2026-09-16' }
  if (name === 'instrumentSearch') return { results: [{ symbol: '601999.SH', name: 'A20搜索样本', asset_type: 'stock' }] }
  if (name === 'klineDailyBatch' || name === 'klineMinuteBatch') return { data: {} }
  return {}
}
const calls = (name: string) => state.apiCall.mock.calls.filter(c => c[0] === name).length
async function tick(ms = 30) { await act(async () => { await vi.advanceTimersByTimeAsync(ms) }) }
function SharedProbe() { useQuery({ queryKey: ['a20-shared'], queryFn: () => state.apiCall('shared', []), refetchInterval: 1000 }); return null }
function HostWatchlistObservers({ enabled, children }: { enabled: boolean; children: React.ReactNode }) {
  useLocation() // Layout rerenders on market URL changes and updates its queryFn options too.
  useQuery({ queryKey: ['watchlist'], queryFn: context => watchlistQueryFn(context), enabled, staleTime: 60_000 })
  useQuery({ queryKey: ['watchlist-groups'], queryFn: context => watchlistGroupsQueryFn(context), enabled, staleTime: 60_000 })
  return children
}
async function renderTiming(strict = false, host: 'none' | 'disabled' | 'active' = 'none') {
  vi.useFakeTimers(); state.real = true
  timingClient = new QueryClient()
  const page = host === 'none' ? <Watchlist /> : <HostWatchlistObservers enabled={host === 'active'}><Watchlist /></HostWatchlistObservers>
  const children = <QueryClientProvider client={timingClient}>{page}<SharedProbe /></QueryClientProvider>
  await render('/watchlist?group=g1', strict ? <StrictMode>{children}</StrictMode> : children)
  await tick(100)
}
async function cnSearch(value: string) {
  const input = active().querySelector<HTMLInputElement>('[placeholder="搜索…"]')!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })) })
  await tick()
}
it.each([1, 2])('inactive market %s stops minute polling, invalidation and explicit refresh, retaining CN state', async target => {
  state.apiCall.mockImplementation(async name => answer(name))
  await renderTiming(); const cn = active()
  await click('[data-watchlist-market="CN"] [title="筛选"]')
  await cnSearch('A20'); const initial = calls('klineMinuteBatch')
  expect(initial).toBeGreaterThan(0)
  await tick(31_000); expect(calls('klineMinuteBatch')).toBeGreaterThan(initial)
  await market(target); await tick()
  const counts = ['watchlistList', 'watchlistGroups', 'watchlistEnriched', 'klineDailyBatch', 'klineMinuteBatch', 'instrumentSearch'].map(calls)
  const shared = calls('shared'), refresh = state.refresh!
  await act(async () => { await timingClient!.invalidateQueries(); cn.querySelector<HTMLButtonElement>('[title="刷新"]')!.click(); refresh() })
  await tick(90_000)
  expect(['watchlistList', 'watchlistGroups', 'watchlistEnriched', 'klineDailyBatch', 'klineMinuteBatch', 'instrumentSearch'].map(calls)).toEqual(counts)
  expect(calls('shared')).toBeGreaterThan(shared)
  await market(0); await tick()
  expect(active()).toBe(cn)
  expect(cn.querySelector<HTMLInputElement>('[placeholder="搜索…"]')?.value).toBe('A20')
  expect(cn.querySelector('[title="筛选"]')?.className).toContain('bg-accent')
  expect(cn.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain('A20分组')
  expect(calls('klineMinuteBatch')).toBeGreaterThan(counts[4])
})
it.each([1, 2])('delayed columns cannot write while hidden in %s; reactivation performs a fresh authorized load', async target => {
  let resolve!: (v: unknown) => void
  const pending = new Promise(r => { resolve = r })
  let requests = 0
  state.apiCall.mockImplementation(name => name === 'watchlistColumns' && requests++ === 0 ? pending : Promise.resolve(answer(name)))
  const write = vi.spyOn(Storage.prototype, 'setItem')
  await renderTiming(); await market(target)
  await act(async () => resolve({ columns })); await tick()
  expect(write.mock.calls.filter(c => c[0] === 'watchlist_columns')).toHaveLength(0)
  await market(0); await tick()
  expect(write.mock.calls.filter(c => c[0] === 'watchlist_columns')).toHaveLength(1)
  expect(calls('klineMinuteBatch')).toBeGreaterThan(0)
})
it('an obsolete load cannot regain write permission after hide and reactivation; StrictMode remains usable', async () => {
  let resolve!: (v: unknown) => void
  const pending = new Promise(r => { resolve = r }); let requests = 0
  state.apiCall.mockImplementation(name => name === 'watchlistColumns' && requests++ === 0 ? pending : Promise.resolve(answer(name)))
  const write = vi.spyOn(Storage.prototype, 'setItem')
  await renderTiming(true); await market(1); await market(0); await tick()
  const writes = write.mock.calls.filter(c => c[0] === 'watchlist_columns').length
  expect(writes).toBeGreaterThan(0)
  await act(async () => resolve({ columns: columns.map(c => ({ ...c, visible: false })) })); await tick()
  expect(write.mock.calls.filter(c => c[0] === 'watchlist_columns')).toHaveLength(writes)
  expect(active().querySelector('[title="隐藏分时图"]')).not.toBeNull()
})
it('late list populates shared cache without starting hidden dependent queries', async () => {
  let resolve!: (v: unknown) => void
  const pending = new Promise(r => { resolve = r })
  state.apiCall.mockImplementation(name => name === 'watchlistList' ? pending : Promise.resolve(answer(name)))
  await renderTiming(); await market(2)
  await act(async () => resolve(answer('watchlistList'))); await tick()
  expect(timingClient!.getQueryData(['watchlist'])).toEqual(answer('watchlistList'))
  expect(calls('watchlistEnriched')).toBe(0)
  await market(0); await tick(); expect(calls('watchlistEnriched')).toBeGreaterThan(0)
})
it('hiding cancels a pending 300ms viewport refresh, then active CN viewport refresh resumes', async () => {
  state.apiCall.mockImplementation(async name => answer(name))
  localStorage.setItem('watchlist_view', JSON.stringify('card'))
  await renderTiming()
  expect(active().querySelector('tbody')).toBeNull()
  const key = timingClient!.getQueryCache().getAll().find(q => q.queryKey[0] === 'watchlist-enriched')!.queryKey
  state.visible = [1]
  await act(async () => { timingClient!.setQueryData(key, { rows: cnRows.map((r, i) => i === 0 ? { ...r, close: 11 } : r), as_of: '2026-09-16' }) }); await tick(20)
  const invalidate = vi.spyOn(timingClient!, 'invalidateQueries')
  await market(1); await tick(400)
  expect(invalidate).not.toHaveBeenCalled()
  await market(0); await tick(30); await tick(400)
  expect(invalidate.mock.calls.some(c => c[0]?.queryKey?.[0] === 'minute-batch')).toBe(true)
  invalidate.mockClear()
  state.visible = [2]
  await act(async () => { timingClient!.setQueryData(key, { rows: cnRows.map((r, i) => i === 0 ? { ...r, close: 12 } : r), as_of: '2026-09-16' }) }); await tick(30); await tick(400)
  expect(invalidate.mock.calls.some(c => c[0]?.queryKey?.[0] === 'minute-batch')).toBe(true)
})
it.each(['table', 'card'])('search and %s group portals are removed while CN is hidden without losing search', async mode => {
  state.apiCall.mockImplementation(async name => answer(name))
  localStorage.setItem('watchlist_view', JSON.stringify(mode))
  await renderTiming(); await cnSearch('A20')
  const menu = active().querySelector<HTMLButtonElement>('[title="展开分组, 选择要加入的自选分组"]')!
  await act(async () => menu.click()); await tick()
  expect(document.body.querySelector('[data-watchlist-group-menu]')).not.toBeNull()
  await market(1); await tick()
  expect(document.body.querySelector('[data-watchlist-group-menu]')).toBeNull()
  const count = calls('instrumentSearch')
  await act(async () => { await timingClient!.invalidateQueries({ queryKey: ['instrument-search'] }) }); await tick()
  expect(calls('instrumentSearch')).toBe(count)
  await market(0); await tick()
  expect(active().querySelector<HTMLInputElement>('[placeholder="搜索…"]')?.value).toBe('A20')
  const picker = active().querySelector<HTMLButtonElement>('[aria-label="600000.SH 的分组"]')!
  await act(async () => picker.click()); await tick()
  expect(document.body.querySelector('[role="menu"]')).not.toBeNull()
  await market(2); await tick()
  expect(document.body.querySelector('[role="menu"]')).toBeNull()
})
it('a previous active round cannot persist after a newer round has loaded columns', async () => {
  let resolve!: (v: unknown) => void
  const pending = new Promise(r => { resolve = r }); let requests = 0
  state.apiCall.mockImplementation(name => name === 'watchlistColumns' && requests++ === 0 ? pending : Promise.resolve(answer(name)))
  const write = vi.spyOn(Storage.prototype, 'setItem')
  await renderTiming(); await market(1); await market(0); await tick()
  expect(write.mock.calls.filter(c => c[0] === 'watchlist_columns')).toHaveLength(1)
  await act(async () => resolve({ columns: columns.map(c => ({ ...c, visible: false })) })); await tick()
  expect(write.mock.calls.filter(c => c[0] === 'watchlist_columns')).toHaveLength(1)
  expect(active().querySelector('[title="隐藏分时图"]')).not.toBeNull()
})
it('unmount revokes the pending column loader write permission', async () => {
  let resolve!: (v: unknown) => void
  const pending = new Promise(r => { resolve = r })
  state.apiCall.mockImplementation(name => name === 'watchlistColumns' ? pending : Promise.resolve(answer(name)))
  const write = vi.spyOn(Storage.prototype, 'setItem')
  await renderTiming(); await act(async () => root.render(null))
  await act(async () => resolve({ columns })); await tick()
  expect(write.mock.calls.filter(c => c[0] === 'watchlist_columns')).toHaveLength(0)
})
it('a hidden observer stops scheduled retries while an independent consumer of the same key still works', async () => {
  state.apiCall.mockImplementation(name => name === 'watchlistList' ? Promise.reject(new Error('A20 synthetic failure')) : Promise.resolve(answer(name)))
  await renderTiming(); expect(calls('watchlistList')).toBe(1)
  await market(1); await tick(5000); expect(calls('watchlistList')).toBe(1)
  const { QueryObserver } = await import('@tanstack/react-query')
  const observer = new QueryObserver(timingClient!, { queryKey: ['watchlist'], queryFn: async () => { state.apiCall('same-key-shared', []); return answer('watchlistList') }, refetchInterval: 1000 })
  const unsubscribe = observer.subscribe(() => {})
  try { await tick(2100); expect(calls('same-key-shared')).toBeGreaterThan(1); expect(calls('watchlistList')).toBe(1) } finally { unsubscribe() }
})
it.each([
  ['watchlistList', 'watchlist', 1], ['watchlistList', 'watchlist', 2],
  ['watchlistGroups', 'watchlist-groups', 1], ['watchlistGroups', 'watchlist-groups', 2],
] as const)('queued %s (%s) retry cannot use a disabled host observer after switching to market %s', async (name, key, target) => {
  state.apiCall.mockImplementation(n => n === name ? Promise.reject(new Error('A22 queued failure')) : Promise.resolve(answer(n)))
  await renderTiming(false, 'disabled')
  expect(calls(name)).toBe(1)
  expect(timingClient!.getQueryCache().find({ queryKey: [key], exact: true })!.getObserversCount()).toBe(2)
  await market(target); await tick(8000)
  expect(calls(name)).toBe(1)
  const query = timingClient!.getQueryCache().find({ queryKey: [key], exact: true })!
  expect(query.getObserversCount()).toBe(1)
  expect(query.state.fetchStatus).toBe('idle')
  state.apiCall.mockImplementation(async n => answer(n))
  await market(0); await tick()
  expect(calls(name)).toBe(2)
  expect(query.state.status).toBe('success')
  expect(active().querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain('A20分组')
})
it.each(['watchlistList', 'watchlistGroups'])('an active shared consumer retains default retries and successful %s data after CN hides', async name => {
  let attempts = 0
  state.apiCall.mockImplementation(n => n === name && ++attempts < 4 ? Promise.reject(new Error('A22 shared retry')) : Promise.resolve(answer(n)))
  await renderTiming(false, 'active'); expect(calls(name)).toBe(1)
  await market(1); await tick(7100)
  expect(calls(name)).toBe(4) // Original browser defaults: initial attempt plus three retries.
  const key = name === 'watchlistList' ? 'watchlist' : 'watchlist-groups'
  expect(timingClient!.getQueryData([key])).toEqual(answer(name))
  await market(0); await tick()
  // CN list keeps its 30s staleTime; CN groups intentionally refresh on return (staleTime 0).
  expect(calls(name)).toBe(name === 'watchlistList' ? 4 : 5)
})
it('rapid hide/show keeps a queued retry usable when CN is active at the attempt boundary', async () => {
  let attempts = 0
  state.apiCall.mockImplementation(n => n === 'watchlistList' && ++attempts === 1 ? Promise.reject(new Error('A22 first attempt')) : Promise.resolve(answer(n)))
  await renderTiming(false, 'disabled')
  await cnSearch('A20'); await click('[data-watchlist-market="CN"] [title="筛选"]')
  await market(1); await tick(100); await market(2); await tick(100); await market(0); await tick(1200)
  expect(calls('watchlistList')).toBe(2)
  expect(timingClient!.getQueryData(['watchlist'])).toEqual(answer('watchlistList'))
  expect(active().querySelector<HTMLInputElement>('[placeholder="搜索…"]')?.value).toBe('A20')
  expect(active().querySelector('[title="筛选"]')?.className).toContain('bg-accent')
})
it('ending an unneeded retry restores cached CN data and permits a fresh active refetch', async () => {
  let fail = false
  state.apiCall.mockImplementation(n => n === 'watchlistList' && fail ? Promise.reject(new Error('A22 failed refetch')) : Promise.resolve(answer(n)))
  await renderTiming(false, 'disabled')
  const cached = timingClient!.getQueryData(['watchlist'])
  expect(cached).toEqual(answer('watchlistList'))
  fail = true
  await act(async () => { void timingClient!.invalidateQueries({ queryKey: ['watchlist'], exact: true }) })
  await tick(50); expect(calls('watchlistList')).toBe(2)
  await market(1); await tick(8000)
  const query = timingClient!.getQueryCache().find({ queryKey: ['watchlist'], exact: true })!
  expect(calls('watchlistList')).toBe(2)
  expect(query.state.data).toBe(cached)
  expect(query.state.status).toBe('success')
  expect(query.state.fetchStatus).toBe('idle')
  expect(query.state.error).toBeNull()
  fail = false; await market(0); await tick()
  expect(calls('watchlistList')).toBe(3)
  expect(query.state.data).toEqual(answer('watchlistList'))
})
it.each(['resolve', 'reject'] as const)('a retry already in flight may %s after hide; no later hidden attempt starts', async outcome => {
  let settle!: (value: unknown) => void, reject!: (error: Error) => void, attempts = 0
  const pending = new Promise((yes, no) => { settle = yes; reject = no })
  state.apiCall.mockImplementation(n => n === 'watchlistList'
    ? ++attempts === 1 ? Promise.reject(new Error('A22 initial failure')) : pending
    : Promise.resolve(answer(n)))
  await renderTiming(false, 'disabled'); await tick(1100)
  expect(calls('watchlistList')).toBe(2)
  await market(2)
  const query = timingClient!.getQueryCache().find({ queryKey: ['watchlist'], exact: true })!
  expect(query.state.fetchStatus).toBe('fetching')
  await act(async () => {
    if (outcome === 'resolve') settle(answer('watchlistList'))
    else reject(new Error('A22 late failed response'))
  })
  await tick(8000)
  expect(calls('watchlistList')).toBe(2)
  expect(query.state.fetchStatus).toBe('idle')
  if (outcome === 'resolve') expect(query.state.data).toEqual(answer('watchlistList'))
})
vi.mock('@/lib/useSharedQueries', () => ({ useCapabilities: () => ({ data: { capabilities: state.real ? { 'kline.minute.batch': true } : {} } }), useQuoteStatus: () => ({ data: { running: state.real, is_trading_hours: true } }), usePreferences: () => ({ data: { minute_intraday_refresh: state.real, minute_intraday_refresh_interval: 6 } }) }))
vi.mock('@/lib/watchlist-columns', async original => {
  const actual = await original<typeof import('@/lib/watchlist-columns')>()
  return { ...actual, loadColumnConfig: (canPersist?: () => boolean) => state.real ? actual.loadColumnConfig(canPersist) : Promise.resolve(actual.BUILTIN_COLUMNS) }
})
vi.mock('@/components/StockPreviewDialog', () => ({ StockPreviewDialog: () => null }))
vi.mock('@/components/DimensionMembersDialog', () => ({ DimensionMembersDialog: () => null, dimensionKindForSourceField: () => null }))
vi.mock('@/extensions/ExtensionSlot', () => ({ ExtensionSlot: ({ context }: { context: { refresh: () => unknown } }) => { state.refresh = context.refresh; return null } }))
vi.mock('@tanstack/react-virtual', () => ({ useVirtualizer: () => ({ getVirtualItems: () => state.visible.map(index => ({ index, key: index, start: index * 200, size: 200, end: (index + 1) * 200 })), getTotalSize: () => 10000 }) }))
vi.mock('@/components/stock-table/MiniCandlestick', () => ({ MiniCandlestick: () => null }))
vi.mock('@/components/stock-table/MiniIntraday', () => ({ MiniIntraday: () => null }))

let host: HTMLDivElement
let root: Root
let timingClient: QueryClient | undefined
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  localStorage.clear(); state.real = false; state.visible = [0]; state.refresh = undefined; state.queries = []; vi.clearAllMocks(); state.apiCall.mockReset()
  for (const name of Object.keys(api)) vi.spyOn(api, name as keyof typeof api).mockImplementation(((...args: unknown[]) => state.apiCall(name, args)) as never)
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); timingClient?.clear(); timingClient = undefined; host.remove(); vi.unstubAllGlobals(); vi.useRealTimers(); vi.restoreAllMocks() })
async function render(path = '/watchlist', element = <Watchlist />) {
  function Navigation() {
    const location = useLocation(), navigate = useNavigate()
    return <><output data-location>{location.pathname}{location.search}</output><button data-back onClick={() => navigate(-1)}>返回</button></>
  }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Navigation /></MemoryRouter>))
}
function active() { return host.querySelector<HTMLElement>('[data-watchlist-market]:not([hidden])')! }
async function market(index: number) {
  await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[index].click())
}
async function click(selector: string) { await act(async () => host.querySelector<HTMLButtonElement>(selector)!.click()) }
async function search(value: string) {
  const input = active().querySelector<HTMLInputElement>('[aria-label="搜索演示自选"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

it('CN retains its original query, filter and view controls through market switches', async () => {
  await render('/watchlist?group=all&keep=1')
  const cn = active()
  expect(cn.querySelector('h1')?.textContent).toBe('自选')
  expect(state.queries).toContainEqual(['watchlist'])
  expect(cn.querySelector('[title="筛选"]')).not.toBeNull()
  await click('[data-watchlist-market="CN"] [title="筛选"]')
  expect(cn.textContent).toContain('板块')
  const originalFilter = cn.querySelector('[title="筛选"]')
  await market(1); await market(2); await market(0)
  expect(active()).toBe(cn)
  expect(cn.querySelector('[title="筛选"]')).toBe(originalFilter)
  expect(cn.textContent).toContain('板块')
  expect(cn.textContent).not.toContain('演示数据｜非生产行情')
  expect(host.querySelector('[data-location]')?.textContent).toContain('group=all')
})

it.each(['HK', 'US'] as const)('direct %s preview uses fixture without queries, fetch, mutation or persistence', async m => {
  const fetch = vi.fn(() => { throw new Error('Preview network prohibited') })
  const write = vi.spyOn(Storage.prototype, 'setItem')
  vi.stubGlobal('fetch', fetch)
  await render(`/watchlist?market=${m}`)
  for (const text of ['演示数据｜非生产行情｜不构成投资信号', '2026-09-16', 'synthetic-fixture', 'PREVIEW', '已自选（演示）']) expect(active().textContent).toContain(text)
  expect(state.queries).toHaveLength(0); expect(state.mutate).not.toHaveBeenCalled()
  expect(fetch).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled()
  expect(host.querySelector('[data-watchlist-market="CN"]')).toBeNull()
  expect(active().textContent).toContain(m === 'HK' ? '0700.HK' : 'AAPL.US')
  expect(active().textContent).not.toContain(m === 'HK' ? 'AAPL.US' : '0700.HK')
})

it('shows all required HK/US samples with independent table/card mode and search state', async () => {
  await render('/watchlist?market=HK&keep=fixture')
  for (const symbol of ['0700.HK', '9988.HK', '3690.HK']) expect(active().textContent).toContain(symbol)
  await search('腾讯')
  expect(active().textContent).toContain('0700.HK'); expect(active().textContent).not.toContain('9988.HK')
  await click('[data-watchlist-market="HK"] [aria-label="卡片视图"]')
  expect(active().querySelector('article')).not.toBeNull()
  await market(2)
  for (const symbol of ['AAPL.US', 'NVDA.US', 'MSFT.US']) expect(active().textContent).toContain(symbol)
  expect(active().querySelector('table')).not.toBeNull()
  await market(1)
  expect(active().querySelector('article')).not.toBeNull()
  expect(active().querySelector<HTMLInputElement>('input')?.value).toBe('腾讯')
  expect(active().textContent).not.toContain('AAPL.US')
  expect(host.querySelector('[data-location]')?.textContent).toContain('keep=fixture')
})

it('reuses table sort with nulls last and no cross-market ranking', async () => {
  await render('/watchlist?market=US')
  const header = [...active().querySelectorAll('th')].find(th => th.textContent?.startsWith('涨跌幅'))!
  await act(async () => header.click())
  let rows = [...active().querySelectorAll('tbody tr')]
  expect(rows[0].textContent).toContain('NVDA.US'); expect(rows[2].textContent).toContain('MSFT.US')
  await act(async () => header.click())
  rows = [...active().querySelectorAll('tbody tr')]
  expect(rows[0].textContent).toContain('AAPL.US'); expect(rows[2].textContent).toContain('MSFT.US')
  expect(active().textContent).toContain('排序：涨跌幅 ↓')
  await market(1)
  expect(active().textContent).toContain('排序：示例原顺序')
  expect(active().textContent).not.toContain('AAPL.US')
})

it('preserves null reasons, source evidence and fraction percentage semantics', async () => {
  await render('/watchlist?market=US')
  const missing = [...active().querySelectorAll('tbody tr')].find(row => row.textContent?.includes('MSFT.US'))!
  expect(missing.querySelector('[data-field="price"]')?.textContent).toContain('—')
  expect(missing.textContent).toContain('演示案例缺少已验证价格')
  expect(missing.textContent).toContain('单位及可比性未证明')
  expect(missing.textContent).toContain('未提供成交额，不补零')
  expect(missing.textContent).toContain('自选状态未知')
  expect(missing.textContent).toContain('2026-09-17T00:00:00Z')
  expect(missing.textContent).toContain('可得时间：—（未证明')
  expect(active().textContent).toContain('+2.50%')
  expect(active().textContent).toContain('fixture:watchlist:US:MSFT.US:v1')
})

it('disabled add/delete cannot mutate the real watchlist', async () => {
  await render('/watchlist?market=HK')
  const buttons = [...active().querySelectorAll<HTMLButtonElement>('button')].filter(button => button.disabled)
  expect(buttons).toHaveLength(4)
  await act(async () => buttons.forEach(button => button.click()))
  expect(state.mutate).not.toHaveBeenCalled(); expect(state.queries).toHaveLength(0)
  expect(active().textContent).toContain('3 只')
})

it('browser back restores market and search empty state stays local', async () => {
  await render('/watchlist?market=HK')
  await search('not-a-fixture-symbol')
  expect(active().textContent).toContain('暂无匹配的演示自选')
  await market(2)
  expect(active().textContent).toContain('AAPL.US')
  await click('[data-back]')
  expect(active().dataset.watchlistMarket).toBe('HK')
  expect(active().textContent).toContain('暂无匹配的演示自选')
})

it.each(['error', 'loading'] as const)('shows %s with nonproduction declaration and no fallback', async kind => {
  await render('/watchlist?market=HK', <WatchlistPreview market="HK" state={{ kind }} />)
  expect(host.textContent).toContain(kind === 'error' ? '自选 Preview 加载失败' : 'Preview 加载中')
  expect(host.textContent).toContain('演示数据｜非生产行情｜不构成投资信号')
  expect(state.queries).toHaveLength(0)
})

it('uses fixed dates, isolated copies and rejects production or mixed fixture data', () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2030-01-06T00:00:00Z'))
  const data = loadWatchlistPreview('HK'), other = loadWatchlistPreview('HK')
  expect(data.trading_date).toBe('2026-09-16'); expect(data).toEqual(other); expect(data.rows[0]).not.toBe(other.rows[0])
  expect(() => validateWatchlistPreview({ ...data, is_production: true } as unknown as WatchlistPreviewData)).toThrow('watchlist_fixture_preview_required')
  expect(() => validateWatchlistPreview({ ...data, rows: loadWatchlistPreview('US').rows })).toThrow('mixed_watchlist_preview')
  expect(() => validateWatchlistPreview({ ...data, rows: [{ ...data.rows[0], price: null, missing_reasons: [] }] })).toThrow('missing_preview_reason')
  expect(() => validateWatchlistPreview({ ...data, rows: [{ ...data.rows[0], price: Infinity }] })).toThrow('nonfinite_preview_value')
})
