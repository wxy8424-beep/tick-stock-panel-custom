// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { UnitedStatesDashboard, US_LAYOUT_KEY, normalizeUSLayout } from './UnitedStatesDashboard'
import { DEFAULT_LAYOUT } from './registry'
import { US_SECTION_KEYS, type USDashboardResponse, type USSection } from '@/lib/api'
import type { DashboardGridProps } from './DashboardGrid'

const mock = vi.hoisted(() => ({ get: vi.fn(), grid: vi.fn() }))
vi.mock('@/lib/api', async importOriginal => ({ ...await importOriginal<typeof import('@/lib/api')>(), api: { usDashboard: mock.get } }))
vi.mock('./DashboardGrid', async importOriginal => ({ ...await importOriginal<typeof import('./DashboardGrid')>(), DashboardGrid: (props: DashboardGridProps) => {
  mock.grid(props)
  return <div>{props.items.map(item => <div key={item.i}>{props.renderItem?.(item)}</div>)}</div>
} }))

function response(symbol = 'AAPL.US'): USDashboardResponse {
  const sections = Object.fromEntries(US_SECTION_KEYS.map(key => [key, { status: 'unavailable', mode: 'UNAVAILABLE', source: '暂无可靠数据源', updated_at: null, error: '暂不可用', data: null } satisfies USSection])) as Record<typeof US_SECTION_KEYS[number], USSection>
  sections.gainers = { status: 'ok', mode: 'DERIVED', source: 'Longbridge quote · 有限样本', updated_at: null, error: null, data: [{ symbol: 'AAPL.US', name: '苹果', close: 102, change_pct: .02 }, { symbol: 'NVDA.US', name: '英伟达', close: 110, change_pct: .1 }] }
  sections.monitor = { status: 'ok', mode: 'LIVE', source: 'Longbridge top_movers', updated_at: null, error: null, data: [{ symbol: 'AAPL.US', name: '苹果', reason: 'Volatility exceeds 20-day avg', labels: ['Media'] }] }
  sections.ladder = { status: 'ok', mode: 'LIVE', source: 'Longbridge option_volume', updated_at: null, error: null, data: { symbol, call_volume: 200, put_volume: 100, put_call_ratio: .5 } }
  return { ...sections, market: { code: 'US', timezone: 'America/New_York', local_time: '2026-10-08T10:00:00-04:00', session_state: 'regular', calendar_status: 'unknown' }, focus_symbol: symbol, focus_quote: { symbol, name: '官方名称', close: 102, currency: 'USD' }, updated_at: '2026-10-08T14:00:00Z', sample: { coverage: '有限样本，非全市场', requested: 6, received: 6 } }
}
let host: HTMLDivElement
let root: Root
let client: QueryClient
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  localStorage.clear()
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  mock.get.mockReset().mockImplementation(symbol => Promise.resolve(response(symbol)))
  mock.grid.mockClear()
})
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove() })
async function render() {
  await act(async () => { root.render(<QueryClientProvider client={client}><UnitedStatesDashboard onMarketChange={vi.fn()} /></QueryClientProvider>); await new Promise(resolve => setTimeout(resolve, 20)) })
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
}
it('keeps CN 13 slot types with spacious US metrics, Chinese labels and independent query/storage', async () => {
  localStorage.setItem('cn-layout-sentinel', 'untouched')
  await render()
  const comfortable = normalizeUSLayout(null)
  expect(mock.grid.mock.lastCall?.[0].items).toEqual(comfortable)
  expect(mock.grid.mock.lastCall?.[0].rowHeight).toBe(48)
  expect(mock.grid.mock.lastCall?.[0].gap).toBe(10)
  expect([...host.querySelectorAll('[data-us-slot]')].map(node => node.getAttribute('data-us-slot'))).toEqual(DEFAULT_LAYOUT.map(item => item.t))
  for (const text of ['美股市场看板', '看涨期权成交量', '看跌期权成交量', '波动率超过20日均值', '媒体', '非全市场', '暂不可用']) expect(host.textContent).toContain(text)
  expect(client.getQueryCache().getAll().every(query => query.queryKey[0] === 'us-dashboard')).toBe(true)
  expect(JSON.parse(localStorage.getItem(US_LAYOUT_KEY)!).items).toEqual(comfortable)
  expect(localStorage.getItem('cn-layout-sentinel')).toBe('untouched')
})

it('expands saved short KPI cards without overlaps or repeatedly shifting the saved layout', () => {
  const expanded = normalizeUSLayout({ v: 1, items: DEFAULT_LAYOUT })
  expect(expanded.find(item => item.t === 'kpi')?.h).toBe(3)
  expect(normalizeUSLayout({ v: 1, items: expanded })).toEqual(expanded)
  for (let i = 0; i < expanded.length; i++) for (const other of expanded.slice(i + 1)) {
    const item = expanded[i]
    expect(item.x < other.x + other.w && other.x < item.x + item.w && item.y < other.y + other.h && other.y < item.y + item.h).toBe(false)
  }
})
it('opens real US row and navigates only its actual list without CN preview queries', async () => {
  await render()
  const button = [...host.querySelectorAll<HTMLDivElement>('[data-us-slot="gainers"] div.cursor-pointer')].find(node => node.textContent?.includes('NVDA.US'))!
  await act(async () => { button.click(); await new Promise(resolve => setTimeout(resolve, 20)) })
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
  expect(mock.get).toHaveBeenLastCalledWith('NVDA.US')
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('NVDA.US')
  const previous = [...host.querySelectorAll('button')].find(node => node.textContent === '上一只')!
  await act(async () => previous.click())
  expect(mock.get).toHaveBeenLastCalledWith('AAPL.US')
})
it('section failure keeps other real modules visible', async () => {
  const data = response()
  data.ladder = { ...data.ladder, status: 'error', error: 'quote_permission', data: null }
  mock.get.mockResolvedValue(data)
  await render()
  expect(host.textContent).toContain('行情权限不足')
  expect(host.textContent).toContain('苹果')
  expect(host.querySelectorAll('[data-us-slot]')).toHaveLength(13)
})

it('shows actual universe coverage, missing batches and snapshot age without claiming exchange completeness', async () => {
  const data = response()
  data.sample = { coverage: 'Longbridge 美股可用证券清单（含ETF等；非全部普通股市场保证）', requested: 16117, received: 15000,
    failed: 1117, failed_batches: 2, rejected_symbols: 0, status: 'partial', scope: 'provider_universe', exchange_complete: false,
    completed_at: '2026-10-08T14:00:00Z' }
  mock.get.mockResolvedValue(data)
  await render()
  for (const label of ['成功 15000/16117', '部分获取', '缺失 1117', '失败批次 2', '逐批快照，非同一瞬间', '覆盖证券涨幅榜']) expect(host.textContent).toContain(label)
  expect(host.textContent).not.toContain('样本涨幅榜')
  expect(host.querySelectorAll('[data-us-slot]')).toHaveLength(13)
})

it('explicitly shows retained stale snapshot after background failure', async () => {
  const data = response()
  data.sample = { ...data.sample, scope: 'provider_universe', status: 'stale', stale: true, error: 'network' }
  mock.get.mockResolvedValue(data)
  await render()
  expect(host.textContent).toContain('保留上轮快照（刷新失败）')
})
