// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
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
function Navigation() {
  const location = useLocation(), navigate = useNavigate()
  return <><output data-url>{location.pathname}{location.search}</output><button data-back onClick={() => navigate(-1)}>history back</button><button data-forward onClick={() => navigate(1)}>history forward</button><button data-switch onClick={() => navigate('/?market=US&quote_symbol=NVDA.US')}>direct NVDA</button></>
}
async function render(path = '/?market=US') {
  await act(async () => { root.render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Navigation /><UnitedStatesDashboard onMarketChange={vi.fn()} /></MemoryRouter></QueryClientProvider>); await new Promise(resolve => setTimeout(resolve, 20)) })
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
it('views and searches the entire returned ranking without extra requests or storage, preserving quote navigation', async () => {
  const data = response()
  data.gainers = { ...data.gainers, data: Array.from({ length: 20 }, (_, i) => ({ symbol: `STOCK${i}.US`, market: 'US', name: `合成榜单${i}`, close: i + 1, change_pct: i / 100 })) }
  mock.get.mockImplementation(symbol => Promise.resolve({ ...data, focus_symbol: symbol ?? null, focus_quote: symbol ? { symbol, close: 42 } : null }))
  await render()
  const writes = vi.spyOn(Storage.prototype, 'setItem')
  const count = mock.get.mock.calls.length
  const opener = host.querySelector<HTMLButtonElement>('[aria-label="查看涨幅榜已返回记录"]')
  expect(opener).not.toBeNull()
  await act(async () => opener!.click()); await settle()
  const panel = host.querySelector<HTMLElement>('[aria-label="美股已返回榜单"]')!
  expect(panel.querySelectorAll('tbody tr')).toHaveLength(20)
  const input = panel.querySelector<HTMLInputElement>('input')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, 'STOCK19')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  expect(panel.querySelectorAll('tbody tr')).toHaveLength(1)
  expect(mock.get).toHaveBeenCalledTimes(count)
  expect(writes).not.toHaveBeenCalled()
  await act(async () => panel.querySelector<HTMLAnchorElement>('tbody a')!.click()); await settle()
  expect(mock.get).toHaveBeenLastCalledWith('STOCK19.US')
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('STOCK19.US')
  expect([...host.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].filter(b => ['上一只', '下一只'].includes(b.textContent!)).every(b => b.disabled)).toBe(true)
  await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="关闭快照"]')!.click()); await settle()
  expect(panel.querySelector('input')?.value).toBe('STOCK19')
  await act(async () => panel.querySelector<HTMLButtonElement>('[aria-label="关闭已返回榜单"]')!.click()); await settle()
  expect(host.querySelector('[aria-label="美股已返回榜单"]')).toBeNull()
  expect(document.activeElement).toBe(opener)
  writes.mockRestore()
})
it('uses backend post-market state and keeps the existing snapshot-only contract', async () => {
  const data = response()
  data.market = { ...data.market, session_state: 'post_market', calendar_status: 'covered' }
  mock.get.mockResolvedValue(data)
  await render()
  expect(host.textContent).toContain('盘后')
  expect(host.textContent).toContain('未启用盘前/盘后行情')
  expect(host.textContent).not.toContain('交易中（时钟窗口）')
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
  const button = [...host.querySelectorAll<HTMLAnchorElement>('[data-us-slot="gainers"] a')].find(node => node.textContent?.includes('NVDA.US'))!
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

async function settle() { await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)) }) }
async function enterCode(value: string) {
  const input = host.querySelector<HTMLInputElement>('input[aria-label="美股证券代码"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
async function submitCode() {
  await act(async () => host.querySelector<HTMLFormElement>('form[aria-label="美股代码查询"]')!.requestSubmit())
  await settle()
}
it.each(['AAPL', ' aapl.us ', ' aapl ', 'BRK.B', 'BRK-B.US'])('opens normalized code %s without list navigation or new persistence', async value => {
  await render('/?market=US&keep=yes')
  const writes = vi.spyOn(Storage.prototype, 'setItem')
  const before = mock.get.mock.calls.length
  await enterCode(value)
  expect(mock.get).toHaveBeenCalledTimes(before)
  await submitCode()
  const symbol = value.trim().toUpperCase().endsWith('.US') ? value.trim().toUpperCase() : value.trim().toUpperCase() + '.US'
  expect(mock.get).toHaveBeenLastCalledWith(symbol)
  expect(host.querySelector('[data-url]')?.textContent).toBe('/?market=US&keep=yes&quote_symbol=' + symbol)
  expect([...host.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].filter(b => ['上一只', '下一只'].includes(b.textContent!)).every(b => b.disabled)).toBe(true)
  expect(writes).not.toHaveBeenCalled()
  await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="关闭快照"]')!.click()); await settle()
  expect(host.querySelector('[data-url]')?.textContent).toBe('/?market=US&keep=yes')
  expect(document.activeElement).toBe(host.querySelector('button[type="submit"]'))
  writes.mockRestore()
})
it.each(['', '   ', '700.HK', '600000.SH', '000001.SZ', '430047.BJ', 'https://example.com/AAPL', 'AAPL,NVDA', 'AAPL NVDA', '苹果', '.SPX.US', 'AAPL/US'])('rejects %s locally without navigation or requests', async value => {
  await render()
  const before = mock.get.mock.calls.length
  await enterCode(value); await submitCode()
  const input = host.querySelector<HTMLInputElement>('input[aria-label="美股证券代码"]')!
  expect(input.getAttribute('aria-invalid')).toBe('true')
  expect(document.getElementById(input.getAttribute('aria-describedby')!.split(' ').at(-1)!)?.textContent).toContain('请输入单个美股证券代码')
  expect(mock.get).toHaveBeenCalledTimes(before)
  expect(host.querySelector('[data-url]')?.textContent).toBe('/?market=US')
  expect(host.querySelector('[role="dialog"]')).toBeNull()
})
it('keeps history stable on duplicate submit and restores the query with back/forward', async () => {
  await render('/?market=US&keep=yes')
  await enterCode('AAPL'); await submitCode()
  const count = mock.get.mock.calls.length
  await submitCode()
  expect(mock.get).toHaveBeenCalledTimes(count)
  await act(async () => host.querySelector<HTMLButtonElement>('[data-back]')!.click()); await settle()
  expect(host.querySelector('[role="dialog"]')).toBeNull()
  await act(async () => host.querySelector<HTMLButtonElement>('[data-forward]')!.click()); await settle()
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('AAPL.US')
})
it('clears local validation on input and leaves absent quotes unavailable rather than falling back', async () => {
  await render(); await enterCode('700.HK'); await submitCode()
  await enterCode('ZZZZ')
  expect(host.querySelector('input[aria-invalid="true"]')).toBeNull()
  mock.get.mockImplementation(symbol => Promise.resolve({ ...response(symbol), focus_quote: null }))
  await submitCode()
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('未返回该证券报价')
  expect(mock.get).toHaveBeenLastCalledWith('ZZZZ.US')
})
it('restores a direct quote URL and closes it in place; no fallback request', async () => {
  await render('/?market=US&quote_symbol=AAPL.US&keep=yes')
  expect(mock.get).toHaveBeenCalledTimes(1); expect(mock.get).toHaveBeenLastCalledWith('AAPL.US')
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('官方名称')
  await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="关闭快照"]')!.click()); await settle()
  expect(host.querySelector('[role="dialog"]')).toBeNull()
  expect(host.querySelector('[data-url]')?.textContent).toBe('/?market=US&keep=yes')
})
it.each(['', 'AAPL', '700.HK', '.SPX.US', 'AAPL.US&quote_symbol=NVDA.US'])('fails closed for invalid quote URL %s', async symbol => {
  await render('/?market=US&quote_symbol=' + symbol)
  expect(host.textContent).toContain('参数错误'); expect(mock.get).not.toHaveBeenCalled()
})
it('preserves native link behavior and browser back/forward without changing saved US layout', async () => {
  await render()
  const saved = localStorage.getItem(US_LAYOUT_KEY)
  const link = host.querySelector<HTMLAnchorElement>('[data-us-slot="gainers"] a')!
  expect(link.href).toContain('quote_symbol=AAPL.US')
  await act(async () => link.click()); await settle()
  expect(host.querySelector('[data-url]')?.textContent).toContain('quote_symbol=AAPL.US')
  await act(async () => host.querySelector<HTMLButtonElement>('[data-back]')!.click()); await settle()
  expect(host.querySelector('[role="dialog"]')).toBeNull()
  await act(async () => host.querySelector<HTMLButtonElement>('[data-forward]')!.click()); await settle()
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('AAPL.US')
  expect(localStorage.getItem(US_LAYOUT_KEY)).toBe(saved)
})
it('late AAPL completion cannot overwrite NVDA after a rapid URL switch', async () => {
  let resolve!: (value: USDashboardResponse) => void
  mock.get.mockImplementation(symbol => symbol === 'AAPL.US' ? new Promise(yes => { resolve = yes }) : Promise.resolve({ ...response(symbol), focus_quote_metadata: { symbol: symbol!, status: 'available', source: 'NVDA matching source', source_reason: null, acquired_at: '2026-10-08T14:01:00Z', acquired_at_reason: null, reason: null } }))
  await render('/?market=US&quote_symbol=AAPL.US')
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('正在获取')
  await act(async () => host.querySelector<HTMLButtonElement>('[data-switch]')!.click()); await settle()
  await act(async () => resolve({ ...response('AAPL.US'), focus_quote: { symbol: 'AAPL.US', close: 777 }, focus_quote_metadata: { symbol: 'AAPL.US', status: 'available', source: 'AAPL obsolete source', source_reason: null, acquired_at: '2020-01-01T00:00:00Z', acquired_at_reason: null, reason: null } })); await settle()
  const dialog = host.querySelector('[role="dialog"]')!
  expect(dialog.textContent).toContain('NVDA.US'); expect(dialog.textContent).not.toContain('777')
  expect(dialog.textContent).toContain('NVDA matching source'); expect(dialog.textContent).not.toContain('AAPL obsolete source')
  expect(client.getQueryData(['us-dashboard', 'AAPL.US'])).toBeDefined()
})
it('retries a failed quote without loading CN APIs and does not infer focus staleness from coverage', async () => {
  mock.get.mockRejectedValueOnce(new Error('synthetic failure')).mockImplementation(symbol => Promise.resolve({ ...response(symbol), sample: { ...response(symbol).sample, stale: true, status: 'stale' } }))
  await render('/?market=US&quote_symbol=AAPL.US')
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('请求失败')
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '重试报价')!.click()); await settle()
  const text = host.querySelector('[role="dialog"]')!.textContent
  expect(text).toContain('102.00'); expect(text).toContain('新鲜度无法判定'); expect(text).not.toContain('报价已过期')
  expect(client.getQueryCache().getAll().every(q => q.queryKey[0] === 'us-dashboard')).toBe(true)
})
it('does not show a differently identified quote even if the response says focus AAPL', async () => {
  mock.get.mockResolvedValue({ ...response(), focus_quote: { symbol: '700.HK', market: 'HK', close: 999 } })
  await render('/?market=US&quote_symbol=AAPL.US')
  expect(host.querySelector('[role="dialog"]')?.textContent).not.toContain('999')
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('未返回该证券报价')
})
it('keeps the source list mounted while a new quote loads without displaying placeholder quote data', async () => {
  await render()
  const link = host.querySelector<HTMLAnchorElement>('[data-us-slot="gainers"] a')!
  let resolve!: (value: USDashboardResponse) => void
  mock.get.mockImplementation(() => new Promise(yes => { resolve = yes }))
  await act(async () => link.click()); await settle()
  expect(host.querySelector('[data-us-slot="gainers"] a')).toBe(link)
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('正在获取')
  expect(host.querySelector('[role="dialog"]')?.textContent).not.toContain('102.00')
  await act(async () => resolve(response('AAPL.US'))); await settle()
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('102.00')
})
it('keeps matching cached data on background failure, then recovers through the actual query retry control', async () => {
  await render('/?market=US&quote_symbol=AAPL.US')
  mock.get.mockRejectedValue(new Error('synthetic refetch failure'))
  await act(async () => { await client.refetchQueries({ queryKey: ['us-dashboard', 'AAPL.US'], exact: true }) }); await settle()
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('保留同证券缓存报价')
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('102.00')
  mock.get.mockResolvedValue(response('AAPL.US'))
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '重试报价')!.click()); await settle()
  expect(host.querySelector('[role="dialog"]')?.textContent).not.toContain('保留同证券缓存报价')
})
it('invalid links cannot bypass the guard through the dashboard reload button', async () => {
  await render('/?market=US&quote_symbol=700.HK')
  const reload = [...host.querySelectorAll('button')].find(b => b.textContent === '重载')!
  expect(reload.disabled).toBe(true)
  await act(async () => reload.click()); expect(mock.get).not.toHaveBeenCalled()
})
it.each(['gainers', 'losers', 'turnover', 'monitor', 'activity'] as const)('opens the existing %s entry with its own navigation context', async slot => {
  const data = response()
  data[slot] = { ...data.gainers }
  mock.get.mockResolvedValue(data)
  await render()
  const entry = host.querySelector<HTMLElement>(`[data-us-slot="${slot}"] ${slot === 'monitor' || slot === 'activity' ? 'button' : 'a'}`)!
  await act(async () => entry.click()); await settle()
  expect(host.querySelector('[data-url]')?.textContent).toContain('quote_symbol=AAPL.US')
  expect(host.querySelector('[role="dialog"]')?.textContent).toContain('AAPL.US')
})
