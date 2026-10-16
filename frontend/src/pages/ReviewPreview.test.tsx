// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ReviewPage } from '@/custom/review/extension'
import { ReviewPreview } from '@/custom/damon/review-preview/Presentation'
import { validateReviewPreview, type ReviewPreviewData } from '@/custom/damon/review-preview/contract'
import { loadReviewPreview } from '../../tests/fixtures/review_preview'

const state = vi.hoisted(() => ({ queries: [] as unknown[][], mutate: vi.fn(), start: vi.fn(), preferences: vi.fn(), review: vi.fn() }))
vi.mock('@tanstack/react-query', async original => ({ ...await original<typeof import('@tanstack/react-query')>(),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({ mutate: state.mutate, isPending: false }),
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    state.queries.push(queryKey)
    return { data: queryKey[0] === 'review-reports' ? { reports: [] } : queryKey[0] === 'overview-market' ? { as_of: '2026-09-16', indices: [] } : undefined, isLoading: false, refetch: vi.fn() }
  },
}))
vi.mock('@/lib/useSharedQueries', () => ({ usePreferences: () => { state.preferences(); return { data: {} } } }))
vi.mock('@/lib/useReviewStore', () => ({ useReviewState: () => { state.review(); return { phase: 'idle', content: '', error: null, meta: null } } }))
vi.mock('@/lib/reviewStore', () => ({ startReviewGeneration: state.start, resetReview: vi.fn(), isReviewGenerating: () => false, cancelReviewGeneration: vi.fn() }))
vi.mock('@/components/StockPreviewDialog', () => ({ StockPreviewDialog: () => null }))
let host: HTMLDivElement, root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  state.queries = []; vi.clearAllMocks()
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })
async function render(path = '/review', element = <ReviewPage />) {
  function Navigation() { const location = useLocation(), navigate = useNavigate(); return <><output data-location>{location.search}</output><button data-back onClick={() => navigate(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Navigation /></MemoryRouter>))
}
function active() { return host.querySelector<HTMLElement>('[data-review-market]:not([hidden])')! }
async function market(index: number) { await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[index].click()) }
async function search(value: string) {
  const input = active().querySelector<HTMLInputElement>('[aria-label="搜索复盘演示"]')!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })) })
}
it('CN keeps original latest queries, focus state and generation through market navigation', async () => {
  await render('/review?keep=1')
  const cn = active(), input = cn.querySelector<HTMLInputElement>('input[placeholder^="可选"]')!
  expect(cn.querySelector('h1')?.textContent).toBe('AI 复盘')
  expect(state.queries).toContainEqual(['overview-market', 'latest']); expect(state.queries).toContainEqual(['review-reports'])
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '保留关注点'); input.dispatchEvent(new Event('input', { bubbles: true })) })
  await market(1); await market(2); await market(0)
  expect(active()).toBe(cn); expect(input.value).toBe('保留关注点')
  expect(cn.textContent).not.toContain('演示数据｜非生产行情')
  const generate = [...cn.querySelectorAll('button')].find(b => b.textContent?.includes('生成复盘'))!
  await act(async () => generate.click())
  expect(state.start).toHaveBeenCalledWith(undefined, '保留关注点', expect.any(Function))
})
it.each(['HK', 'US'] as const)('direct %s renders isolated fixture without queries, AI, mutation, fetch or persistence', async m => {
  const fetch = vi.fn(), write = vi.spyOn(Storage.prototype, 'setItem'); vi.stubGlobal('fetch', fetch)
  await render(`/review?market=${m}`)
  for (const text of ['2026-09-16', '演示数据｜非生产行情｜不构成投资信号', 'synthetic-fixture', 'PREVIEW', '不是 AI 生成', 'available_at', '生产输入仍 BLOCKED']) expect(active().textContent).toContain(text)
  expect(active().textContent).toContain(m === 'HK' ? '0700.HK' : 'AAPL.US')
  expect(active().textContent).not.toContain(m === 'HK' ? 'AAPL.US' : '0700.HK')
  await act(async () => active().querySelector<HTMLButtonElement>('button:disabled')!.click())
  expect(state.queries).toHaveLength(0)
  for (const spy of [state.start, state.mutate, state.preferences, state.review, fetch, write]) expect(spy).not.toHaveBeenCalled()
  expect(host.querySelector('[data-review-market="CN"]')).toBeNull()
})
it('independent date/filter state survives switching and browser back, preserving other URL parameters', async () => {
  await render('/review?market=HK&keep=1')
  await act(async () => active().querySelector<HTMLButtonElement>('[data-report-date="2026-09-15"]')!.click())
  await search('腾讯')
  expect(active().querySelector('tbody')?.textContent).toContain('0700.HK')
  expect(active().querySelectorAll('tbody tr')).toHaveLength(1)
  await market(2)
  expect(active().textContent).toContain('交易日：2026-09-16'); expect(active().querySelectorAll('tbody tr')).toHaveLength(6)
  await act(async () => host.querySelector<HTMLButtonElement>('[data-back]')!.click())
  expect(active().dataset.reviewMarket).toBe('HK'); expect(active().textContent).toContain('交易日：2026-09-15')
  expect(active().querySelector<HTMLInputElement>('input')?.value).toBe('腾讯')
  expect(host.querySelector('[data-location]')?.textContent).toContain('keep=1')
})
it('sorts fraction returns with nulls last, renders zero and explicit missing evidence', async () => {
  await render('/review?market=US')
  const header = [...active().querySelectorAll('th')].find(th => th.textContent?.startsWith('涨跌幅'))!
  await act(async () => header.click())
  let rows = [...active().querySelectorAll('tbody tr')]
  expect(rows[0].textContent).toContain('IXIC'); expect(rows.at(-1)?.textContent).toContain('MSFT.US')
  await act(async () => header.click())
  rows = [...active().querySelectorAll('tbody tr')]
  expect(rows[0].textContent).toContain('SPX'); expect(rows[0].textContent).toContain('+1.20%')
  expect(rows.at(-1)?.textContent).toContain('不补零'); expect(rows.at(-1)?.textContent).toContain('fixture:review:US:2026-09-16:MSFT.US:v1')
  expect(rows.find(row => row.textContent?.includes('AAPL.US'))?.textContent).toContain('0.00%')
})
it('filters type, missing fields and local empty search without production fallback', async () => {
  await render('/review?market=HK')
  const select = active().querySelector<HTMLSelectElement>('select')!
  await act(async () => { select.value = 'INDEX'; select.dispatchEvent(new Event('change', { bubbles: true })) })
  expect(active().querySelectorAll('tbody tr')).toHaveLength(2)
  await act(async () => { select.value = 'ALL'; select.dispatchEvent(new Event('change', { bubbles: true })) })
  await act(async () => active().querySelector<HTMLInputElement>('input[type="checkbox"]')!.click())
  expect(active().querySelectorAll('tbody tr')).toHaveLength(1)
  expect(active().querySelector('tbody')?.textContent).toContain('3690.HK')
  await search('does-not-exist'); expect(active().textContent).toContain('暂无匹配的复盘示例')
  expect(state.queries).toHaveLength(0)
})
it('handles loading, error and empty reports without current-date or production fallback', async () => {
  for (const [stateValue, text] of [[{ kind: 'loading' }, '加载中'], [{ kind: 'error' }, '加载失败'], [{ kind: 'ready', data: { ...loadReviewPreview('HK'), reports: [] } }, '暂无复盘演示样稿']] as const) {
    await render('/review?market=HK', <ReviewPreview market="HK" state={stateValue} />)
    expect(host.textContent).toContain(text); expect(host.querySelector('table')).toBeNull()
  }
})
it('fixture dates are fixed and loads do not share mutable objects', () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z'))
  const a = loadReviewPreview('HK'), b = loadReviewPreview('HK')
  expect(a).toEqual(b); expect(a.reports[0]).not.toBe(b.reports[0]); expect(a.reports[0].rows[0]).not.toBe(b.reports[0].rows[0])
  expect(a.reports.map(r => r.trading_date)).toEqual(['2026-09-16', '2026-09-15'])
  expect(a.reports.every(r => r.available_at === null)).toBe(true)
})
it('rejects production flags, mixed markets, nonfinite values and missing reasons', () => {
  const bad = (edit: (data: ReviewPreviewData) => unknown) => { const data = structuredClone(loadReviewPreview('HK')); edit(data); expect(() => validateReviewPreview(data)).toThrow() }
  bad(data => Object.assign(data, { is_production: true }))
  bad(data => Object.assign(data.reports[0].rows[0], { market: 'US' }))
  bad(data => Object.assign(data.reports[0].rows[0], { change_pct: Infinity }))
  bad(data => Object.assign(data.reports[0].rows.at(-1)!, { missing_reason: null }))
})
