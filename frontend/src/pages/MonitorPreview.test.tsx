// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Monitor } from '@/custom/monitor/extension'
import { MonitorPreview } from '@/custom/damon/monitor-preview/Presentation'
import { loadMonitorPreview } from '../../tests/fixtures/monitor_preview'
import { validateMonitorPreview, type MonitorPreviewData } from '@/custom/damon/monitor-preview/contract'

const state = vi.hoisted(() => ({ queries: [] as unknown[][], mutate: vi.fn(), apiCall: vi.fn(), prefs: vi.fn(), quote: vi.fn(), seen: vi.fn(), leave: vi.fn(), reset: vi.fn() }))
vi.mock('@tanstack/react-query', async original => ({ ...await original<typeof import('@tanstack/react-query')>(),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({ mutate: state.mutate, isPending: false }),
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => { state.queries.push(queryKey); return { data: { alerts: [], total: 0, rules: [], items: [], groups: [], signals: [], symbols: [] }, isLoading: false, refetch: vi.fn() } },
}))
vi.mock('@/lib/api', async original => { const actual = await original<typeof import('@/lib/api')>(); return { ...actual, api: Object.fromEntries(Object.keys(actual.api).map(key => [key, (...args: unknown[]) => state.apiCall(key, args)])) } })
vi.mock('@/lib/useSharedQueries', () => ({ usePreferences: () => { state.prefs(); return { data: {} } }, useQuoteStatus: () => { state.quote(); return { data: { mode: 'none', is_trading_hours: false } } } }))
vi.mock('@/lib/monitorBadge', () => ({ markSeen: state.seen, leaveMonitorPage: state.leave, resetBadge: state.reset }))
vi.mock('@/components/monitor/RuleEditor', () => ({ RuleEditor: ({ preset }: { preset?: { type?: string } }) => <div data-editor>{preset?.type ?? 'CN new rule'}</div> }))
vi.mock('@/components/StockPreviewDialog', () => ({ StockPreviewDialog: () => null }))
vi.mock('@/components/DimensionMembersDialog', () => ({ DimensionMembersDialog: () => null }))
let host: HTMLDivElement, root: Root
beforeEach(() => { Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); state.queries = []; vi.clearAllMocks(); host = document.createElement('div'); document.body.append(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })
async function render(path = '/monitor', element = <Monitor />) {
  function Navigation() { const location = useLocation(), navigate = useNavigate(); return <><output data-location>{location.search}</output><button data-back onClick={() => navigate(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Navigation /></MemoryRouter>))
}
function active() { return host.querySelector<HTMLElement>('[data-monitor-market]:not([hidden])')! }
async function market(index: number) { await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[index].click()) }
async function select(label: string, value: string) { const input = active().querySelector<HTMLSelectElement>(`[aria-label="${label}"]`)!; await act(async () => { input.value = value; input.dispatchEvent(new Event('change', { bubbles: true })) }) }
async function search(value: string) { const input = active().querySelector<HTMLInputElement>('input')!; await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })) }) }
it('CN keeps original real queries, source filter, unavailable banner and new-rule permission', async () => {
  await render('/monitor?keep=1')
  const cn = active()
  expect(cn.querySelector('h1')?.textContent).toBe('监控中心')
  expect(state.queries).toContainEqual(['monitor-rules'])
  expect(state.queries).toContainEqual(['alerts', '', 'ext_gn_ths.所属概念,ext_hy_ths.所属同花顺行业'])
  expect(cn.textContent).toContain('实时行情当前不可用')
  await act(async () => [...cn.querySelectorAll('button')].find(b => b.textContent === '价格/涨跌')!.click())
  expect(state.queries).toContainEqual(['alerts', 'price', 'ext_gn_ths.所属概念,ext_hy_ths.所属同花顺行业'])
  await act(async () => cn.querySelector<HTMLButtonElement>('[title="新建规则"]')!.click())
  expect(cn.querySelector('[data-editor]')?.textContent).toBe('CN new rule')
  expect(state.seen).toHaveBeenCalledTimes(1)
  await market(1)
  expect(state.leave).toHaveBeenCalledTimes(1)
  expect(active().querySelector('[data-editor]')).toBeNull()
  await market(0)
  expect(active()).toBe(cn); expect(cn.querySelector('[data-editor]')).not.toBeNull()
  expect(state.seen).toHaveBeenCalledTimes(2)
  expect([...cn.querySelectorAll('button')].find(b => b.textContent === '价格/涨跌')?.className).toContain('bg-accent')
  expect(state.apiCall).not.toHaveBeenCalled(); expect(state.mutate).not.toHaveBeenCalled()
})
it.each(['HK', 'US'] as const)('direct %s uses no real queries, preferences, quote health, APIs, badge writes or storage', async m => {
  const fetch = vi.fn(), storage = vi.spyOn(Storage.prototype, 'setItem'); vi.stubGlobal('fetch', fetch)
  await render(`/monitor?market=${m}&new=abnormal`)
  for (const text of ['演示数据｜非生产状态｜不构成真实告警或投资信号', '真实 Worker 状态：未观测', '真实服务健康：未观测', 'synthetic-fixture', '2026-09-16', '2026-09-17T02:00:00Z', 'PREVIEW']) expect(active().textContent).toContain(text)
  expect(active().textContent).not.toMatch(/RUNNING|HEALTHY|实时行情当前不可用/)
  expect(active().textContent).toContain(m === 'HK' ? '0700.HK' : 'AAPL.US')
  expect(active().textContent).not.toContain(m === 'HK' ? 'AAPL.US' : '0700.HK')
  expect(host.querySelector('[data-monitor-market="CN"]')).toBeNull()
  expect(host.querySelector('[data-location]')?.textContent).toContain('new=abnormal')
  await act(async () => active().querySelectorAll<HTMLButtonElement>('button:disabled').forEach(b => b.click()))
  expect(state.queries).toHaveLength(0)
  for (const spy of [state.prefs, state.quote, state.apiCall, state.mutate, state.seen, state.leave, state.reset, fetch, storage]) expect(spy).not.toHaveBeenCalled()
})
it('CN abnormal deep-link still opens the original editor and consumes its parameter', async () => {
  await render('/monitor?new=abnormal')
  expect(active().querySelector('[data-editor]')?.textContent).toBe('abnormal')
  expect(host.querySelector('[data-location]')?.textContent).toBe('')
})
it.each(['HK', 'US'] as const)('%s overview counts match its fixture tasks, including known zero versus unknown', async m => {
  await render(`/monitor?market=${m}`)
  const data = loadMonitorPreview(m)
  for (const key of ['total', 'NORMAL', 'WARNING', 'ERROR', 'UNAVAILABLE'] as const) expect(active().querySelector(`[data-monitor-count="${key}"] .font-mono`)?.textContent).toBe(String(data.counts[key].value))
  expect(active().querySelectorAll('tbody tr')).toHaveLength(4)
  expect(active().querySelector('tbody tr [data-monitor-field="source"]')?.textContent).toContain(`fixture:monitor:${m}:task:0:v1`)
  expect(active().querySelectorAll('article')).toHaveLength(m === 'HK' ? 2 : 3)
  if (m === 'US') expect(active().textContent).toContain('US 样稿未提供最近更新时间')
})
it('search, severity, task status and sorting operate only on the local samples', async () => {
  await render('/monitor?market=HK')
  await search('0700.HK')
  expect(active().querySelectorAll('tbody tr')).toHaveLength(1); expect(active().querySelectorAll('article')).toHaveLength(1)
  await search(''); await select('演示严重程度', 'WARN')
  expect(active().querySelector('tbody')?.textContent).toContain('9988.HK')
  expect(active().querySelectorAll('article')).toHaveLength(1)
  await select('演示严重程度', 'ALL'); await select('演示任务状态', 'UNAVAILABLE')
  expect(active().querySelectorAll('tbody tr')).toHaveLength(1); expect(active().querySelector('tbody')?.textContent).toContain('3690.HK')
  await select('演示任务状态', 'ALL')
  const header = [...active().querySelectorAll('th')].find(th => th.textContent?.startsWith('状态'))!
  await act(async () => header.click())
  expect(active().querySelector('tbody tr')?.textContent).toContain('HSI')
  const timeHeader = [...active().querySelectorAll('th')].find(th => th.textContent?.startsWith('检查时间'))!
  await act(async () => timeHeader.click())
  expect([...active().querySelectorAll('tbody tr')].at(-1)?.textContent).toContain('3690.HK')
  expect(state.queries).toHaveLength(0)
})
it('task and alert details expose synthetic conditions, evidence, null reasons and blockers', async () => {
  await render('/monitor?market=US')
  await act(async () => active().querySelector<HTMLButtonElement>('[data-task-id="fixture-monitor-US-3"]')!.click())
  const detail = active().querySelector('[aria-label="监控样本详情"]')!
  for (const text of ['MSFT.US', '样稿部分缺失', '—（样稿未提供）', '未编写严重程度', 'fixture:monitor:US:task:3:v1', 'PIT/vintage 未闭合', '不执行规则']) expect(detail.textContent).toContain(text)
  const alert = [...active().querySelectorAll('article')].at(-1)!
  await act(async () => alert.querySelector<HTMLElement>('summary')!.click())
  expect(alert.querySelector('details')?.open).toBe(true)
  for (const text of ['告警状态未知', '不推断为未确认', '固定发生时间', '合成触发说明', 'fixture:monitor:US:alert:2:v1']) expect(alert.textContent).toContain(text)
  expect(state.mutate).not.toHaveBeenCalled(); expect(state.apiCall).not.toHaveBeenCalled()
})
it('market navigation/back retains independent filters and selected task without cross-market samples', async () => {
  await render('/monitor?market=HK&keep=fixture')
  await search('3690.HK')
  await market(2)
  expect(active().querySelector<HTMLInputElement>('input')?.value).toBe(''); expect(active().querySelectorAll('tbody tr')).toHaveLength(4)
  await select('演示严重程度', 'UNKNOWN')
  expect(active().querySelectorAll('tbody tr')).toHaveLength(1)
  await act(async () => host.querySelector<HTMLButtonElement>('[data-back]')!.click())
  expect(active().dataset.monitorMarket).toBe('HK'); expect(active().querySelector<HTMLInputElement>('input')?.value).toBe('3690.HK')
  expect(active().textContent).not.toContain('MSFT.US'); expect(host.querySelector('[data-location]')?.textContent).toContain('keep=fixture')
})
it('empty filtered lists, loading, error and empty store never fall back to real monitoring', async () => {
  await render('/monitor?market=HK'); await search('not-a-sample')
  expect(active().textContent).toContain('暂无匹配的监控样本'); expect(active().textContent).toContain('暂无匹配的合成告警')
  const empty = loadMonitorPreview('HK'); Object.assign(empty, { tasks: [], alerts: [], counts: Object.fromEntries(Object.keys(empty.counts).map(key => [key, { value: 0, reason: null }])) })
  for (const [value, text] of [[{ kind: 'loading' }, '加载中'], [{ kind: 'error' }, '加载失败'], [{ kind: 'ready', data: empty }, '暂无监控演示样本']] as const) {
    await render('/monitor', <MonitorPreview market="HK" state={value} />); expect(host.textContent).toContain(text)
  }
  expect(state.queries).toHaveLength(0); expect(state.apiCall).not.toHaveBeenCalled()
})
it('unknown count remains null with reason while dates/time and fixture objects remain deterministic', async () => {
  const data = loadMonitorPreview('HK'); Object.assign(data.counts.NORMAL, { value: null, reason: '样稿计数未提供，不补零' })
  await render('/monitor', <MonitorPreview market="HK" state={{ kind: 'ready', data }} />)
  expect(host.querySelector('[data-monitor-count="NORMAL"]')?.textContent).toContain('—样稿计数未提供')
  vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z'))
  const a = loadMonitorPreview('US'), b = loadMonitorPreview('US')
  expect(a).toEqual(b); expect(a.tasks[0]).not.toBe(b.tasks[0]); expect(a.counts.total).not.toBe(b.counts.total)
  expect(a.trading_date).toBe('2026-09-16'); expect(a.tasks.at(-1)?.checked_at).toBeNull()
})
it('rejects production flags, mixed identities, wrong statistics, invalid times and missing reasons', () => {
  const bad = (edit: (d: MonitorPreviewData) => unknown) => { const data = structuredClone(loadMonitorPreview('US')); edit(data); expect(() => validateMonitorPreview(data)).toThrow() }
  bad(d => Object.assign(d, { is_production: true }))
  bad(d => Object.assign(d.tasks[0], { market: 'HK' }))
  bad(d => Object.assign(d.counts.ERROR, { value: Infinity }))
  bad(d => Object.assign(d.counts.total, { value: 99 }))
  bad(d => Object.assign(d.tasks[0], { checked_at: '2026-09-17 01:00:00' }))
  bad(d => Object.assign(d.tasks[3], { reasons: [] }))
  bad(d => Object.assign(d.alerts[2], { reasons: [] }))
  bad(d => Object.assign(d.tasks[0], { sample_state: 'RUNNING' }))
})
