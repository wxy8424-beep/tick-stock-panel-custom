// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { LimitUpLadder } from '@/custom/limit-ladder/extension'
import { MomentumCard, MomentumPreview } from './Presentation'
import { displayOrder, validatePreview } from './contract'
import { loadMomentumPreview } from '../../../../tests/fixtures/momentum_ladder'

const state = vi.hoisted(() => ({ queries: [] as unknown[][], error: false, empty: false, loading: false }))
vi.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    state.queries.push(queryKey)
    const down = queryKey[3] === 'down'
    return { data: queryKey[0] === 'limit-ladder' ? {
      as_of: queryKey[1] || '2026-09-16', counts: { up: 1, down: 1 }, sealed_ready: false,
      tiers: state.empty ? [] : [{ boards: 1, count: 1, stocks: [{ symbol: '600000.SH', name: 'A股对照股票',
        close: 12, change_pct: down ? -0.1 : 0.1, status: down ? 'limit_down' : 'limit_up',
        consecutive_limit_ups: 1, consecutive_limit_downs: 1 }] }],
    } : { rules: [] }, isLoading: state.loading, isError: state.error, isFetching: false, refetch: vi.fn() }
  },
}))
vi.mock('@/lib/useSharedQueries', () => ({
  useCapabilities: () => ({ data: { capabilities: {} } }), usePreferences: () => ({ data: {} }),
}))
vi.mock('@/components/StockPreviewDialog', () => ({ StockPreviewDialog: ({ symbol }: { symbol: string | null }) => <output data-stock-dialog>{symbol}</output> }))
vi.mock('@/components/DimensionMembersDialog', () => ({ DimensionMembersDialog: () => null }))
vi.mock('@/components/SealedBadge', () => ({ SealedBadge: () => <span>原封单状态</span> }))
vi.mock('@/lib/theme', () => ({ useTheme: () => 'dark' }))
vi.mock('@/components/DatePicker', () => ({ DatePicker: ({ value, onChange }: { value: string; onChange: (value: string) => void }) =>
  <button aria-label="A股日期" onClick={() => onChange('2026-09-15')}>{value}</button> }))

let host: HTMLDivElement
let root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.stubGlobal('scrollTo', vi.fn())
  localStorage.clear()
  state.queries = []; state.error = false; state.empty = false; state.loading = false
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals() })

async function render(element = <LimitUpLadder />, path = '/limit-ladder') {
  function Location() { const location = useLocation(); return <output data-location>{location.pathname}{location.search}</output> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Location /></MemoryRouter>))
}
async function market(index: number) {
  await act(async () => host.querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[index].click())
}

it('keeps the CN ladder/query/filter/direction/card behavior and state across market switches', async () => {
  await render(undefined, '/limit-ladder?keep=1')
  expect(host.querySelector('h1')?.textContent).toBe('连板梯队')
  expect(host.textContent).toContain('A股对照股票')
  expect(state.queries.some(key => key[0] === 'limit-ladder' && key[1] === undefined && key[3] === 'up')).toBe(true)
  for (const label of ['概念', '行业', '主板', '涨停', '跌停']) expect(host.textContent).toContain(label)
  const down = [...host.querySelectorAll('button')].find(button => button.textContent === '跌停1')!
  await act(async () => down.click())
  expect(host.querySelector('h1')?.textContent).toBe('连跌梯队')
  expect(state.queries.some(key => key[0] === 'limit-ladder' && key[3] === 'down')).toBe(true)
  const cn = host.querySelector('[data-cn-ladder]')!
  await act(async () => cn.querySelector<HTMLButtonElement>('[aria-label="A股日期"]')!.click())
  expect(state.queries.some(key => key[0] === 'limit-ladder' && key[1] === '2026-09-15' && key[3] === 'down')).toBe(true)
  await act(async () => cn.querySelector<HTMLElement>('[role="button"]')!.click())
  expect(cn.querySelector('[data-stock-dialog]')?.textContent).toBe('600000.SH')
  const industry = [...cn.querySelectorAll('button')].find(button => button.textContent === '行业')!
  await act(async () => industry.click())
  const industryClass = industry.className
  await market(1)
  expect(cn.querySelector('[data-stock-dialog]')).toBeNull()
  await market(2); await market(0)
  expect(host.querySelector('[data-cn-ladder]')).toBe(cn)
  expect(cn.querySelector('h1')?.textContent).toBe('连跌梯队')
  expect(cn.querySelector('[aria-label="A股日期"]')?.textContent).toBe('2026-09-15')
  expect(cn.querySelector('[data-stock-dialog]')?.textContent).toBe('600000.SH')
  expect(industry.className).toBe(industryClass)
  expect(host.querySelector('[data-location]')?.textContent).toBe('/limit-ladder?keep=1&market=CN')
})

it.each(['HK', 'US'] as const)('direct %s preview mounts no CN queries and makes no data requests', async m => {
  const fetch = vi.fn(() => { throw new Error('Preview must not fetch') })
  vi.stubGlobal('fetch', fetch)
  await render(undefined, `/limit-ladder?market=${m}`)
  expect(state.queries).toHaveLength(0)
  expect(fetch).not.toHaveBeenCalled()
  expect(host.querySelector('[data-cn-ladder]')).toBeNull()
  expect(host.textContent).toContain('Momentum Preview')
  expect(host.textContent).toContain('非生产数据')
  expect(host.textContent).toContain('Production Execution: BLOCKED')
  expect(host.textContent).toContain('2026-09-16')
  expect(host.querySelector(`[data-momentum-preview="${m}"]`)).not.toBeNull()
})

