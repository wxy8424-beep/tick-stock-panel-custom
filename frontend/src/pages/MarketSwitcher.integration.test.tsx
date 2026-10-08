// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Dashboard } from './Dashboard'
import { Watchlist } from './Watchlist'
import { Settings } from './Settings'

const fixtures = vi.hoisted(() => ({
  overview: { as_of: '2026-10-08', emotion: { score: 50, label: '中性' }, quote_status: {} },
  watchlist: { symbols: [] }, groups: { groups: [] },
  queryKeys: [] as unknown[][],
}))
vi.mock('@tanstack/react-query', async importOriginal => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return { ...actual,
    useQueryClient: () => ({ invalidateQueries: vi.fn(), setQueryData: vi.fn() }),
    useMutation: () => ({ mutate: vi.fn(), isPending: false }),
    useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
      fixtures.queryKeys.push(queryKey)
      const data = queryKey[0] === 'overview-market' ? fixtures.overview
        : queryKey[0] === 'watchlist' ? fixtures.watchlist
          : queryKey[0] === 'watchlist-groups' ? fixtures.groups : undefined
      return { data, isLoading: false, isSuccess: true, refetch: vi.fn() }
    },
  }
})
vi.mock('@/lib/useSharedQueries', () => ({
  useDataStatus: () => ({ data: { enriched: { trading_days: 1, latest_date: '2026-10-08' } } }),
  useCapabilities: () => ({ data: { capabilities: {} } }),
  useSettings: () => ({ data: { onboarding_completed: true } }),
  usePreferences: () => ({ data: {} }), useQuoteStatus: () => ({ data: {} }),
}))
vi.mock('@/components/dashboard/useDashboardLayout', () => ({ useDashboardLayout: () => ({ items: [], setItems: vi.fn() }) }))
vi.mock('@/components/dashboard/DashboardGrid', async importOriginal => ({ ...await importOriginal<typeof import('@/components/dashboard/DashboardGrid')>(), DashboardGrid: ({ renderItem }: { renderItem?: unknown }) => <div>{renderItem ? '美股独立看板网格' : '原 A 股看板网格'}</div> }))
vi.mock('@/components/AdjFactorSyncGate', () => ({ useAdjFactorSyncGate: () => ({ guard: vi.fn(), dialog: null }) }))
vi.mock('@/components/StockPreviewDialog', () => ({ StockPreviewDialog: () => null }))
vi.mock('@/components/DimensionMembersDialog', () => ({ DimensionMembersDialog: () => null, dimensionKindForSourceField: () => null }))
vi.mock('@/extensions/ExtensionSlot', () => ({ ExtensionSlot: () => null }))
vi.mock('./settings/DataSources', () => ({ SettingsDataSourcesPanel: () => <div>数据源设置</div> }))

let host: HTMLDivElement
let root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  fixtures.queryKeys.length = 0
  host = document.createElement('div'); document.body.append(host)
  root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

async function render(page: React.ReactNode, path: string) {
  function Location() {
    const location = useLocation()
    return <output data-location>{location.pathname}{location.search}</output>
  }
  await act(async () => { root.render(<MemoryRouter initialEntries={[path]}>{page}<Location /></MemoryRouter>) })
}
function assertControls(hkEnabled = false, usEnabled = false) {
  const group = host.querySelector('[aria-label="市场选择"]')!
  expect(group).not.toBeNull()
  const buttons = group.querySelectorAll('button')
  expect(buttons[0].getAttribute('aria-pressed')).toBe('true')
  expect(buttons[1].disabled).toBe(!hkEnabled)
  expect(buttons[2].disabled).toBe(!usEnabled)
  return buttons
}

it('Dashboard preserves CN queries/grid and URL parameters through CN -> US -> HK -> CN', async () => {
  await render(<Dashboard />, '/?keep=original')
  expect(host.textContent).toContain('市场看板')
  expect(host.textContent).toContain('原 A 股看板网格')
  expect(fixtures.queryKeys).toContainEqual(['overview-market', 'latest'])
  const buttons = assertControls(true, true)
  await act(async () => buttons[2].click())
  expect(host.querySelector('h1')?.textContent).toBe('美股市场看板')
  expect(host.querySelector('[data-location]')?.textContent).toBe('/?keep=original&market=US')
  await act(async () => host.querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[1].click())
  expect(host.querySelector('h1')?.textContent).toBe('港股市场')
  expect(host.querySelector('[data-location]')?.textContent).toBe('/?keep=original&market=HK')
  await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="市场选择"] button')!.click())
  expect(host.querySelector('h1')?.textContent).toBe('市场看板')
  expect(host.textContent).toContain('原 A 股看板网格')
  expect(host.querySelector('[data-location]')?.textContent).toBe('/?keep=original&market=CN')
})

it('direct URL and refresh initial state render HK without mounting CN queries', async () => {
  await render(<Dashboard />, '/?market=HK')
  expect(host.querySelector('h1')?.textContent).toBe('港股市场')
  expect(fixtures.queryKeys.some(key => key[0] === 'overview-market')).toBe(false)
  const buttons = host.querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')
  expect(buttons[1].getAttribute('aria-pressed')).toBe('true')
  expect(buttons[2].disabled).toBe(false)
})

it('direct US URL preserves US on refresh and never mounts CN query keys', async () => {
  await render(<Dashboard />, '/?market=US')
  expect(host.querySelector('h1')?.textContent).toBe('美股市场看板')
  expect(fixtures.queryKeys.some(key => key[0] === 'overview-market' || key[0] === 'hk-dashboard')).toBe(false)
  expect(fixtures.queryKeys).toContainEqual(['us-dashboard', 'default'])
  expect(host.querySelectorAll('[aria-label="市场选择"] button')[2].getAttribute('aria-pressed')).toBe('true')
})

it('Watchlist retains CN filters and the original query without changing on disabled clicks', async () => {
  await render(<Watchlist />, '/watchlist')
  expect(host.querySelector('h1')?.textContent).toBe('自选股')
  expect(fixtures.queryKeys).toContainEqual(['watchlist'])
  const content = host.textContent
  const count = fixtures.queryKeys.length
  const buttons = assertControls()
  await act(async () => { buttons[1].click(); buttons[2].click() })
  expect(host.textContent).toBe(content)
  expect(fixtures.queryKeys).toHaveLength(count)
})

it('actual Settings page keeps its settings content without market controls', async () => {
  await render(<Settings />, '/settings')
  expect(host.textContent).toContain('数据源设置')
  expect(host.querySelector('[aria-label="市场选择"]')).toBeNull()
})
