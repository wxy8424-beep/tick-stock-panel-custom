// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Watchlist } from './Watchlist'
import { WatchlistPreview } from '@/custom/damon/watchlist-preview/Presentation'
import { loadWatchlistPreview } from '../../tests/fixtures/watchlist_preview'
import { validateWatchlistPreview, type WatchlistPreviewData } from '@/custom/damon/watchlist-preview/contract'

const state = vi.hoisted(() => ({ queries: [] as unknown[][], mutate: vi.fn() }))
vi.mock('@tanstack/react-query', async original => ({ ...await original<typeof import('@tanstack/react-query')>(),
  useQueryClient: () => ({ invalidateQueries: vi.fn(), setQueryData: vi.fn() }),
  useMutation: () => ({ mutate: state.mutate, mutateAsync: state.mutate, isPending: false }),
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    state.queries.push(queryKey)
    return { data: queryKey[0] === 'watchlist' ? { symbols: [] } : queryKey[0] === 'watchlist-groups' ? { groups: [] } : undefined,
      isLoading: false, isSuccess: true, refetch: vi.fn() }
  },
}))
vi.mock('@/lib/useSharedQueries', () => ({ useCapabilities: () => ({ data: { capabilities: {} } }), useQuoteStatus: () => ({ data: {} }), usePreferences: () => ({ data: {} }) }))
vi.mock('@/lib/watchlist-columns', async original => {
  const actual = await original<typeof import('@/lib/watchlist-columns')>()
  return { ...actual, loadColumnConfig: async () => actual.BUILTIN_COLUMNS }
})
vi.mock('@/components/StockPreviewDialog', () => ({ StockPreviewDialog: () => null }))
vi.mock('@/components/DimensionMembersDialog', () => ({ DimensionMembersDialog: () => null, dimensionKindForSourceField: () => null }))
vi.mock('@/extensions/ExtensionSlot', () => ({ ExtensionSlot: () => null }))

let host: HTMLDivElement
let root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  localStorage.clear(); state.queries = []; state.mutate.mockClear()
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.useRealTimers(); vi.restoreAllMocks() })
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
