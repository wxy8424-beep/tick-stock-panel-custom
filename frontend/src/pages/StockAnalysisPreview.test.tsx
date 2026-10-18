// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { StockAnalysis } from '@/custom/stock-analysis/extension'
import { StockAnalysisPreview } from '@/custom/damon/stock-analysis-preview/Presentation'
import { validateAnalysisPreview, type AnalysisPreviewData } from '@/custom/damon/stock-analysis-preview/contract'
import { loadAnalysisPreview } from '../../tests/fixtures/stock_analysis_preview'

const state = vi.hoisted(() => ({ api: vi.fn(), query: vi.fn(), load: vi.fn(), history: vi.fn(), today: vi.fn(), analyze: vi.fn(), open: vi.fn(), remove: vi.fn(), toast: vi.fn(), searchMount: vi.fn(), alerts: vi.fn(), preview: vi.fn() }))
vi.mock('@tanstack/react-query', async original => ({ ...await original<typeof import('@tanstack/react-query')>(),
  useQuery: (o: { queryKey: unknown[]; queryFn: () => unknown; enabled?: boolean }) => {
    state.query(o.queryKey); if (o.enabled !== false) o.queryFn()
    return { isLoading: false, data: { rows: [], levels: {} } }
  },
}))
vi.mock('@/lib/api', async original => {
  const actual = await original<typeof import('@/lib/api')>()
  return { ...actual, api: Object.fromEntries(Object.keys(actual.api).map(k => [k, (...args: unknown[]) => state.api(k, ...args)])) }
})
vi.mock('@/lib/stockAnalysisStore', () => ({ loadHistory: () => state.load(), useHistoryReports: () => state.history(),
  findTodayReport: (...args: unknown[]) => state.today(...args), startAnalysis: (...args: unknown[]) => state.analyze(...args),
  openHistoryReport: (...args: unknown[]) => state.open(...args), deleteReport: (...args: unknown[]) => state.remove(...args),
}))
vi.mock('@/components/Toast', () => ({ toast: (...args: unknown[]) => state.toast(...args) }))
vi.mock('@/components/financials/StockFinancialSearch', () => ({ StockFinancialSearch: ({ onSelect, assetTypes }: { onSelect: (s: string, n: string) => void; assetTypes: string }) => {
  state.searchMount(assetTypes); return <button data-cn-select onClick={() => onSelect('600000.SH', 'CN 合成对照')}>CN 搜索替身</button>
} }))
vi.mock('@/components/stock-analysis/AnalysisKChart', () => ({ AnalysisKChart: () => <div data-cn-chart /> }))
vi.mock('@/components/stock-analysis/PriceAlertDialog', () => ({ PriceAlertDialog: ({ symbol, onClose }: { symbol: string; onClose: () => void }) => {
  state.alerts(symbol); return <button data-cn-alert onClick={onClose}>CN 提醒替身</button>
} }))
vi.mock('@/components/StockPreviewDialog', () => ({ StockPreviewDialog: ({ symbol }: { symbol: string | null }) => {
  state.preview(symbol); return symbol ? <div data-cn-detail>{symbol}</div> : null
} }))

let host: HTMLDivElement, root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.clearAllMocks(); localStorage.clear(); sessionStorage.clear()
  state.history.mockReturnValue({ reports: [], loaded: true }); state.today.mockResolvedValue(null); state.analyze.mockResolvedValue({ id: 'qa-task' })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })
