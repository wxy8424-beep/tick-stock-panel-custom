// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
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
vi.mock('@/components/dashboard/DashboardGrid', () => ({ DashboardGrid: () => <div>原 A 股看板网格</div> }))
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
  await act(async () => { root.render(<MemoryRouter initialEntries={[path]}>{page}</MemoryRouter>) })
}
function assertControls() {
  const group = host.querySelector('[aria-label="市场选择"]')!
  expect(group).not.toBeNull()
  const buttons = group.querySelectorAll('button')
  expect(buttons[0].getAttribute('aria-pressed')).toBe('true')
  expect(buttons[1].disabled).toBe(true)
  expect(buttons[2].disabled).toBe(true)
  return buttons
}

it('Dashboard retains its CN title/grid and query identity after disabled clicks', async () => {
  await render(<Dashboard />, '/')
  expect(host.textContent).toContain('市场看板')
  expect(host.textContent).toContain('原 A 股看板网格')
  expect(fixtures.queryKeys).toContainEqual(['overview-market', 'latest'])
  const count = fixtures.queryKeys.length
  const buttons = assertControls()
  await act(async () => { buttons[1].click(); buttons[2].click() })
  expect(fixtures.queryKeys).toHaveLength(count)
  expect(host.textContent).toContain('原 A 股看板网格')
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
