// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Factors } from './Factors'
import { FactorPreview } from '@/custom/damon/factor-preview/Presentation'
import { validateFactorPreview, type FactorPreviewData } from '@/custom/damon/factor-preview/contract'
import { loadFactorPreview } from '../../tests/fixtures/factor_preview'

const state = vi.hoisted(() => ({
  queries: [] as unknown[][], mounts: [] as string[], mutate: vi.fn(),
  api: vi.fn(async (_method: string, _args: unknown[]) => ({})),
}))
vi.mock('@tanstack/react-query', async original => ({
  ...await original<typeof import('@tanstack/react-query')>(),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({ mutate: state.mutate, isPending: false }),
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    state.queries.push(queryKey)
    return { isLoading: false, isError: false, data: { factors: [{
      id: 'cn-control', label: 'CN 因子对照', kind: 'base', group: 'CN组', version: 1,
      formula: 'close', unit: 'CNY', direction: 'none', warmup_bars: 1, pit: false,
      asset_types: ['stock'], stability: 'stable', scale_free: false, dependencies: ['close'],
    }] } }
  },
}))
vi.mock('@/lib/api', async original => {
  const actual = await original<typeof import('@/lib/api')>()
  return { ...actual, api: Object.fromEntries(Object.keys(actual.api).map(k => [k, (...args: unknown[]) => state.api(k, args)])) }
})
vi.mock('./backtest/FactorDiscovery', () => ({ FactorDiscovery: ({ focusFactor }: { focusFactor: string }) => {
  state.mounts.push('inspect'); return <div data-cn-inspect>{focusFactor || 'CN 检验'}</div>
} }))
vi.mock('./factors/FactorEditor', () => ({ FactorEditor: ({ editId }: { editId: string }) => {
  state.mounts.push('editor'); return <div data-cn-editor>{editId || 'CN 编辑器'}</div>
} }))
vi.mock('./factors/FactorComposite', () => ({ FactorComposite: () => {
  state.mounts.push('composite'); return <div data-cn-composite>CN 组合</div>
} }))
vi.mock('./backtest/MiningWorkbench', () => ({ MiningWorkbench: () => {
  state.mounts.push('mining'); return <div data-cn-mining>CN 挖掘</div>
} }))
vi.mock('./backtest/ResearchCandidatesDialog', () => ({ ResearchCandidatesDialog: ({ onClose }: { onClose: () => void }) => <div data-cn-candidates><button onClick={onClose}>关闭候选对照</button></div> }))

let host: HTMLDivElement, root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.clearAllMocks()
  state.queries = []; state.mounts = []; localStorage.clear()
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })
async function render(path = '/factors', element = <Factors />) {
  function Nav() { const l = useLocation(), navigate = useNavigate(); return <><output data-location>{l.search}</output><button data-back onClick={() => navigate(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Nav /></MemoryRouter>))
}
function active() { return host.querySelector<HTMLElement>('[data-factor-market]')! }
async function market(i: number) { await act(async () => active().querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[i].click()) }
async function tab(label: string, preview = true) {
  const nav = active().querySelector(`[aria-label="${preview ? '因子样稿视图' : '因子视图'}"]`)!
  await act(async () => [...nav.querySelectorAll('button')].find(b => b.textContent?.trim() === label)!.click())
}
async function search(value: string) {
  const input = active().querySelector<HTMLInputElement>('input[aria-label="搜索因子样稿"]')!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })) })
}
async function filter(label: string, value: string) {
  const select = active().querySelector<HTMLSelectElement>(`select[aria-label="${label}"]`)!
  await act(async () => { select.value = value; select.dispatchEvent(new Event('change', { bubbles: true })) })
}
async function pick(i: number) { await act(async () => active().querySelector<HTMLButtonElement>(`[data-factor-id="fixture-factor-${active().dataset.factorMarket}-${i}"]`)!.click()) }