it('switches HK/US without mixing symbols and preserves URL parameters', async () => {
  await render(undefined, '/limit-ladder?market=HK&keep=fixture')
  expect(host.textContent).toContain('0700.HK')
  await market(2)
  expect(host.textContent).toContain('AAPL.US'); expect(host.textContent).not.toContain('0700.HK')
  expect(host.querySelector('[data-location]')?.textContent).toContain('keep=fixture')
  await market(1)
  expect(host.textContent).toContain('9988.HK'); expect(host.textContent).not.toContain('AAPL.US')
  expect(state.queries).toHaveLength(0)
})

it('renders HK tiers, independent theme and non-causal follower explanation', async () => {
  await render(<MomentumPreview view={loadMomentumPreview('HK')} />)
  for (const label of ['T1 龙头', 'T2 强势', 'T3 强势', '突破', '连续上涨', '放量', '不表示因果跟随', '主题：暂无可靠数据']) {
    expect(host.textContent).toContain(label)
  }
  for (const symbol of ['0700.HK', '9988.HK', '3690.HK']) expect(host.querySelector(`[data-symbol="${symbol}"]`)).not.toBeNull()
})

it('renders US overlapping labels/groups plus provided ranks and all three tiers', async () => {
  await render(<MomentumPreview view={loadMomentumPreview('US')} />)
  const card = host.querySelector('[data-symbol="AAPL.US"]')!
  for (const label of ['Momentum Leader', 'Breakout', 'Gap Up', 'Volume Spike', 'Consecutive Up']) expect(card.textContent).toContain(label)
  expect(card.querySelector('[data-score]')?.textContent).toBe('86.00')
  expect(card.querySelector('[data-rank]')?.textContent).toBe('1')
  for (const tier of ['T1', 'T2', 'T3']) expect([...host.querySelectorAll('[data-tier]')].some(node => node.textContent === tier)).toBe(true)
})

it('renders nulls with reasons and preserves false/zero as explicit real fixture values', async () => {
  const missing = loadMomentumPreview('US').items.find(i => i.quality.status === 'BLOCKED')!
  await render(<MomentumCard item={missing} />)
  for (const key of ['close', 'volume_ratio', 'breakout_status', 'volatility_trend_status']) {
    expect(host.querySelector(`[data-metric="${key}"] dd`)?.textContent).toBe('—')
  }
  expect(host.querySelector('[data-score]')?.textContent).toBe('—')
  expect(host.textContent).toContain('缺少前一交易日波动率')
  expect(host.textContent).toContain('成交量单位及公司行动可比性尚未证明')
  const zero = loadMomentumPreview('US').items[1]
  await render(<MomentumCard item={{ ...zero, metrics: { ...zero.metrics,
    close: { value: 0, status: 'READY', reason: null }, breakout_status: { value: false, status: 'READY', reason: null },
  } }} />)
  expect(host.querySelector('[data-metric="close"] dd')?.textContent).toBe('0.00')
  expect(host.querySelector('[data-metric="breakout_status"] dd')?.textContent).toBe('未突破')
})

it('exposes status/evidence and fixed timestamps separately from production readiness', async () => {
  await render(<MomentumPreview view={loadMomentumPreview('US')} />)
  for (const text of ['READY', 'PARTIAL', 'BLOCKED', 'Data Status', 'Evidence Status', 'Universe', 'Calculation',
    'Score Profile', 'momentum-daily / v1.1', 'momentum-technical / v1.2', 'Source', 'Generated At', 'Available At',
    'Finality', 'PIT status', 'synthetic-fixture/us/v1', '2026-09-17T00:00:00Z', '历史可得时间未知']) {
    expect(host.textContent).toContain(text)
  }
  expect(host.textContent).toContain('非生产 READY')
})

it.each(['empty', 'error', 'loading'] as const)('CN %s retains a usable market switch and original state', async kind => {
  state[kind] = true
  await render()
  if (kind === 'empty') expect(host.textContent).toContain('暂无连板数据')
  if (kind === 'error') expect(host.textContent).toContain('连板数据加载失败')
  await market(1)
  expect(host.textContent).toContain('港股 Momentum Ladder')
})

it('fixture adapter is isolated, fixed-date, rejects production/mixed markets and never persists', () => {
  const write = vi.spyOn(Storage.prototype, 'setItem')
  const a = loadMomentumPreview('HK'), b = loadMomentumPreview('HK')
  expect(a).toEqual(b); expect(a).not.toBe(b); expect(a.items[0]).not.toBe(b.items[0])
  expect(a).toMatchObject({ fixture_only: true, production: false, synthetic: true, trading_date: '2026-09-16' })
  expect(() => validatePreview({ ...a, production: true } as unknown as typeof a)).toThrow('fixture_preview_required')
  expect(() => validatePreview({ ...a, items: loadMomentumPreview('US').items })).toThrow('preview_market_or_identity_conflict')
  expect(write).not.toHaveBeenCalled(); write.mockRestore()
})

it('display order uses existing rank, null last and symbol only to stabilize tied display', () => {
  const items = loadMomentumPreview('US').items
  const reversed = [...items].reverse()
  expect(displayOrder(reversed).map(i => i.rank)).toEqual([1, 2, 3, null, null])
  expect(reversed).toEqual([...items].reverse())
  const tied = [{ ...items[0], symbol: 'Z.US', rank: 1 }, { ...items[1], symbol: 'A.US', rank: 1 }]
  expect(displayOrder(tied).map(i => [i.symbol, i.rank])).toEqual([['A.US', 1], ['Z.US', 1]])
})
