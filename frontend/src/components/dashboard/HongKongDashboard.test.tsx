// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { HongKongDashboard } from './HongKongDashboard'
import { HK_SECTION_KEYS, type HKDashboardResponse, type HKSection } from '@/lib/api'

const mock = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', async importOriginal => ({ ...await importOriginal<typeof import('@/lib/api')>(), api: { hkDashboard: mock.get } }))
let host: HTMLDivElement
let root: Root
let client: QueryClient
const titles = ['每日股票数据', '每日 ETF 数据', '股票资金流向', '早盘抢筹', '尾盘抢筹', '行业资金流向', '概念资金流向', '股票基本面数据', '股票分红配送', '港股异动榜', '股票大宗交易', '异动原因揭秘']
function response(): HKDashboardResponse {
  const sections = Object.fromEntries(HK_SECTION_KEYS.map(key => [key, {
    status: 'unavailable', mode: 'UNAVAILABLE', source: '可靠来源未提供', updated_at: null, data: null, error: '暂无可靠数据源',
  } satisfies HKSection])) as Record<typeof HK_SECTION_KEYS[number], HKSection>
  sections.daily_stocks = { status: 'ok', mode: 'LIVE', source: 'Longbridge quote · 有限候选', updated_at: null, error: null, data: [
    { symbol: '700.HK', last_price: 500, change_pct: .02, timestamp: 1791426600000 },
    { symbol: '9988.HK', last_price: 100, change_pct: .01, timestamp: 1791426600000 },
  ] }
  sections.capital_flow = { status: 'error', mode: 'LIVE', source: 'Longbridge capital_flow', data: null, error: 'quote_permission', updated_at: null }
  return { ...sections, market: { code: 'HK', timezone: 'Asia/Hong_Kong', local_time: '2026-10-08T10:00:00+08:00', session_state: 'regular', calendar_status: 'unknown' }, updated_at: '2026-10-08T02:00:00Z', focus_symbol: '700.HK' }
}
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  mock.get.mockReset().mockResolvedValue(response())
})
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove() })
async function render() {
  await act(async () => { root.render(<QueryClientProvider client={client}><HongKongDashboard onMarketChange={vi.fn()} /></QueryClientProvider>); await new Promise(resolve => setTimeout(resolve, 20)) })
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
}
it('shows all 12 sections, honest unavailable states, and isolates a section error', async () => {
  await render()
  expect(Array.from(host.querySelectorAll('h2')).map(node => node.textContent)).toEqual(titles)
  expect(host.textContent).toContain('UNAVAILABLE')
  expect(host.textContent).toContain('quote_permission')
  expect(host.textContent).toContain('500')
  expect(host.textContent).toContain('非全港股')
})
it('clicking a real table row updates the focus query without sharing CN cache keys', async () => {
  await render()
  const button = Array.from(host.querySelectorAll('tbody button')).find(node => node.textContent?.includes('9988.HK'))!
  await act(async () => { (button as HTMLButtonElement).click(); await new Promise(resolve => setTimeout(resolve, 20)) })
  expect(mock.get).toHaveBeenLastCalledWith('9988.HK')
  expect(host.textContent).toContain('焦点股票 9988.HK')
  expect(client.getQueryCache().getAll().every(query => query.queryKey[0] === 'hk-dashboard')).toBe(true)
})