it('CN default retains five tab dispatches, focus/edit URL semantics and candidate dialog', async () => {
  await render('/factors?focus=cn-focus&edit=cn-edit&keep=1')
  expect(active().dataset.factorMarket).toBe('CN'); expect(active().querySelector('h1')?.textContent).toBe('因子')
  expect(active().querySelector('[data-cn-inspect]')?.textContent).toBe('cn-focus')
  await act(async () => active().querySelector<HTMLButtonElement>('[aria-label="打开候选方案"]')!.click())
  expect(active().querySelector('[data-cn-candidates]')).not.toBeNull()
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent === '关闭候选对照')!.click())
  for (const [label, key] of [['编辑器', 'editor'], ['组合', 'composite'], ['挖掘', 'mining'], ['检验', 'inspect']]) {
    await tab(label, false); expect(active().querySelector(`[data-cn-${key}]`)).not.toBeNull()
  }
  expect(host.querySelector('[data-location]')?.textContent).toContain('keep=1')
  expect(host.querySelector('[data-location]')?.textContent).not.toContain('focus=')
  expect(host.querySelector('[data-location]')?.textContent).not.toContain('edit=')
  await market(1); expect(host.querySelector('[data-cn-candidates]')).toBeNull(); await market(0)
  expect(active().querySelector('[data-cn-inspect]')?.textContent).toBe('CN 检验')
})
it('CN real library component still queries, filters and forwards inspect selection', async () => {
  await render('/factors?tab=library&keep=1')
  expect(state.queries).toContainEqual(['factors-library', 'all'])
  expect(active().textContent).toContain('CN 因子对照')
  const select = active().querySelector<HTMLSelectElement>('[aria-label="因子类型"]')!
  await act(async () => { select.value = 'custom'; select.dispatchEvent(new Event('change', { bubbles: true })) })
  expect(active().textContent).not.toContain('CN 因子对照')
  await act(async () => { select.value = 'all'; select.dispatchEvent(new Event('change', { bubbles: true })) })
  await act(async () => [...active().querySelectorAll('button')].find(b => b.textContent?.includes('去检验'))!.click())
  expect(active().querySelector('[data-cn-inspect]')?.textContent).toBe('cn-control')
  expect(host.querySelector('[data-location]')?.textContent).toContain('keep=1')
})
it('direct CN editor preserves explicit edit target', async () => {
  await render('/factors?tab=editor&edit=cn-custom')
  expect(active().querySelector('[data-cn-editor]')?.textContent).toBe('cn-custom')
})
it.each(['HK', 'US'] as const)('direct %s is fixed and isolated from CN/provider/API/storage/notification paths', async m => {
  const fetch = vi.fn(), write = vi.spyOn(Storage.prototype, 'setItem'), remove = vi.spyOn(Storage.prototype, 'removeItem'), notify = vi.fn()
  vi.stubGlobal('fetch', fetch); vi.stubGlobal('Notification', notify)
  await render(`/factors?market=${m}&edit=real-factor&focus=real-factor&run=real-run&candidate=real-candidate`)
  for (const t of ['演示因子｜合成数据｜非生产因子配置｜不产生真实信号｜不构成投资建议', 'synthetic-fixture', '2026-09-16', '2026-09-17T09:00:00Z', 'is_production: false', 'is_investment_signal: false', m === 'HK' ? '0700.HK' : 'AAPL.US']) expect(active().textContent).toContain(t)
  expect(active().querySelectorAll('[data-factor-id]')).toHaveLength(4)
  expect(active().textContent).not.toContain(m === 'HK' ? 'AAPL.US' : '0700.HK')
  for (const label of ['因子库', '编辑器', '组合', '挖掘', '检验']) {
    await tab(label); await act(async () => active().querySelectorAll<HTMLButtonElement>('button:disabled').forEach(b => b.click()))
  }
  expect(state.queries).toHaveLength(0); expect(state.mounts).toHaveLength(0)
  for (const spy of [state.api, state.mutate, fetch, write, remove, notify]) expect(spy).not.toHaveBeenCalled()
})
it('search, kind, group and status filters work with empty results', async () => {
  await render('/factors?market=HK'); await search('fixture-factor-HK-1')
  expect(active().querySelectorAll('[data-factor-id]')).toHaveLength(1)
  await search(''); await filter('演示因子类型', 'custom'); expect(active().querySelector('tbody')?.textContent).toContain('量能阻塞样稿')
  await filter('演示因子定义状态', 'READY'); expect(active().textContent).toContain('暂无匹配的因子样稿')
  await filter('演示因子类型', 'ALL'); expect(active().querySelectorAll('[data-factor-id]')).toHaveLength(1)
  await filter('演示因子定义状态', 'ALL'); await filter('演示因子分组', '量能样稿')
  expect(active().querySelectorAll('[data-factor-id]')).toHaveLength(1)
})
it('shared table sorts values in both directions with missing values last, and never ranks markets', async () => {
  await render('/factors?market=US')
  for (const label of ['因子名称 / 标识', '样稿版本', '定义状态', '合成展示值']) {
    const th = [...active().querySelectorAll('th')].find(h => h.textContent?.startsWith(label))!
    await act(async () => th.click()); const asc = [...active().querySelectorAll('[data-factor-id]')].map(r => r.getAttribute('data-factor-id'))
    await act(async () => th.click()); const desc = [...active().querySelectorAll('[data-factor-id]')].map(r => r.getAttribute('data-factor-id'))
    expect(asc[0]).not.toBe(desc[0]); expect(new Set(asc)).toEqual(new Set(desc))
    if (label === '合成展示值') expect(asc.slice(-2)).toEqual(desc.slice(-2))
  }
})
it('definition counts and detail preserve provenance, null reasons and execution blockers', async () => {
  await render('/factors?market=HK')
  for (const q of ['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED']) expect(active().querySelector(`[data-factor-count="${q}"]`)?.textContent).toContain('1 项定义样稿')
  const detail = active().querySelector('[aria-label="因子样稿详情"]')!
  for (const t of ['fixture:factor:HK:0:metadata:v1', '生产验证：BLOCKED', '生产执行：BLOCKED', 'Volume/VR20 BLOCKED', 'split-only BLOCKED', 'PIT/vintage BLOCKED', 'Daily finality PARTIAL', 'corporate actions UNKNOWN']) expect(detail.textContent).toContain(t)
  for (const key of ['ic_mean', 'ic_ir', 'coverage_count', 'evaluated_at', 'pit', 'universe_identity', 'input_contract_identity']) expect(detail.querySelector(`[data-factor-missing="${key}"]`)?.textContent).toContain('—')
  await pick(2); expect(detail.textContent).toContain('没有已确认的样稿公式'); expect(detail.textContent).toContain('未编写此项样稿值')
  expect(loadFactorPreview('HK').rows[2].sample_value).toBeNull()
})
it('all five Preview views remain read-only without synthetic IC, equal-weight fallback or mining records', async () => {
  await render('/factors?market=US')
  for (const [label, text] of [['检验', '无实际 IC / Rank IC / IR'], ['因子库', '未加入注册表'], ['编辑器', '不运行 DSL'], ['组合', '不自动等权或重分配'], ['挖掘', '挖掘任务：—（未创建）']]) {
    await tab(label); expect(active().querySelector('[aria-label="当前因子样稿视图"]')?.textContent).toContain(text)
    expect(active().querySelectorAll('button:disabled').length).toBeGreaterThan(0)
  }
})
it('market switch and browser back reset filters/detail but preserve unrelated URL context', async () => {
  await render('/factors?market=HK&keep=1'); await pick(1); await search('波动'); await filter('演示因子类型', 'virtual')
  await market(2); expect(active().querySelector<HTMLInputElement>('input')?.value).toBe('')
  expect(active().querySelectorAll('[data-factor-id]')).toHaveLength(4); expect(active().textContent).not.toContain('fixture-factor-HK')
  await pick(3); await act(async () => host.querySelector<HTMLButtonElement>('[data-back]')!.click())
  expect(active().dataset.factorMarket).toBe('HK'); expect(active().querySelector<HTMLInputElement>('input')?.value).toBe('')
  expect(active().querySelector<HTMLSelectElement>('select')?.value).toBe('ALL')
  expect(active().querySelector('[aria-label="因子样稿详情"]')?.textContent).toContain('fixture-factor-HK-0')
  expect(host.querySelector('[data-location]')?.textContent).toContain('keep=1')
})
it('fixture dates/values are deterministic and each call returns isolated sample data', () => {
  const old = loadFactorPreview('US'); vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z'))
  expect(loadFactorPreview('US')).toEqual(old); expect(loadFactorPreview('US').rows).not.toBe(old.rows)
  expect(loadFactorPreview('HK').rows[0].sample_value).not.toBe(old.rows[0].sample_value)
})
it('contract rejects mixed markets, fake readiness, nonfinite values and missing explanations', () => {
  const mutations: ((d: FactorPreviewData) => void)[] = [
    d => { Object.assign(d.rows[0], { market: 'HK' }) }, d => { Object.assign(d.rows[0], { execution_status: 'READY' }) },
    d => { Object.assign(d.rows[0], { pit: true }) }, d => { Object.assign(d.rows[0], { ic_mean: 0 }) },
    d => { Object.assign(d.rows[0], { sample_value: Infinity }) }, d => { Object.assign(d.rows[0], { sample_value: NaN }) },
    d => { Object.assign(d.rows[0], { formula: null }) }, d => { delete d.rows[0].missing_reasons.pit },
    d => { Object.assign(d.rows[0], { source: 'longbridge' }) }, d => { Object.assign(d.rows[0], { input_contract_identity: 'real-contract' }) },
    d => { Object.assign(d.rows[0], { sample_symbols: ['0700.HK'] }) },
  ]
  for (const mutate of mutations) { const d = loadFactorPreview('US'); mutate(d); expect(() => validateFactorPreview(d)).toThrow() }
})
it('loading/error/empty/wrong-market states retain the disclaimer and never fall back to CN', async () => {
  const empty = loadFactorPreview('HK'); empty.rows = []
  for (const [s, t] of [[{ kind: 'loading' }, '加载中'], [{ kind: 'error' }, '加载失败'], [{ kind: 'ready', data: empty }, '暂无匹配的因子样稿'], [{ kind: 'ready', data: loadFactorPreview('US') }, '加载失败']] as const) {
    await render('/factors', <FactorPreview market="HK" state={s} />)
    expect(host.textContent).toContain(t); expect(host.textContent).toContain('演示因子｜合成数据')
    expect(host.querySelector('tbody')).toBeNull()
  }
  expect(state.queries).toHaveLength(0); expect(state.api).not.toHaveBeenCalled()
})

it('only HK/US headers reserve mobile menu clearance and reset it at the desktop breakpoint', async () => {
  await render('/factors?market=HK')
  for (const m of ['HK', 'US']) {
    await market(m === 'HK' ? 1 : 2)
    const header = active().querySelector('header')!
    expect(header.classList.contains('pl-14')).toBe(true)
    expect(header.classList.contains('md:pl-5')).toBe(true)
    expect(header.textContent).toContain(`${m} 因子 · Preview`)
  }
  await market(0)
  expect(active().querySelector('header')!.classList.contains('pl-14')).toBe(false)
  // This checks the responsive class contract only. Actual geometry is verified in Edge.
})
