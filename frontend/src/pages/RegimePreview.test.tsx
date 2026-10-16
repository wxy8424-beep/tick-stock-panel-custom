// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Regime } from './Regime'
import { EnvironmentPreview } from '@/custom/damon/environment-preview/Presentation'
import { loadEnvironmentPreview } from '../../tests/fixtures/environment_preview'
import { validateEnvironmentPreview, type EnvironmentPreviewData } from '@/custom/damon/environment-preview/contract'

const state = vi.hoisted(() => ({ queries: [] as unknown[][], init: vi.fn(), recompute: vi.fn() }))
vi.mock('@tanstack/react-query', async original => ({ ...await original<typeof import('@tanstack/react-query')>(),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    state.queries.push(queryKey)
    return { data: queryKey[0] === 'regime-coverage' ? { rows: 0, earliest_date: null, latest_date: null } : { rows: [], distribution: [], segments: [] }, isLoading: false, refetch: vi.fn() }
  },
}))
vi.mock('echarts', () => ({ init: (...args: unknown[]) => { state.init(...args); return { resize: vi.fn(), setOption: vi.fn(), dispose: vi.fn(), getZr: () => ({ on: vi.fn(), off: vi.fn() }) } } }))
vi.mock('@/lib/api', async original => {
  const actual = await original<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, regimeRecompute: state.recompute } }
})
let host: HTMLDivElement, root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); state.queries = []; vi.clearAllMocks()
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })
async function render(path = '/regime', element = <Regime />) {
  function Navigation() { const location = useLocation(), navigate = useNavigate(); return <><output data-location>{location.search}</output><button data-back onClick={() => navigate(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Navigation /></MemoryRouter>))
}
function active() { return host.querySelector<HTMLElement>('[data-environment-market]:not([hidden])')! }
async function market(index: number) { await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[index].click()) }
async function button(text: string) { await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent === text)!.click()) }
async function date(value: string) { const select = active().querySelector<HTMLSelectElement>('select')!; await act(async () => { select.value = value; select.dispatchEvent(new Event('change', { bubbles: true })) }) }
async function search(value: string) {
  const input = active().querySelector<HTMLInputElement>('[aria-label="搜索环境指数"]')!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })) })
}
it('CN default preserves original range queries, phase tab, empty state and retained UI', async () => {
  await render('/regime?keep=cn')
  const cn = active()
  expect(cn.querySelector('h1')?.textContent).toBe('市场环境')
  expect(state.queries).toContainEqual(['regime-history', '1y'])
  expect(state.queries).toContainEqual(['regime-states', 250])
  await button('2年')
  expect(state.queries).toContainEqual(['regime-history', '2y']); expect(state.queries).toContainEqual(['regime-states', 500])
  await button('情绪周期')
  expect(cn.textContent).toContain('涨停情绪 · 市场阶段 · 主线脉络')
  await market(1); await market(2); await market(0)
  expect(active()).toBe(cn); expect(cn.textContent).toContain('涨停情绪 · 市场阶段 · 主线脉络')
  expect([...cn.querySelectorAll('button')].find(b => b.textContent === '2年')?.className).toContain('bg-accent')
  expect(cn.textContent).not.toContain('演示数据｜非生产行情')
  expect(state.recompute).not.toHaveBeenCalled()
})
it('CN custom range modal stays off the Preview and restores without changing original apply semantics', async () => {
  await render()
  await button('自定义')
  expect(host.querySelector('[aria-label="自定义天数"]')).not.toBeNull()
  await market(1)
  expect(host.querySelector('[aria-label="自定义天数"]')).toBeNull()
  await market(0)
  const input = host.querySelector<HTMLInputElement>('input[type="number"]')!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, '90'); input.dispatchEvent(new Event('input', { bubbles: true })) })
  await button('应用')
  expect(state.queries).toContainEqual(['regime-history', { custom: 90 }])
  expect(state.queries).toContainEqual(['regime-states', 90])
})
it.each(['HK', 'US'] as const)('direct %s uses only dedicated synthetic fixture, never queries production or initializes CN charts', async m => {
  const fetch = vi.fn(), storage = vi.spyOn(Storage.prototype, 'setItem'); vi.stubGlobal('fetch', fetch)
  await render(`/regime?market=${m}`)
  for (const text of ['演示数据｜非生产行情｜不构成投资信号', 'synthetic-fixture', 'PREVIEW', 'Session：NONE', 'POST_CLOSE', '2026-09-16', 'generated_at: 2026-09-17T01:00:00Z', 'available_at: —', 'missing_fields:', 'Volume / VR20 BLOCKED', 'split-only price basis BLOCKED']) expect(active().textContent).toContain(text)
  const names = m === 'HK' ? ['恒生指数', '恒生科技指数', '国企指数'] : ['S&P 500', 'Nasdaq Composite', 'Dow Jones', 'Russell 2000']
  for (const name of names) expect(active().textContent).toContain(name)
  expect(active().querySelectorAll('tbody tr')).toHaveLength(names.length)
  expect(active().textContent).toContain(`fixture:environment:${m}:2026-09-16:v1`)
  await act(async () => active().querySelector<HTMLButtonElement>('button:disabled')!.click())
  expect(state.queries).toHaveLength(0)
  for (const spy of [state.recompute, state.init, fetch, storage]) expect(spy).not.toHaveBeenCalled()
  expect(host.querySelector('[data-environment-market="CN"]')).toBeNull()
})
it('HK/US dates and search are independent; URL back and remount restore market without mixing statistics', async () => {
  await render('/regime?market=HK&keep=1')
  await date('2026-09-15'); await search('恒生科技')
  expect(active().querySelectorAll('tbody tr')).toHaveLength(1)
  await market(2)
  expect(active().querySelector<HTMLSelectElement>('select')?.value).toBe('2026-09-16')
  expect(active().textContent).toContain('WEAK'); expect(active().textContent).not.toContain('恒生指数')
  expect(active().querySelectorAll('tbody tr')).toHaveLength(4)
  await act(async () => host.querySelector<HTMLButtonElement>('[data-back]')!.click())
  expect(active().dataset.environmentMarket).toBe('HK')
  expect(active().querySelector<HTMLSelectElement>('select')?.value).toBe('2026-09-15')
  expect(active().querySelector<HTMLInputElement>('input')?.value).toBe('恒生科技')
  expect(active().textContent).toContain('NEUTRAL'); expect(host.querySelector('[data-location]')?.textContent).toContain('keep=1')
  await render('/regime?market=US', <EnvironmentPreview market="US" state={{ kind: 'ready', data: loadEnvironmentPreview('US') }} />)
  expect(host.textContent).toContain('S&P 500')
})
it('sorts fractions with nulls last and preserves explicit zero and missing reasons', async () => {
  await render('/regime?market=HK')
  const header = [...active().querySelectorAll('th')].find(th => th.textContent?.startsWith('涨跌幅'))!
  await act(async () => header.click())
  expect(active().querySelector('tbody tr')?.textContent).toContain('HSCEI')
  await act(async () => header.click())
  expect(active().querySelector('tbody tr')?.textContent).toContain('HSI')
  expect(active().querySelector('tbody tr')?.textContent).toContain('+1.50%')
  expect(active().textContent).toContain('0.00%')
  const pointHeader = [...active().querySelectorAll('th')].find(th => th.textContent?.startsWith('样稿点位'))!
  await act(async () => pointHeader.click())
  expect([...active().querySelectorAll('tbody tr')].at(-1)?.textContent).toContain('HSCEI')
  expect(active().querySelector('[aria-label="强弱环境"]')?.textContent).toContain('—')
  expect(active().textContent).toContain('未提供 Volume Spike 样稿统计')
  expect(active().textContent).toContain('此指数未编写样稿点位')
})
it('missing-only and empty search stay inside the selected market and date', async () => {
  await render('/regime?market=US')
  await act(async () => active().querySelector<HTMLInputElement>('input[type="checkbox"]')!.click())
  expect(active().querySelectorAll('tbody tr')).toHaveLength(2)
  await search('no matching synthetic symbol')
  expect(active().textContent).toContain('暂无匹配的环境指数')
  expect(state.queries).toHaveLength(0)
})
it('unavailable conclusion has a reason and never runs a fallback score', async () => {
  await render('/regime?market=US'); await date('2026-09-15')
  const conclusion = active().querySelector('[aria-label="市场环境结论"]')!
  expect(conclusion.textContent).toContain('UNAVAILABLE'); expect(conclusion.textContent).toContain('未编写环境结论')
  expect(active().textContent).toContain('市场状态：CLOSED')
  expect(state.queries).toHaveLength(0)
})
it('loading/error/empty states do not synthesize dates or request production data', async () => {
  for (const [value, text] of [[{ kind: 'loading' }, '加载中'], [{ kind: 'error' }, '加载失败'], [{ kind: 'ready', data: { ...loadEnvironmentPreview('HK'), days: [] } }, '暂无市场环境演示数据']] as const) {
    await render('/regime?market=HK', <EnvironmentPreview market="HK" state={value} />)
    expect(host.textContent).toContain(text); expect(host.querySelector('table')).toBeNull()
    expect(host.textContent).not.toContain('generated_at:')
  }
  expect(state.queries).toHaveLength(0)
})
it('fixed dates and deep independent fixture objects do not depend on the system clock', () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z'))
  const a = loadEnvironmentPreview('US'), b = loadEnvironmentPreview('US')
  expect(a).toEqual(b); expect(a.days[0].indices[0]).not.toBe(b.days[0].indices[0]); expect(a.days[0].metrics.up).not.toBe(b.days[0].metrics.up)
  expect(a.days.map(d => d.trading_date)).toEqual(['2026-09-16', '2026-09-15'])
  expect(a.days.every(d => d.available_at === null)).toBe(true)
})
it('rejects production flags, mixed market/date, nonfinite/invalid counts and unexplained missing values', () => {
  const bad = (edit: (d: EnvironmentPreviewData) => unknown) => { const data = structuredClone(loadEnvironmentPreview('HK')); edit(data); expect(() => validateEnvironmentPreview(data)).toThrow() }
  bad(d => Object.assign(d, { is_production: true }))
  bad(d => Object.assign(d.days[0].indices[0], { market: 'US' }))
  bad(d => Object.assign(d.days[0].indices[0], { trading_date: '2020-01-01' }))
  bad(d => Object.assign(d.days[0].metrics.up, { value: NaN }))
  bad(d => Object.assign(d.days[0].metrics.down, { value: Infinity }))
  bad(d => Object.assign(d.days[0].metrics.flat, { value: -1 }))
  bad(d => Object.assign(d.days[0].metrics.volume_spike, { reason: null }))
  bad(d => Object.assign(d.days[0], { missing_fields: [] }))
  bad(d => Object.assign(d.days[0], { available_at: '2026-09-16T00:00:00Z' }))
})
it('unknown market parameter retains the original default CN behavior', async () => {
  await render('/regime?market=unexpected')
  expect(active().dataset.environmentMarket).toBe('CN')
  expect(state.queries).toContainEqual(['regime-history', '1y'])
})
