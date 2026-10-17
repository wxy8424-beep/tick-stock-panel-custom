// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Data } from './Data'
import { DataPreview } from '@/custom/damon/data-preview/Presentation'
import { validateDataPreview } from '@/custom/damon/data-preview/contract'
import { loadDataPreview } from '../../tests/fixtures/data_preview'

const state = vi.hoisted(() => ({ queries: [] as unknown[][], mutate: vi.fn(), api: vi.fn() }))
vi.mock('@tanstack/react-query', async original => ({ ...await original<typeof import('@tanstack/react-query')>(),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }), useMutation: () => ({ mutate: state.mutate, isPending: false }),
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => { state.queries.push(queryKey); return { data: undefined, isLoading: false, refetch: vi.fn() } },
}))
vi.mock('@/lib/api', async original => { const actual = await original<typeof import('@/lib/api')>(); return { ...actual, api: Object.fromEntries(Object.keys(actual.api).map(k => [k, (...args: unknown[]) => state.api(k, args)])) } })
let host: HTMLDivElement, root: Root
beforeEach(() => { Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.clearAllMocks(); state.queries = []; host = document.createElement('div'); document.body.append(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })
async function render(path = '/data', element = <Data />) {
  function Nav() { const l = useLocation(), navigate = useNavigate(); return <><output data-location>{l.search}</output><button data-back onClick={() => navigate(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Nav /></MemoryRouter>))
}
function active() { return host.querySelector<HTMLElement>('[data-data-market]:not([hidden])')! }
async function market(i: number) { await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[i].click()) }
async function search(v: string) { const el = active().querySelector<HTMLInputElement>('input[aria-label="搜索数据样稿"]')!; await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })) }) }
async function filter(label: string, v: string) { const el = active().querySelector<HTMLSelectElement>(`select[aria-label="${label}"]`)!; await act(async () => { el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })) }) }
async function dataset(id: string) { await act(async () => active().querySelector<HTMLButtonElement>(`[data-dataset-id="${id}"]`)!.click()) }
it('CN keeps production query keys, original sync and clear confirmation handlers; leaving closes execution dialogs', async () => {
  await render(); expect(active().querySelector('h1')?.textContent).toBe('数据')
  for (const key of [['data-status'], ['pipeline-jobs'], ['ext-data']]) expect(state.queries).toContainEqual(key)
  expect(active().textContent).toContain('本地数据画像 · 同步状态 · 历史记录')
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent?.trim() === '立即同步')!.click()); expect(state.mutate).toHaveBeenCalledTimes(1)
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent?.trim() === '清除数据')!.click())
  expect([...active().querySelectorAll('button')].filter(b => b.textContent?.trim() === '清除数据')).toHaveLength(2)
  await market(1); expect(host.querySelector('[data-data-market="CN"]')).toBeNull(); state.queries = []; state.mutate.mockClear()
  await search('close'); expect(state.queries).toHaveLength(0); expect(state.mutate).not.toHaveBeenCalled()
  await market(0); expect(active().querySelector('h1')?.textContent).toBe('数据'); expect([...active().querySelectorAll('button')].filter(b => b.textContent?.trim() === '清除数据')).toHaveLength(1)
})
it.each(['HK', 'US'] as const)('direct %s uses independent evidence and no production query, refresh, write or notification', async m => {
  const fetch = vi.fn(), write = vi.spyOn(Storage.prototype, 'setItem'), notify = vi.fn(); vi.stubGlobal('fetch', fetch); vi.stubGlobal('Notification', notify)
  await render(`/data?market=${m}`)
  for (const t of ['Preview 数据｜非实时数据源状态｜不代表生产覆盖率', 'synthetic-fixture', 'PREVIEW', '2026-09-16', '2026-10-17T00:00:00Z', `${m} Longbridge Daily`, '当前生产覆盖：—（未测量）']) expect(active().textContent).toContain(t)
  expect(active().querySelectorAll('[data-dataset-id]')).toHaveLength(m === 'HK' ? 3 : 4)
  expect(active().textContent).not.toContain(m === 'HK' ? 'US Longbridge Daily' : 'HK Longbridge Daily')
  await act(async () => active().querySelectorAll<HTMLButtonElement>('button:disabled').forEach(b => b.click()))
  expect(state.queries).toHaveLength(0); for (const spy of [state.mutate, state.api, fetch, write, notify]) expect(spy).not.toHaveBeenCalled()
  expect(host.querySelector('[data-data-market="CN"]')).toBeNull()
})
it('SDK, limited read, integration and current health stay separate with document evidence', async () => {
  await render('/data?market=US'); const sources = active().querySelector('[aria-label="静态数据源证据"]')!
  for (const t of ['SDK 5.2.0', '2026-10-15', '两种模式各73根', '未接入 Momentum 生产历史输入', '当前生产观测：— · 实时健康：—', 'Research only', 'historical-provider-contract-v1.md']) expect(sources.textContent).toContain(t)
  expect(sources.textContent).not.toContain('HEALTHY'); expect(sources.textContent).not.toContain('RUNNING')
  expect(loadDataPreview('US').sources.every(s => s.health === null && s.production_observation === null)).toBe(true)
})
it('unknown real coverage is null, while separately labeled synthetic coverage has defined denominators and missing reasons', async () => {
  await render('/data?market=HK'); let details = active().querySelector('[aria-label="数据集样稿详情"]')!
  expect(details.textContent).toContain('静态审计结果'); expect(details.querySelector('[data-coverage-field="symbol_count"]')?.textContent).toContain('—（未测量）')
  const d = loadDataPreview('HK'); expect(Object.values(d.rows[0].coverage).every(v => v === null)).toBe(true)
  await dataset('sample-daily-HK'); details = active().querySelector('[aria-label="数据集样稿详情"]')!
  for (const t of ['合成覆盖样稿', '0700.HK', '证券数：2', '已覆盖交易日：2', '缺失交易日：1', '100.0%', '75.0%', '成交额字段比例：—', '2026-09-14', '2026-09-17T06:00:00Z', 'available_at：—', '保留 null', 'fixture:data:HK:coverage:v1']) expect(details.textContent).toContain(t)
  expect(d.rows[1].coverage.turnover_ratio).toBeNull(); expect(d.rows[1].adjustment).toBeNull()
  expect(active().querySelector('[aria-label="生产覆盖边界"]')?.textContent).toContain('—（未测量）')
})
it('latest static quality preserves vendor blockers, exact calendar, naive time and Universe boundaries', async () => {
  await render('/data?market=US'); const quality = active().querySelector('[aria-label="静态质量契约"]')!
  for (const key of ['volume', 'price_basis', 'pit', 'universe', 'corporate_actions']) expect(quality.querySelector(`[data-quality-key="${key}"]`)?.textContent).toContain('BLOCKED')
  expect(quality.querySelector('[data-quality-key="finality"]')?.textContent).toContain('PARTIAL')
  const calendar = quality.querySelector('[data-quality-key="calendar"]')!
  for (const t of ['READY', 'us-cash-equity-official', '2026-v1', 'cfb976ea41ff8037ab0dd5225f061dcb960976cd404bcd10eae2bb74a1084d76', '不证明 Daily 数据覆盖']) expect(calendar.textContent).toContain(t)
  for (const t of ['宿主本地 naive datetime', '不能直接解释为 UTC', 'fetched_at 代替', '不是实时诊断', '供应商审计日期：2026-10-15']) expect(quality.textContent).toContain(t)
})
it('data type, source, quality and field/symbol search filter locally without hiding quality blockers', async () => {
  await render('/data?market=US'); await filter('演示数据类型', 'UNIVERSE'); expect(active().querySelectorAll('[data-dataset-id]')).toHaveLength(1)
  expect(active().querySelector('tbody')?.textContent).toContain('Universe')
  await filter('演示数据类型', 'ALL'); await filter('演示数据源', 'yfinance'); expect(active().querySelectorAll('[data-dataset-id]')).toHaveLength(1)
  await filter('限定质量状态', 'READY'); expect(active().textContent).toContain('暂无匹配的数据集样稿')
  await filter('演示数据源', 'ALL'); expect(active().textContent).toContain('暂无匹配的数据集样稿')
  await filter('限定质量状态', 'PARTIAL'); expect(active().querySelector('tbody')?.textContent).toContain('Daily 字段覆盖样稿')
  await filter('限定质量状态', 'ALL'); await search('NVDA.US'); expect(active().querySelectorAll('[data-dataset-id]')).toHaveLength(1)
  await search('membership_vintage'); expect(active().querySelector('tbody')?.textContent).toContain('Universe')
  expect(active().querySelector('[data-quality-key="volume"]')?.textContent).toContain('BLOCKED'); expect(state.queries).toHaveLength(0)
})
it('coverage sorts known sample before unknowns in both directions and name sorting is functional', async () => {
  await render('/data?market=HK'); const th = [...active().querySelectorAll('th')].find(e => e.textContent?.startsWith('证券数'))!
  for (let n = 0; n < 2; n++) { await act(async () => th.click()); expect(active().querySelector('[data-dataset-id]')?.getAttribute('data-dataset-id')).toBe('sample-daily-HK') }
  await act(async () => [...active().querySelectorAll('th')].find(e => e.textContent?.startsWith('数据集 /'))!.click())
  expect(active().querySelectorAll('[data-dataset-id]')).toHaveLength(3)
})
it('market URL, unrelated parameters and browser back retain isolated filters and details', async () => {
  await render('/data?market=HK&keep=1'); await search('0700.HK'); await dataset('sample-daily-HK'); await market(2)
  expect(active().querySelector<HTMLInputElement>('input')?.value).toBe(''); expect(active().querySelectorAll('[data-dataset-id]')).toHaveLength(4)
  await filter('演示数据源', 'yfinance'); await act(async () => host.querySelector<HTMLButtonElement>('[data-back]')!.click())
  expect(active().dataset.dataMarket).toBe('HK'); expect(active().querySelector<HTMLInputElement>('input')?.value).toBe('0700.HK'); expect(active().textContent).not.toContain('yfinance 研究日线')
  expect(host.querySelector('[data-location]')?.textContent).toContain('keep=1'); await market(2); expect(active().querySelector<HTMLSelectElement>('[aria-label="演示数据源"]')?.value).toBe('yfinance')
})
it('fixed dates are time-independent and fresh fixture objects do not share mutations', async () => {
  const d = loadDataPreview('HK'); vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z')); expect(loadDataPreview('HK')).toEqual(d); vi.useRealTimers()
  const next = loadDataPreview('HK'); expect(next.rows).not.toBe(d.rows); d.rows[1].coverage.volume_ratio = null; expect(next.rows[1].coverage.volume_ratio).toBe(.75)
  await render('/data?market=HK'); expect(active().textContent).not.toContain('2040-01-01'); expect(active().textContent).toContain('不是供应商更新时间')
})
it('rejects non-finite ratios, mixed markets, static production claims and invented dynamic health', () => {
  type D = ReturnType<typeof loadDataPreview>
  for (const mutate of [(d: D) => { d.rows[0].coverage.symbol_count = 0 }, (d: D) => { d.rows[1].coverage.volume_ratio = NaN }, (d: D) => { d.rows[1].coverage.ohlc_ratio = Infinity }, (d: D) => { d.rows[0].market = 'US' }, (d: D) => { Object.assign(d.sources[0], { health: 'HEALTHY' }) }, (d: D) => { d.rows[0].updated_at = '2026-10-17T00:00:00Z' }]) { const d = loadDataPreview('HK'); mutate(d); expect(() => validateDataPreview(d)).toThrow() }
})
it('empty dataset, loading and error keep declaration without production fallback', async () => {
  const empty = loadDataPreview('HK'); empty.rows = []
  for (const [s, t] of [[{ kind: 'loading' }, '加载中'], [{ kind: 'error' }, '加载失败'], [{ kind: 'ready', data: empty }, '暂无匹配的数据集样稿']] as const) {
    await render('/data', <DataPreview market="HK" state={s} />); expect(host.textContent).toContain(t); expect(host.textContent).toContain('Preview 数据｜非实时数据源状态｜不代表生产覆盖率'); expect(host.querySelector('tbody')).toBeNull()
  }
  expect(state.queries).toHaveLength(0); expect(state.api).not.toHaveBeenCalled()
})
