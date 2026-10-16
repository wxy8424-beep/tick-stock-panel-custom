// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Indices } from './Indices'
import { IndexPreview } from '@/custom/damon/index-preview/Presentation'
import { sortIndexPreview, validateIndexPreview, type IndexPreviewData } from '@/custom/damon/index-preview/contract'
import { loadIndexPreview } from '../../tests/fixtures/index_preview'
import { api } from '@/lib/api'

vi.mock('@/lib/api', () => ({ api: {
  indexQuotes: vi.fn(async () => ({ rows: [{ symbol: '000001.SH', last_price: 3000, change_pct: 1 }], count: 1 })),
  indexDaily: vi.fn(async (symbol: string) => ({ symbol, source: 'CN-test-source', rows: [
    { date: '2026-09-15', open: 10, high: 12, low: 9, close: 11, volume: 1 },
    { date: '2026-09-16', open: 11, high: 13, low: 10, close: 12, volume: 1 },
  ] })),
  indexMinute: vi.fn(async () => ({ rows: [] })), syncIndexDaily: vi.fn(async () => ({})),
} }))
vi.mock('@/lib/useSharedQueries', () => ({ useCapabilities: () => ({ data: { capabilities: {} } }) }))
vi.mock('@/components/EChartsCandlestick', () => ({ EChartsCandlestick: ({ symbol, data, onDateClick }: {
  symbol: string; data: { date: string }[]; onDateClick: (date: string) => void
}) => <div data-cn-chart={symbol}>{data.map(row => <button key={row.date} data-day={row.date} onClick={() => onDateClick(row.date)}>{row.date}</button>)}</div> }))
vi.mock('@/components/EChartsIntraday', () => ({ EChartsIntraday: () => <div>原分时图</div> }))

let host: HTMLDivElement
let root: Root
let client: QueryClient
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.clearAllMocks()
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, gcTime: Infinity } } })
})
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove(); vi.useRealTimers(); vi.unstubAllGlobals() })
async function settle() {
  for (let i = 0; i < 4; i++) await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) })
}
async function render(path = '/indices', element?: React.ReactNode) {
  function Navigation() {
    const navigate = useNavigate(), location = useLocation()
    return <><output data-location>{location.pathname}{location.search}</output>
      <button data-back onClick={() => navigate(-1)}>返回</button><button data-forward onClick={() => navigate(1)}>前进</button>
      <button data-other onClick={() => navigate('/other')}>其他页面</button></>
  }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}><QueryClientProvider client={client}>
    {element ?? <Routes><Route path="/indices" element={<Indices />} /><Route path="/other" element={<p>其他页面</p>} /></Routes>}
    <Navigation />
  </QueryClientProvider></MemoryRouter>))
  await settle()
}
function active() { return host.querySelector<HTMLElement>('[data-index-market]:not([hidden])')! }
async function switchMarket(index: number) {
  await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[index].click())
  await settle()
}
async function click(selector: string) { await act(async () => host.querySelector<HTMLButtonElement>(selector)!.click()); await settle() }

it('defaults to unchanged CN production queries, four indexes, sync and symbol selection', async () => {
  await render()
  expect(active().dataset.indexMarket).toBe('CN')
  for (const text of ['上证指数', '深证成指', '创业板指', '科创综指', '同步指数日K', 'CN-test-source']) expect(active().textContent).toContain(text)
  expect(api.indexDaily).toHaveBeenCalledWith('000001.SH', 180, expect.any(Object))
  expect(client.getQueryCache().getAll().some(q => q.queryKey[0] === 'index-daily')).toBe(true)
  const index = [...active().querySelectorAll('button')].find(button => button.textContent?.includes('深证成指'))!
  await act(async () => index.click()); await settle()
  expect(api.indexDaily).toHaveBeenCalledWith('399001.SZ', 180, expect.any(Object))
  const sync = [...active().querySelectorAll('button')].find(button => button.textContent?.includes('同步指数日K'))!
  await act(async () => sync.click()); await settle()
  expect(api.syncIndexDaily).toHaveBeenCalledWith(365)
  expect(active().querySelector('[data-cn-chart]')?.getAttribute('data-cn-chart')).toBe('399001.SZ')
})

it.each(['HK', 'US'] as const)('direct %s preview renders isolated fixture without CN/API/fetch activity', async market => {
  const fetch = vi.fn(() => { throw new Error('No preview network') }); vi.stubGlobal('fetch', fetch)
  await render(`/indices?market=${market}`)
  expect(active().textContent).toContain(`${market} · Preview`)
  for (const text of ['合成数据', '非生产行情', '不构成投资信号', '仅用于界面验收，不代表真实行情', '交易日：2026-09-16', 'synthetic-fixture']) expect(active().textContent).toContain(text)
  expect(api.indexQuotes).not.toHaveBeenCalled(); expect(api.indexDaily).not.toHaveBeenCalled()
  expect(api.indexMinute).not.toHaveBeenCalled(); expect(api.syncIndexDaily).not.toHaveBeenCalled()
  expect(fetch).not.toHaveBeenCalled(); expect(client.getQueryCache().getAll()).toHaveLength(0)
  expect(host.querySelector('[data-index-market="CN"]')).toBeNull()
})