async function render(path = '/stock-analysis', element = <StockAnalysis />) {
  function Nav() { const nav = useNavigate(), loc = useLocation(); return <><output data-url>{loc.search}</output><button data-back onClick={() => nav(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[path]}>{element}<Nav /></MemoryRouter>))
}
async function click(selector: string) { await act(async () => host.querySelector<HTMLButtonElement>(selector)!.click()) }
async function button(text: string) { await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent?.trim() === text)!.click()) }
async function market(i: number) { await act(async () => host.querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[i].click()) }
async function search(value: string) { await act(async () => {
  const el = host.querySelector<HTMLInputElement>('[aria-label="搜索合成证券"]')!
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, value); el.dispatchEvent(new Event('input', { bubbles: true }))
}) }
it('CN retains initial history, search asset types, empty board, selected-symbol queries and remembered identity', async () => {
  await render(); expect(host.querySelector('[data-analysis-market]')!.getAttribute('data-analysis-market')).toBe('CN')
  expect(state.load).toHaveBeenCalledTimes(1); expect(state.history).toHaveBeenCalled(); expect(state.searchMount).toHaveBeenCalledWith('stock,index')
  expect(host.textContent).toContain('选择一只股票开始分析'); expect(state.api).not.toHaveBeenCalled()
  await click('[data-cn-select]')
  expect(state.api).toHaveBeenCalledWith('klineDaily', '600000.SH', 250)
  expect(state.api).toHaveBeenCalledWith('stockAnalysisLevels', '600000.SH', 250)
  expect(JSON.parse(localStorage.getItem('last_stock:stock-analysis')!)).toEqual({ symbol: '600000.SH', name: 'CN 合成对照' })
  expect(state.query.mock.calls.map(c => c[0])).toContainEqual(['kline', '600000.SH', ''])
  await button('AI 个股分析'); expect(state.today).toHaveBeenCalledWith('600000.SH'); expect(state.analyze).toHaveBeenCalledWith('600000.SH', 'CN 合成对照')
  await button('点位提醒'); expect(state.alerts).toHaveBeenCalledWith('600000.SH')
  await click('button[title="查看个股日 K 详情"]'); expect(host.querySelector('[data-cn-detail]')!.textContent).toBe('600000.SH')
  await market(1); expect(host.querySelector('[data-cn-alert]')).toBeNull(); expect(host.querySelector('[data-cn-detail]')).toBeNull()
  await market(2); await market(0); expect(host.textContent).toContain('CN 合成对照'); expect(state.load).toHaveBeenCalledTimes(2)
})
it('CN history/view/delete and same-day confirmation remain original actions with substituted store', async () => {
  state.history.mockReturnValue({ loaded: true, reports: [{ id: 'qa-report', symbol: '600000.SH', name: 'CN 历史对照', created_at: '2026-09-16T09:00:00Z' }] })
  state.today.mockResolvedValue({ id: 'qa-report', created_at: '2026-09-16T09:00:00Z', focus: '合成关注点' })
  await render(); await act(async () => host.querySelector<HTMLElement>('aside button')!.click())
  expect(state.open).toHaveBeenCalledWith('qa-report')
  await click('button[title="删除"]'); expect(state.remove).toHaveBeenCalledWith('qa-report'); expect(state.toast).toHaveBeenCalledWith('已删除', 'success')
  await click('[data-cn-select]'); await button('AI 个股分析')
  expect(host.textContent).toContain('该个股已有分析报告'); expect(state.analyze).not.toHaveBeenCalled()
  await button('查看历史'); expect(state.open).toHaveBeenCalledWith('qa-report')
  await button('AI 个股分析'); await button('重新分析'); expect(state.analyze).toHaveBeenCalledWith('600000.SH', 'CN 合成对照')
})
it.each(['HK', 'US'] as const)('%s preview ignores production URL/storage identity and mounts no CN business hooks or actions', async m => {
  localStorage.setItem('last_stock:stock-analysis', JSON.stringify({ symbol: '600000.SH', name: '不可恢复的生产标的' }))
  const fetch = vi.fn(), notify = vi.fn(), stream = vi.fn()
  vi.stubGlobal('fetch', fetch); vi.stubGlobal('Notification', notify); vi.stubGlobal('EventSource', stream)
  const read = vi.spyOn(Storage.prototype, 'getItem'), write = vi.spyOn(Storage.prototype, 'setItem'), remove = vi.spyOn(Storage.prototype, 'removeItem'), clear = vi.spyOn(Storage.prototype, 'clear')
  await render(`/stock-analysis?market=${m}&symbol=600000.SH&id=real&report=real&analyze=1&keep=qa`)
  expect(host.textContent).toContain(`${m} 个股分析 · Preview`); expect(host.textContent).not.toContain('不可恢复的生产标的')
  for (const text of ['演示个股分析｜合成数据｜只读｜非生产研究', 'Synthetic Data', 'Read-only', 'Not production research', 'synthetic-fixture', '2026-09-16', '2026-09-17T09:00:00Z']) expect(host.textContent).toContain(text)
  expect(host.querySelectorAll('[data-analysis-id]')).toHaveLength(2); expect(host.textContent).not.toContain(m === 'HK' ? 'SYNTH-A.US' : 'SYNTH-A.HK')
  expect(host.querySelectorAll('button:disabled')).toHaveLength(12)
  await act(async () => host.querySelectorAll<HTMLButtonElement>('button:disabled').forEach(b => b.click()))
  await search('Synthetic'); await click(`[data-analysis-id="fixture-stock-${m}-B"]`)
  for (const spy of [state.api, state.query, state.load, state.history, state.searchMount, state.alerts, state.preview, state.analyze, state.today, state.open, state.remove, state.toast, fetch, notify, stream, read, write, remove, clear]) expect(spy).not.toHaveBeenCalled()
})
it('market changes/back/refresh remount local search/detail and preserve unrelated URL parameters', async () => {
  await render('/stock-analysis?market=HK&keep=qa'); await click('[data-analysis-id="fixture-stock-HK-B"]'); await search('nothing')
  await market(2); expect(host.querySelector<HTMLInputElement>('input')!.value).toBe(''); expect(host.textContent).toContain('US 合成证券 A')
  await click('[data-back]'); expect(host.querySelector<HTMLInputElement>('input')!.value).toBe(''); expect(host.querySelector('[aria-label="合成证券详情"]')!.textContent).toContain('SYNTH-A.HK')
  expect(host.querySelector('[data-url]')!.textContent).toContain('keep=qa')
  await act(async () => root.unmount()); root = createRoot(host); await render('/stock-analysis?market=US')
  expect(host.querySelector('[data-analysis-market]')!.getAttribute('data-analysis-market')).toBe('US')
})
it('search, tri-state sort, details and null reasons retain actual unknowns', async () => {
  await render('/stock-analysis?market=US'); await search('SYNTH-B.US')
  expect(host.querySelectorAll('[data-analysis-id]')).toHaveLength(1)
  expect(host.querySelector('[data-analysis-field="last"]')!.textContent).toBe('— · 此合成样稿未定义参考价')
  expect(host.querySelector('[data-analysis-missing="available_at"]')!.textContent).toContain('没有已证明的上游可得时间')
  await search(''); await click('[aria-label="按合成证券 / 代码排序"]'); expect(host.querySelector('th')!.getAttribute('aria-sort')).toBe('ascending')
  await click('[aria-label="按合成证券 / 代码排序"]'); expect(host.querySelectorAll('[data-analysis-id]')[0].getAttribute('data-analysis-id')).toBe('fixture-stock-US-B')
  await click('[aria-label="按合成证券 / 代码排序"]'); expect(host.querySelector('th')!.getAttribute('aria-sort')).toBe('none')
  await search('not found'); expect(host.textContent).toContain('暂无匹配的合成证券')
})
it('loading/error/empty and rejected opposite-market data retain disclaimer and disabled actions', async () => {
  for (const state of [{ kind: 'loading' }, { kind: 'error' }, { kind: 'ready', data: { ...loadAnalysisPreview('HK'), rows: [] } }, { kind: 'ready', data: loadAnalysisPreview('US') }] as const) {
    await render('/stock-analysis', <StockAnalysisPreview market="HK" state={state} />)
    expect(host.textContent).toContain('演示个股分析｜合成数据'); expect(host.querySelectorAll('button:disabled')).toHaveLength(12)
    expect(host.querySelector('[data-analysis-id]')).toBeNull()
  }
  expect(state.api).not.toHaveBeenCalled(); expect(state.load).not.toHaveBeenCalled()
})
it('fixed sample dates, values and identity ignore current clock; keyboard targets use native buttons', async () => {
  const expected = loadAnalysisPreview('HK'); vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z'))
  expect(loadAnalysisPreview('HK')).toEqual(expected); expect(loadAnalysisPreview('HK').rows).not.toBe(expected.rows); vi.useRealTimers()
  await render('/stock-analysis?market=HK')
  const switcher = host.querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')
  switcher[2].focus(); expect(document.activeElement).toBe(switcher[2]); expect(switcher[2].disabled).toBe(false)
  expect(switcher[1].getAttribute('aria-pressed')).toBe('true'); expect(host.querySelector('header')!.className).toContain('pl-14 md:pl-5')
})
it.each(['HK', 'US'] as const)('%s fixture validates as a separate synthetic envelope', m => {
  const data = loadAnalysisPreview(m); expect(validateAnalysisPreview(data)).toBe(data)
  expect(data.rows.every(r => r.market === m && r.execution_status === 'BLOCKED')).toBe(true)
})
const invalid: [string, (d: AnalysisPreviewData) => void][] = [
  ['wrong market', d => { Object.assign(d.rows[0], { market: 'US' }) }],
  ['real symbol', d => { Object.assign(d.rows[0], { symbol: '00700.HK' }) }],
  ['real id', d => { Object.assign(d.rows[0], { id: 'production-object' }) }],
  ['wrong currency', d => { Object.assign(d.rows[0], { currency: 'USD' }) }],
  ['wrong evidence', d => { Object.assign(d.rows[0], { evidence: 'real-report' }) }],
  ['missing null reason', d => { delete d.rows[0].missing_reasons.available_at }],
  ['NaN', d => { d.rows[0].quote.last = NaN }],
  ['Infinity', d => { d.rows[0].technical.ma20 = Infinity }],
  ['numeric string', d => { Object.assign(d.rows[0].quote, { last: '102' }) }],
  ['production readiness', d => { Object.assign(d.rows[0], { execution_status: 'READY' }) }],
  ['production flags', d => { Object.assign(d.rows[0], { is_production: true }) }],
  ['guessed availability', d => { Object.assign(d.rows[0].unknown, { available_at: d.generated_at }) }],
  ['unexpected action', d => { Object.assign(d.rows[0], { save: true }) }],
  ['invalid date', d => { d.trading_date = '2026-02-31' }],
  ['duplicate row', d => { Object.assign(d.rows[1], d.rows[0]) }],
]
it.each(invalid)('contract rejects %s', (_label, mutate) => { const data = loadAnalysisPreview('HK'); mutate(data); expect(() => validateAnalysisPreview(data)).toThrow() })
