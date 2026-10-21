// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, US_SECTION_KEYS } from '@/lib/api'
import { Dashboard } from './Dashboard'

const calls = vi.hoisted(() => ({ cn: vi.fn() }))
vi.mock('@/lib/useSharedQueries', () => ({
  useDataStatus: () => { calls.cn(); return { data: undefined } },
  useCapabilities: () => ({ data: { capabilities: {} } }), useSettings: () => ({ data: {} }), usePreferences: () => ({ data: {} }),
}))
vi.mock('@/components/dashboard/HongKongDashboard', () => ({ HongKongDashboard: ({ onMarketChange }: { onMarketChange: (m: string) => void }) => <button onClick={() => onMarketChange('CN')}>HK return CN</button> }))
vi.mock('@/components/dashboard/DashboardGrid', async original => ({ ...await original<typeof import('@/components/dashboard/DashboardGrid')>(), DashboardGrid: () => <div data-grid /> }))
vi.mock('@/components/AdjFactorSyncGate', () => ({ useAdjFactorSyncGate: () => ({ dialog: null, guard: vi.fn() }) }))
let root: Root, host: HTMLDivElement, client: QueryClient
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); localStorage.clear(); calls.cn.mockClear()
  host = document.createElement('div'); document.body.append(host); root = createRoot(host); client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  for (const name of Object.keys(api)) vi.spyOn(api, name as keyof typeof api).mockResolvedValue({} as never)
  vi.mocked(api.overviewMarket).mockResolvedValue({ emotion: { label: 'CN测试样本', score: 50 }, as_of: '2026-10-08' } as never)
  vi.mocked(api.usDashboard).mockImplementation(async symbol => ({ ...Object.fromEntries(US_SECTION_KEYS.map(k => [k, { status: 'unavailable', mode: 'UNAVAILABLE', data: null, source: 'test', updated_at: null, error: null }])), market: { code: 'US', timezone: 'America/New_York', local_time: '2026-10-08T10:00:00-04:00', session_state: 'regular', calendar_status: 'unknown' }, updated_at: '2026-10-08T14:00:00Z', focus_symbol: symbol ?? null, focus_quote: symbol ? { symbol, market: 'US', close: 102 } : null, sample: { requested: 1, received: 1, coverage: 'synthetic test response' } }) as Awaited<ReturnType<typeof api.usDashboard>>)
})
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove(); vi.restoreAllMocks() })
function Location() { const l = useLocation(), n = useNavigate(); return <><output data-url>{l.search}</output><button data-us onClick={() => n('/?market=US&quote_symbol=AAPL.US')}>US link</button></> }
async function settle() { await act(async () => { await new Promise(r => setTimeout(r, 25)) }) }
async function render(path: string) { await act(async () => root.render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Location /><Dashboard /></MemoryRouter></QueryClientProvider>)); await settle() }
it('keeps default CN queries and mounts US details before CN hooks, then removes quote params on market change', async () => {
  await render('/'); expect(calls.cn).toHaveBeenCalled(); expect(api.overviewMarket).toHaveBeenCalledWith(undefined)
  calls.cn.mockClear(); vi.mocked(api.overviewMarket).mockClear()
  await act(async () => host.querySelector<HTMLButtonElement>('[data-us]')!.click()); await settle()
  expect(calls.cn).not.toHaveBeenCalled(); expect(api.overviewMarket).not.toHaveBeenCalled()
  expect(api.usDashboard).toHaveBeenLastCalledWith('AAPL.US')
  await act(async () => [...host.querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')].find(b => b.textContent === '港股')!.click()); await settle()
  expect(host.querySelector('[data-url]')?.textContent).toBe('?market=HK')
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === 'HK return CN')!.click()); await settle()
  expect(calls.cn).toHaveBeenCalled()
  expect(host.textContent).toContain('CN测试样本')
  expect(api.overviewMarket).not.toHaveBeenCalled() // Original 5s fresh CN cache survives switching.
  await act(async () => { await client.invalidateQueries({ queryKey: ['overview-market'] }) }); await settle()
  expect(api.overviewMarket).toHaveBeenCalledWith(undefined)
})
it.each(['?quote_symbol=AAPL.US', '?market=CN&quote_symbol=AAPL.US', '?market=US&market=CN&quote_symbol=AAPL.US'])('fails closed before all market business hooks for %s', async query => {
  await render('/' + query)
  expect(host.textContent).toContain('报价链接参数错误'); expect(calls.cn).not.toHaveBeenCalled()
  expect(api.usDashboard).not.toHaveBeenCalled(); expect(api.overviewMarket).not.toHaveBeenCalled()
})
it('opens a direct US URL with only the US business request and no extra detail storage writes', async () => {
  const write = vi.spyOn(Storage.prototype, 'setItem')
  await render('/?market=US&quote_symbol=AAPL.US')
  expect(calls.cn).not.toHaveBeenCalled(); expect(api.usDashboard).toHaveBeenCalledTimes(1)
  const used = Object.entries(api).filter(([, fn]) => vi.isMockFunction(fn) && fn.mock.calls.length).map(([name]) => name)
  expect(used).toEqual(['usDashboard'])
  expect(write.mock.calls.map(c => c[0])).toEqual(['tsp.dashboard.us.layout.v1']) // Existing dashboard layout persistence, not a new detail write.
})
