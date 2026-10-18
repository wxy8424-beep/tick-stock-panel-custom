// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Signals } from '@/custom/signals/extension'
import { SignalPreview } from '@/custom/damon/signal-preview/Presentation'
import { validateSignalPreview, type SignalPreviewData } from '@/custom/damon/signal-preview/contract'
import { loadSignalPreview } from '../../tests/fixtures/signal_preview'

const state = vi.hoisted(() => ({ queries: [] as unknown[][], invalidate: vi.fn(), api: vi.fn(), scroll: vi.fn() }))
const cnSignal = { id: 'cn_control', name: 'CN 条件对照', kind: 'entry', enabled: true, timeframe: 'daily', conditions: [{ left: 'close', op: '>', right: 'field:ma20', leftDays: 1, rightDays: 0 }] }
const options = { fields: [{ key: 'close', label: '收盘价' }, { key: 'ma20', label: 'MA20' }], operators: ['>', '>=', '<', '<=', '==', '!='], maxDays: 60 }
vi.mock('@tanstack/react-query', async original => ({
  ...await original<typeof import('@tanstack/react-query')>(),
  useQueryClient: () => ({ invalidateQueries: state.invalidate }),
  useQuery: ({ queryKey, queryFn, enabled }: { queryKey: unknown[]; queryFn: () => unknown; enabled?: boolean }) => {
    state.queries.push(queryKey)
    if (enabled !== false) queryFn()
    return { isLoading: false, data: { signals: [cnSignal], ...options } }
  },
  useMutation: (o: { mutationFn: (v: unknown) => unknown; onSuccess?: (v: unknown) => void; onError?: (e: unknown) => void }) => ({
    isPending: false, mutate: (v: unknown) => { Promise.resolve().then(() => o.mutationFn(v)).then(o.onSuccess).catch(o.onError) },
  }),
}))
vi.mock('@/lib/api', async original => {
  const actual = await original<typeof import('@/lib/api')>()
  return { ...actual, api: Object.fromEntries(Object.keys(actual.api).map(k => [k, (...args: unknown[]) => state.api(k, ...args)])) }
})
let host: HTMLDivElement, root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.clearAllMocks(); state.queries = []
  state.api.mockImplementation(async (name, signal) => name === 'strategyAiStatus' ? { configured: false } : { signal })
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: state.scroll })
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => { cb(0); return 1 })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })
async function render(path = '/signals', element = <Signals />) {
  function Nav() { const loc = useLocation(), nav = useNavigate(); return <><output data-location>{loc.search}</output><button data-back onClick={() => nav(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Nav /></MemoryRouter>))
}
const active = () => host.querySelector<HTMLElement>('[data-signal-market]')!
async function click(selector: string) { await act(async () => host.querySelector<HTMLButtonElement>(selector)!.click()) }
async function button(label: string) { await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent?.trim() === label)!.click()) }
async function market(i: number) { await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[i].click()) }
async function input(selector: string, value: string) {
  await act(async () => { const el = host.querySelector<HTMLInputElement>(selector)!; Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, value); el.dispatchEvent(new Event('input', { bubbles: true })) })
}
async function filter(label: string, value: string) {
  await act(async () => { const el = host.querySelector<HTMLSelectElement>(`[aria-label="${label}"]`)!; el.value = value; el.dispatchEvent(new Event('change', { bubbles: true })) })
}
it('CN retains actual list/options, highlight, toggle and two-step deletion', async () => {
  await render('/signals?highlight=signals&keep=1')
  expect(active().dataset.signalMarket).toBe('CN'); expect(host.textContent).toContain('CN 条件对照')
  expect(state.scroll).toHaveBeenCalled(); expect(host.querySelector('#signals')).not.toBeNull()
  expect(state.api).toHaveBeenCalledWith('customSignalsList'); expect(state.api).toHaveBeenCalledWith('customSignalsOptions')
  expect(host.textContent).toContain('收盘价(前1日)')
  await click('button[title="停用"]')
  expect(state.api).toHaveBeenCalledWith('customSignalSave', { ...cnSignal, enabled: false })
  await click('button[title="删除"]'); expect(state.api).not.toHaveBeenCalledWith('customSignalDelete', expect.anything())
  await click('button[title="再次点击确认删除"]'); expect(state.api).toHaveBeenCalledWith('customSignalDelete', 'cn_control')
})
it('CN actual edit dialog saves unchanged condition semantics and leaving CN unmounts it', async () => {
  await render('/signals'); await click('button[title="编辑"]')
  expect(host.querySelector('[role="dialog"]')).not.toBeNull()
  expect(host.querySelector<HTMLInputElement>('input[placeholder="如 low_touches_ma5"]')!.disabled).toBe(true)
  await input('input[placeholder="如 跌至MA5"]', 'CN 修改名称')
  await button('保存')
  expect(state.api).toHaveBeenCalledWith('customSignalSave', { ...cnSignal, name: 'CN 修改名称' })
  expect(state.invalidate).toHaveBeenCalled()
  await button('新建信号'); await market(1)
  expect(host.querySelector('[role="dialog"]')).toBeNull(); expect(host.textContent).not.toContain('CN 条件对照')
})
it.each(['HK', 'US'] as const)('%s ignores real URL identities and never calls business APIs, storage or notifications', async m => {
  const fetch = vi.fn(), notification = vi.fn(), eventSource = vi.fn(), write = vi.spyOn(Storage.prototype, 'setItem'), remove = vi.spyOn(Storage.prototype, 'removeItem')
  vi.stubGlobal('fetch', fetch); vi.stubGlobal('Notification', notification); vi.stubGlobal('EventSource', eventSource)
  await render(`/signals?market=${m}&highlight=signals&id=cn_control&edit=real&run=real&keep=1`)
  expect(active().dataset.signalMarket).toBe(m); expect(host.textContent).toContain(`${m} 信号定义 · Preview`)
  expect(host.querySelectorAll('[data-signal-id]')).toHaveLength(4); expect(host.textContent).not.toContain(m === 'HK' ? 'fixture-signal-US' : 'fixture-signal-HK')
  for (const text of ['演示信号定义｜合成数据｜非生产配置', 'synthetic-fixture', '2026-09-16', '2026-09-17T09:00:00Z', '生产执行：BLOCKED']) expect(host.textContent).toContain(text)
  expect(host.querySelectorAll('button:disabled')).toHaveLength(7)
  await act(async () => host.querySelectorAll<HTMLButtonElement>('button:disabled').forEach(b => b.click()))
  expect(state.queries).toHaveLength(0)
  for (const spy of [state.api, fetch, notification, eventSource, write, remove]) expect(spy).not.toHaveBeenCalled()
  expect(host.querySelector('[role="dialog"]')).toBeNull(); expect(host.querySelector('#signals')).toBeNull()
})
it('search, direction/timeframe/quality filtering, sorting and null detail reasons work', async () => {
  await render('/signals?market=HK')
  await input('[aria-label="搜索信号样稿"]', 'fixture-signal-HK-1'); expect(host.querySelectorAll('[data-signal-id]')).toHaveLength(1)
  await click('[data-signal-id]'); expect(host.querySelector('[aria-label="信号样稿详情"]')!.textContent).toContain('没有已确认的演示左字段')
  await input('[aria-label="搜索信号样稿"]', '')
  await filter('样稿方向', 'both'); expect(host.querySelectorAll('[data-signal-id]')).toHaveLength(1)
  await filter('样稿方向', 'ALL'); await filter('样稿时间框架', 'intraday'); expect(host.querySelectorAll('[data-signal-id]')).toHaveLength(1)
  await filter('样稿时间框架', 'ALL'); await filter('样稿定义质量', 'BLOCKED'); expect(host.querySelectorAll('[data-signal-id]')).toHaveLength(1)
  await filter('样稿定义质量', 'ALL')
  const names = () => [...host.querySelectorAll('[data-signal-id]')].map(b => b.textContent)
  await click('[aria-label="按合成定义名称 / 标识排序"]'); const asc = names()
  expect(host.querySelector('th')!.getAttribute('aria-sort')).toBe('ascending')
  await click('[aria-label="按合成定义名称 / 标识排序"]'); expect(names()).toEqual([...asc].reverse())
  await click('[data-signal-id="fixture-signal-HK-2"]')
  expect(host.textContent).toContain('未定义此样稿的条件')
  for (const key of ['production_version', 'last_trigger_at', 'trigger_count', 'production_binding']) expect(host.querySelector(`[data-signal-missing="${key}"]`)!.textContent).toContain('— ·')
  await input('[aria-label="搜索信号样稿"]', 'no such sample'); expect(host.textContent).toContain('暂无匹配的信号样稿')
})
it('market changes and browser back reset local state; direct fresh mount supports refresh', async () => {
  await render('/signals?market=HK&keep=1'); await input('[aria-label="搜索信号样稿"]', 'missing'); await filter('样稿方向', 'both')
  await market(2); expect(host.querySelector<HTMLInputElement>('input')!.value).toBe(''); expect(host.querySelectorAll('[data-signal-id]')).toHaveLength(4)
  await click('[data-signal-id="fixture-signal-US-2"]'); await click('[data-back]')
  expect(active().dataset.signalMarket).toBe('HK'); expect(host.querySelector<HTMLInputElement>('input')!.value).toBe('')
  expect(host.querySelector('[aria-label="信号样稿详情"]')!.textContent).toContain('fixture-signal-HK-0')
  expect(host.querySelector('[data-location]')!.textContent).toContain('keep=1')
  await act(async () => root.unmount()); root = createRoot(host); await render('/signals?market=US')
  expect(active().dataset.signalMarket).toBe('US'); expect(host.querySelectorAll('[data-signal-id]')).toHaveLength(4)
})
it('loading/error/empty/invalid-market states keep disclaimer and disabled actions without fallback', async () => {
  for (const state of [{ kind: 'loading' }, { kind: 'error' }, { kind: 'ready', data: { ...loadSignalPreview('HK'), rows: [] } }, { kind: 'ready', data: loadSignalPreview('US') }] as const) {
    await render('/signals', <SignalPreview market="HK" state={state} />)
    expect(host.textContent).toContain('演示信号定义｜合成数据'); expect(host.querySelectorAll('button:disabled')).toHaveLength(7)
    expect(host.querySelector('[data-signal-id]')).toBeNull()
  }
  expect(state.api).not.toHaveBeenCalled(); expect(state.queries).toHaveLength(0)
})
it('layout clearance is Preview-local, fixed fixture dates/identities do not depend on current time', async () => {
  const expected = loadSignalPreview('US'); vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z'))
  expect(loadSignalPreview('US')).toEqual(expected); expect(loadSignalPreview('US').rows).not.toBe(expected.rows); vi.useRealTimers()
  await render('/signals?market=HK')
  expect(host.querySelector('header')!.className).toContain('pl-14 md:pl-5')
  await market(0); expect(host.querySelector('header')!.className).not.toContain('pl-14')
})
it.each(['HK', 'US'] as const)('valid %s fixture has separate AND-only identity and blocked execution', m => {
  expect(validateSignalPreview(loadSignalPreview(m)).rows).toHaveLength(4)
  expect(loadSignalPreview(m).rows.every(r => r.logic === 'AND' && r.execution_status === 'BLOCKED')).toBe(true)
})
it.each(['HK', 'US'] as const)('%s contract rejects opposite-market membership', m => {
  const d = loadSignalPreview(m); Object.assign(d.rows[0], { market: m === 'HK' ? 'US' : 'HK' })
  expect(() => validateSignalPreview(d)).toThrow()
})
const mutations: [string, (d: SignalPreviewData) => void][] = [
  ['mixed market', d => { Object.assign(d.rows[0], { market: 'US' }) }],
  ['production id', d => { Object.assign(d.rows[0], { id: 'csg_real' }) }],
  ['bad source', d => { Object.assign(d.rows[0], { source: 'provider' }) }],
  ['bad evidence', d => { Object.assign(d.rows[0], { evidence: 'fixture:signal:US:0:v1' }) }],
  ['missing reason', d => { delete d.rows[0].missing_reasons.trigger_count }],
  ['ready execution', d => { Object.assign(d.rows[0], { execution_status: 'READY' }) }],
  ['OR', d => { Object.assign(d.rows[0], { logic: 'OR' }) }],
  ['unknown condition property', d => { Object.assign(d.rows[0].conditions![0], { expression: 'code()' }) }],
  ['unsupported field', d => { Object.assign(d.rows[0].conditions![0], { left: 'real_registry_factor' }) }],
  ['unsupported operator', d => { Object.assign(d.rows[0].conditions![0], { op: 'eval' }) }],
  ['bad parameter', d => { Object.assign(d.rows[0].conditions![0], { left_sessions: '0' }) }],
  ['NaN', d => { Object.assign(d.rows[0].conditions![0], { right: { kind: 'number', value: NaN } }) }],
  ['Infinity', d => { Object.assign(d.rows[0].conditions![0], { right: { kind: 'number', value: Infinity } }) }],
  ['bad right type', d => { Object.assign(d.rows[0].conditions![0], { right: { kind: 'number', value: '20' } }) }],
  ['missing field reason', d => { delete d.rows[1].conditions![0].missing_reasons.left }],
  ['production timestamp', d => { Object.assign(d.rows[0], { last_trigger_at: '2026-09-16T01:00:00Z' }) }],
  ['production flag', d => { Object.assign(d.rows[0], { is_production: true }) }],
  ['duplicate id', d => { Object.assign(d.rows[1], { id: d.rows[0].id }) }],
  ['invalid date', d => { Object.assign(d, { trading_date: '2026-02-31' }) }],
  ['extra execution field', d => { Object.assign(d.rows[0], { enabled: true }) }],
  ['null rules claiming ready', d => { Object.assign(d.rows[0], { conditions: null }) }],
  ['empty rules', d => { Object.assign(d.rows[0], { conditions: [] }) }],
  ['incomplete ready condition', d => { Object.assign(d.rows[0].conditions![0], { left: null }) }],
  ['negative session offset', d => { Object.assign(d.rows[0].conditions![0], { left_sessions: -1 }) }],
]
it.each(mutations)('contract rejects %s', (_name, mutate) => { const d = loadSignalPreview('HK'); mutate(d); expect(() => validateSignalPreview(d)).toThrow() })