it('switches HK/US with independent list, selection and sort state', async () => {
  await render('/indices?market=HK&keep=1')
  for (const name of ['恒生指数', '恒生科技指数', '国企指数']) expect(active().textContent).toContain(name)
  await click('[data-index-market="HK"] [aria-label="切换涨跌幅排序"]')
  expect([...active().querySelectorAll<HTMLElement>('[data-preview-index]')].map(i => i.dataset.previewIndex)).toEqual(['HSTECH', 'HSCEI', 'HSI'])
  await click('[data-preview-index="HSCEI"]')
  await switchMarket(2)
  for (const name of ['S&P 500', 'Nasdaq Composite', 'Dow Jones Industrial Average', 'Russell 2000']) expect(active().textContent).toContain(name)
  expect(active().textContent).not.toContain('恒生')
  expect([...active().querySelectorAll<HTMLElement>('[data-preview-index]')].map(i => i.dataset.previewIndex)).toEqual(['IXIC', 'SPX', 'RUT', 'DJI'])
  await click('[data-preview-index="RUT"]')
  expect(active().querySelector('[data-selected-preview]')?.getAttribute('data-selected-preview')).toBe('RUT')
  expect(active().querySelector('[data-preview-field="成交额（fixture）"] dd')?.textContent).toBe('—')
  expect(active().textContent).toContain('fixture 未定义成交额')
  await switchMarket(1)
  expect(active().querySelector('[data-selected-preview]')?.getAttribute('data-selected-preview')).toBe('HSCEI')
  expect(active().textContent).not.toContain('Russell')
  expect(active().querySelector('[aria-label="切换涨跌幅排序"]')?.textContent).toContain('↑')
  expect(host.querySelector('[data-location]')?.textContent).toContain('keep=1')
})

it('keeps the CN panel, chart, range and selection through CN/HK/US transitions', async () => {
  await render('/indices?symbol=399006.SZ')
  const cn = active(), chart = cn.querySelector('[data-cn-chart]')
  const dates = [...cn.querySelectorAll<HTMLInputElement>('input[type="date"]')].map(input => input.value)
  await switchMarket(1); await switchMarket(2); await switchMarket(0)
  expect(active()).toBe(cn)
  expect(cn.querySelector('[data-cn-chart]')).toBe(chart)
  expect(cn.querySelector('[data-cn-chart]')?.getAttribute('data-cn-chart')).toBe('399006.SZ')
  expect([...cn.querySelectorAll<HTMLInputElement>('input[type="date"]')].map(input => input.value)).toEqual(dates)
  expect(active().textContent).not.toContain('合成数据')
})

it('uses URL history for back/forward, remount and navigation away/back', async () => {
  await render('/indices?market=HK')
  await switchMarket(2)
  await click('[data-back]'); expect(active().dataset.indexMarket).toBe('HK')
  await click('[data-forward]'); expect(active().dataset.indexMarket).toBe('US')
  await click('[data-other]'); expect(host.querySelector('[data-index-market]')).toBeNull()
  await click('[data-back]'); expect(active().dataset.indexMarket).toBe('US')
  expect(api.indexDaily).not.toHaveBeenCalled()
})

it('renders every detail field, explicit zero and fixture amount currency', async () => {
  await render('/indices?market=HK')
  for (const name of ['最新值', '涨跌', '涨跌幅', '开盘', '最高', '最低', '昨收', '成交额（fixture）']) expect(active().querySelector(`[data-preview-field="${name}"]`)).not.toBeNull()
  expect(active().querySelector('[data-preview-field="成交额（fixture）"] dd')?.textContent).toContain('HKD')
  await click('[data-preview-index="HSCEI"]')
  expect(active().querySelector('[data-preview-field="涨跌"] dd')?.textContent).toBe('0.00')
  expect(active().querySelector('[data-preview-field="涨跌幅"] dd')?.textContent).toBe('0.00%')
})

it.each(['empty', 'error', 'loading'] as const)('shows safe %s preview state without fallback', async kind => {
  const data = loadIndexPreview('HK')
  await render('/indices?market=HK', <IndexPreview market="HK" state={kind === 'empty' ? { kind: 'ready', data: { ...data, rows: [] } } : { kind }} />)
  expect(host.textContent).toContain(kind === 'empty' ? '暂无指数 Preview 数据' : kind === 'error' ? '指数 Preview 加载失败' : 'Preview 加载中')
  expect(host.textContent).toContain('非生产行情')
  expect(api.indexQuotes).not.toHaveBeenCalled(); expect(api.indexDaily).not.toHaveBeenCalled()
})

it('fixture dates stay fixed under different system clocks and carry provenance on every row', () => {
  vi.useFakeTimers()
  for (const time of ['2020-01-01T00:00:00Z', '2030-01-06T00:00:00Z']) {
    vi.setSystemTime(new Date(time))
    for (const market of ['HK', 'US'] as const) {
      const data = loadIndexPreview(market)
      expect(data.trading_date).toBe('2026-09-16')
      for (const item of [data, ...data.rows]) expect(item).toMatchObject({ status: 'PREVIEW', source: 'synthetic-fixture',
        data_mode: 'preview', is_production: false, is_investment_signal: false, fixture_only: true, synthetic: true, market })
    }
  }
  vi.useRealTimers()
})

it('strictly separates production/mixed data and keeps sorting nonmutating with null last', () => {
  const data = loadIndexPreview('HK')
  expect(() => validateIndexPreview({ ...data, is_production: true } as unknown as IndexPreviewData)).toThrow('index_fixture_preview_required')
  expect(() => validateIndexPreview({ ...data, rows: loadIndexPreview('US').rows })).toThrow('mixed_preview_identity')
  expect(() => validateIndexPreview({ ...data, rows: [{ ...data.rows[0], latest_value: Infinity }] })).toThrow('nonfinite_preview_value')
  const rows = [data.rows[0], { ...data.rows[1], change_pct: null }]
  expect(sortIndexPreview(rows, 'asc')[1].change_pct).toBeNull()
  expect(sortIndexPreview(rows, 'desc')[1].change_pct).toBeNull()
  expect(rows[0].symbol).toBe('HSI')
  expect(loadIndexPreview('HK')).not.toBe(data)
})
