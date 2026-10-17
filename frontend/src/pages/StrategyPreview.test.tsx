// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Screener } from './Screener'
import { StrategyPreview } from '@/custom/damon/strategy-preview/Presentation'
import { validateStrategyPreview } from '@/custom/damon/strategy-preview/contract'
import { loadStrategyPreview } from '../../tests/fixtures/strategy_preview'
const state = vi.hoisted(() => ({ queries: [] as unknown[][], mutate: vi.fn(), api: vi.fn(async (_method: string, _args: unknown[]) => ({})), columns: vi.fn() }))
vi.mock('@tanstack/react-query', async original => ({ ...await original<typeof import('@tanstack/react-query')>(), useQueryClient: () => ({ invalidateQueries: vi.fn(), fetchQuery: vi.fn() }), useMutation: () => ({ mutate: state.mutate, isPending: false }), useQuery: ({ queryKey }: { queryKey: unknown[] }) => { state.queries.push(queryKey); return { data: undefined, isLoading: false, refetch: vi.fn() } } }))
vi.mock('@/lib/api', async original => { const actual = await original<typeof import('@/lib/api')>(); return { ...actual, api: Object.fromEntries(Object.keys(actual.api).map(k => [k, (...args: unknown[]) => state.api(k, args)])) } })
vi.mock('@/lib/screener-columns', async original => { const actual = await original<typeof import('@/lib/screener-columns')>(); return { ...actual, loadScreenerColumnConfig: async () => { state.columns(); return actual.SCREENER_BUILTIN_COLUMNS }, saveScreenerColumnConfig: vi.fn() } })
let host: HTMLDivElement, root: Root
beforeEach(() => { Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.clearAllMocks(); state.queries = []; localStorage.clear(); host = document.createElement('div'); document.body.append(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })
async function render(path = '/screener', element = <Screener />) {
  function Nav() { const l = useLocation(), navigate = useNavigate(); return <><output data-location>{l.search}</output><button data-back onClick={() => navigate(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Nav /></MemoryRouter>))
}
function active() { return host.querySelector<HTMLElement>('[data-strategy-market]')! }
async function market(i: number) { await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[i].click()) }
async function search(v: string) { const el = active().querySelector<HTMLInputElement>('input[aria-label="搜索策略样稿"]')!; await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })) }) }
async function filter(label: string, v: string) { const el = active().querySelector<HTMLSelectElement>(`select[aria-label="${label}"]`)!; await act(async () => { el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })) }) }
async function pick(i: number) { await act(async () => active().querySelector<HTMLButtonElement>(`[data-strategy-id="fixture-strategy-${active().dataset.strategyMarket}-${i}"]`)!.click()) }
it('CN retains default strategy queries, empty pool, reload mutation, asset selection and original toolbar', async () => {
  await render(); expect(active().querySelector('h1')?.textContent).toBe('策略'); expect(active().textContent).toContain('策略池为空')
  expect(state.queries).toContainEqual(['screener-strategies', 'all', '1d', 'all']); expect(state.columns).toHaveBeenCalled()
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent?.trim() === '重载')!.click()); expect(state.mutate).toHaveBeenCalledTimes(1)
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent?.trim() === 'ETF')!.click()); expect(active().textContent).toContain('创建策略 · AI')
  await market(1); expect(active().textContent).not.toContain('策略池为空'); await market(0); expect(active().querySelector('h1')?.textContent).toBe('策略')
})
it.each(['HK', 'US'] as const)('direct %s has isolated metadata and no real strategy/signal/backtest/trade/storage paths', async m => {
  const fetch = vi.fn(), write = vi.spyOn(Storage.prototype, 'setItem'), remove = vi.spyOn(Storage.prototype, 'removeItem'), notify = vi.fn(); vi.stubGlobal('fetch', fetch); vi.stubGlobal('Notification', notify)
  await render(`/screener?market=${m}`)
  for (const t of ['演示策略｜非生产策略配置｜不产生真实交易信号｜不构成投资建议', 'synthetic-fixture', 'PREVIEW', '2026-09-16', '2026-09-17T08:00:00Z', `${m} 趋势观察样稿`, m === 'HK' ? '0700.HK' : 'AAPL.US']) expect(active().textContent).toContain(t)
  expect(active().textContent).not.toContain(m === 'HK' ? 'AAPL.US' : '0700.HK'); expect(active().querySelectorAll('[data-strategy-id]')).toHaveLength(4)
  await act(async () => active().querySelectorAll<HTMLButtonElement>('button:disabled').forEach(b => b.click()))
  expect(state.queries).toHaveLength(0); for (const spy of [state.mutate, state.api, state.columns, fetch, write, remove, notify]) expect(spy).not.toHaveBeenCalled()
})
it('search, type, definition status and version filters work without changing validation eligibility', async () => {
  await render('/screener?market=HK'); await search('fixture-strategy-HK-1'); expect(active().querySelectorAll('[data-strategy-id]')).toHaveLength(1)
  await search(''); await filter('演示策略类型', 'FILTER_SAMPLE'); expect(active().querySelector('tbody')?.textContent).toContain('过滤规则样稿')
  await filter('演示定义状态', 'READY'); expect(active().textContent).toContain('暂无匹配的策略样稿')
  await filter('演示策略类型', 'ALL'); expect(active().querySelectorAll('[data-strategy-id]')).toHaveLength(1)
  await filter('演示定义状态', 'ALL'); await filter('演示策略版本', 'preview-v2'); expect(active().querySelector('tbody')?.textContent).toContain('量能规则阻塞样稿')
  expect(active().querySelector('[aria-label="策略样稿详情"]')?.textContent).toContain('生产验证：BLOCKED')
})
it('name, version and definition-state sorting works in both directions and preserves row identity', async () => {
  await render('/screener?market=US')
  for (const label of ['策略名称 / 标识', '样稿版本', '定义状态']) {
    const th = [...active().querySelectorAll('th')].find(h => h.textContent?.startsWith(label))!
    await act(async () => th.click()); const asc = [...active().querySelectorAll('[data-strategy-id]')].map(r => r.getAttribute('data-strategy-id'))
    await act(async () => th.click()); const desc = [...active().querySelectorAll('[data-strategy-id]')].map(r => r.getAttribute('data-strategy-id'))
    expect(asc[0]).not.toBe(desc[0]); expect(new Set(asc)).toEqual(new Set(desc)); expect(desc).toHaveLength(4)
  }
})
it('overview and detail separate display, definition, validation and unknown runtime; missing is never zero', async () => {
  await render('/screener?market=HK'); const overview = active().querySelector('[aria-label="策略样稿概览"]')!
  for (const s of ['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED']) expect(overview.querySelector(`[data-strategy-count="${s}"]`)?.textContent).toContain('1 项定义样稿')
  const detail = active().querySelector('[aria-label="策略样稿详情"]')!
  for (const t of ['结构完整样稿', '生产验证：BLOCKED', '真实运行状态：—（未观测）', '真实信号数：—（未知，不填0）', 'fixture:strategy:HK:0:config:v1', 'preview-params-v1', '未绑定，禁止自动选择']) expect(detail.textContent).toContain(t)
  expect(detail.textContent).not.toContain('RUNNING'); expect(loadStrategyPreview('HK').rows.every(r => r.runtime_status === null && r.last_run_at === null && r.signal_count === null)).toBe(true)
})
it('entry/exit groups show existing condition shapes, offsets and combination logic without evaluation', async () => {
  await render('/screener?market=US'); const d = active().querySelector('[aria-label="策略样稿详情"]')!
  for (const t of ['组合逻辑：AND', '组合逻辑：OR', 'field:ma20', 'change_pct', '左偏移', '仅元数据展示，不执行条件', '小数制']) expect(d.textContent).toContain(t)
  await pick(1); expect(d.textContent).toContain('退出规则未定义，保留 null'); await pick(2); expect(d.textContent).toContain('入场与退出规则均未定义')
  expect(loadStrategyPreview('US').rows[2].entry).toBeNull()
})
it('parameters disclose unit/version/source and unknown defaults/bounds; risk metadata never claims enforcement', async () => {
  await render('/screener?market=US'); const p = active().querySelector('[data-param-id="window"]')!
  for (const t of ['20', 'completed sessions', '正式默认值：—', '允许范围：—', 'preview-params-v1', 'StrategyParamDef', 'synthetic-fixture']) expect(p.textContent).toContain(t)
  const stop = active().querySelector('[data-risk-key="stop_loss"]')!
  expect(stop.textContent).toContain('0.08 = 8%'); expect(stop.textContent).toContain('强制执行：否')
  for (const key of ['symbol_position_cap', 'total_position_cap', 'max_drawdown', 'daily_risk_budget', 'trade_frequency', 'trading_cost']) { const r = active().querySelector(`[data-risk-key="${key}"]`)!; expect(r.textContent).toContain('UNAVAILABLE'); expect(r.textContent).toContain('—'); expect(r.textContent).toContain('没有本项 HK/US 已冻结执行契约') }
})
it('dependencies retain source blockers and absent factor/backtest/account evidence', async () => {
  await render('/screener?market=HK'); const d = active().querySelector('[aria-label="策略依赖样稿"]')!
  for (const t of ['split-only 未闭合', 'Volume/VR20、PIT/vintage BLOCKED', 'finality PARTIAL', '公司行动 UNKNOWN', '真实 membership', '未选择 Factor', '无实际回测结果', '未绑定真实账户、Worker', 'longbridge-historical-vendor-evidence-closure-v1.md']) expect(d.textContent).toContain(t)
  expect(d.textContent).not.toContain('READY'); await pick(3); expect(active().textContent).toContain('条件保留 null')
})
it('market navigation/back resets selection, filters and detail while preserving unrelated URL parameters', async () => {
  await render('/screener?market=HK&keep=1'); await pick(1); await search('过滤规则'); await filter('演示策略类型', 'FILTER_SAMPLE')
  await market(2); expect(active().querySelector<HTMLInputElement>('input')?.value).toBe(''); expect(active().querySelectorAll('[data-strategy-id]')).toHaveLength(4); expect(active().textContent).not.toContain('fixture-strategy-HK')
  await pick(3); await act(async () => host.querySelector<HTMLButtonElement>('[data-back]')!.click())
  expect(active().dataset.strategyMarket).toBe('HK'); expect(active().querySelector<HTMLInputElement>('input')?.value).toBe(''); expect(active().querySelector<HTMLSelectElement>('select')?.value).toBe('ALL')
  expect(active().querySelector('[aria-label="策略样稿详情"]')?.textContent).toContain('fixture-strategy-HK-0'); expect(host.querySelector('[data-location]')?.textContent).toContain('keep=1')
})
it('fixture identity/time is deterministic; mixed markets, false runtime, enforcement and missing-ready values reject', () => {
  const d = loadStrategyPreview('US'); vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z')); expect(loadStrategyPreview('US')).toEqual(d); vi.useRealTimers(); expect(loadStrategyPreview('US').rows).not.toBe(d.rows)
  type D = ReturnType<typeof loadStrategyPreview>
  for (const mutate of [(x: D) => { x.rows[0].market = 'HK' }, (x: D) => { Object.assign(x.rows[0], { runtime_status: 'RUNNING' }) }, (x: D) => { Object.assign(x.rows[0].risks[0], { enforced: true }) }, (x: D) => { x.rows[0].parameters[0].value = null }, (x: D) => { x.rows[0].parameters[0].value = Infinity }, (x: D) => { x.rows[0].entry = null }]) { const copy = loadStrategyPreview('US'); mutate(copy); expect(() => validateStrategyPreview(copy)).toThrow() }
})
it('loading/error/empty fixtures retain the disclaimer and do not fall back to production', async () => {
  const empty = loadStrategyPreview('HK'); empty.rows = []
  for (const [s, t] of [[{ kind: 'loading' }, '加载中'], [{ kind: 'error' }, '加载失败'], [{ kind: 'ready', data: empty }, '暂无匹配的策略样稿']] as const) { await render('/screener', <StrategyPreview market="HK" state={s} />); expect(host.textContent).toContain(t); expect(host.textContent).toContain('非生产策略配置'); expect(host.querySelector('tbody')).toBeNull() }
  expect(state.queries).toHaveLength(0); expect(state.api).not.toHaveBeenCalled()
})
