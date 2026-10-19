// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Backtest } from './Backtest'
import { BacktestPreview } from '@/custom/damon/backtest-preview/Presentation'
import { validateBacktestPreview, type BacktestPreviewData, type BacktestPreviewState } from '@/custom/damon/backtest-preview/contract'
import { loadBacktestPreview } from '../../tests/fixtures/backtest_preview'

const calls = vi.hoisted(() => ({ strategy: vi.fn(), robustness: vi.fn(), candidates: vi.fn(), consume: vi.fn(), api: vi.fn(), toast: vi.fn() }))
vi.mock('./backtest/StrategyBacktest', () => ({ StrategyBacktest: (props: { loadCandidate?: unknown; onLoadConsumed: () => void }) => {
  calls.strategy(props.loadCandidate)
  return <button data-cn-strategy onClick={() => { calls.consume(props.loadCandidate); props.onLoadConsumed() }}>CN 策略替身</button>
} }))
vi.mock('./backtest/RobustnessValidation', () => ({ RobustnessValidation: () => { calls.robustness(); return <div data-cn-robustness /> } }))
vi.mock('./backtest/ResearchCandidatesDialog', () => ({ ResearchCandidatesDialog: (props: { onClose: () => void; onLoadStrategy: (c: unknown) => void }) => {
  calls.candidates(); return <div data-cn-candidates><button data-cn-close onClick={props.onClose}>关闭</button><button data-cn-load onClick={() => props.onLoadStrategy({ id: 'cn-fixture-candidate' })}>载入</button></div>
} }))
vi.mock('@/lib/api', () => ({ api: new Proxy({}, { get: (_target, key) => (...args: unknown[]) => calls.api(key, ...args) }) }))
vi.mock('@/components/Toast', () => ({ toast: (...args: unknown[]) => calls.toast(...args) }))

let host: HTMLDivElement, root: Root
beforeEach(() => { Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.clearAllMocks(); localStorage.clear(); sessionStorage.clear(); host = document.createElement('div'); document.body.append(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })
async function render(path = '/backtest', element = <Backtest />, state?: unknown) {
  function Nav() { const nav = useNavigate(), loc = useLocation(); return <><output data-url>{loc.pathname}{loc.search}</output><button data-back onClick={() => nav(-1)}>返回</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={[{ pathname: path.split('?')[0], search: path.includes('?') ? `?${path.split('?')[1]}` : '', state }]}>
    <Routes><Route path="/backtest" element={element} /><Route path="/factors" element={<div data-factors />} /></Routes><Nav />
  </MemoryRouter>))
}
async function click(selector: string) { await act(async () => host.querySelector<HTMLButtonElement>(selector)!.click()) }
async function textButton(text: string) { await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent?.trim() === text)!.click()) }
async function market(index: number) { await act(async () => host.querySelectorAll<HTMLButtonElement>('[aria-label="市场选择"] button')[index].click()) }
async function input(value: string) { await act(async () => {
  const el = host.querySelector<HTMLInputElement>('[aria-label="搜索回测样稿"]')!
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, value); el.dispatchEvent(new Event('input', { bubbles: true }))
}) }
async function select(label: string, value: string) { await act(async () => { const el = host.querySelector<HTMLSelectElement>(`[aria-label="${label}"]`)!; el.value = value; el.dispatchEvent(new Event('change', { bubbles: true })) }) }
it('CN keeps strategy default, tabs and candidate close/load/consume behavior', async () => {
  await render(); expect(host.querySelector('[data-backtest-market]')!.getAttribute('data-backtest-market')).toBe('CN')
  expect(calls.strategy).toHaveBeenCalledWith(null); expect(calls.robustness).not.toHaveBeenCalled()
  await textButton('验证'); expect(host.querySelector('[data-cn-robustness]')).not.toBeNull()
  await click('[aria-label="打开候选方案"]'); await click('[data-cn-close]'); expect(host.querySelector('[data-cn-candidates]')).toBeNull()
  await click('[aria-label="打开候选方案"]'); await click('[data-cn-load]')
  expect(host.querySelector('[data-cn-strategy]')).not.toBeNull(); expect(calls.strategy).toHaveBeenLastCalledWith({ id: 'cn-fixture-candidate' })
  await click('[data-cn-strategy]'); expect(calls.consume).toHaveBeenCalledWith({ id: 'cn-fixture-candidate' }); expect(calls.strategy).toHaveBeenLastCalledWith(null)
})
it('CN router-state candidate is passed to strategy and URL state consumed', async () => {
  await render('/backtest?keep=qa', <Backtest />, { loadCandidate: { id: 'cn-state-candidate' } })
  expect(calls.strategy).toHaveBeenLastCalledWith({ id: 'cn-state-candidate' }); expect(host.querySelector('[data-url]')!.textContent).toContain('keep=qa')
})
it.each(['factor', 'mining'])('CN legacy %s redirect retains other query parameters', async tab => {
  await render(`/backtest?tab=${tab}&run=qa&candidate=qa`)
  expect(host.querySelector('[data-factors]')).not.toBeNull(); expect(host.querySelector('[data-url]')!.textContent).toContain('run=qa&candidate=qa')
  expect(host.querySelector('[data-url]')!.textContent).toContain(tab === 'mining' ? 'tab=mining' : '/factors?run=')
  expect(calls.strategy).not.toHaveBeenCalled(); expect(calls.robustness).not.toHaveBeenCalled()
})
it.each(['HK', 'US'] as const)('%s direct Preview ignores production URL/state/reconnect inputs and has zero own side effects', async m => {
  localStorage.setItem('backtest_reconnect', 'real-task-must-not-be-adopted')
  const set = vi.spyOn(Storage.prototype, 'setItem'), remove = vi.spyOn(Storage.prototype, 'removeItem'), clear = vi.spyOn(Storage.prototype, 'clear')
  const get = vi.spyOn(Storage.prototype, 'getItem'), fetch = vi.fn(), eventSource = vi.fn(), notification = vi.fn()
  vi.stubGlobal('fetch', fetch); vi.stubGlobal('EventSource', eventSource); vi.stubGlobal('Notification', notification)
  await render(`/backtest?market=${m}&tab=mining&run=production&candidate=production&highlight=production`, <Backtest />, { loadCandidate: { id: 'production' } })
  expect(host.querySelector('[data-backtest-market]')!.getAttribute('data-backtest-market')).toBe(m)
  expect(host.textContent).toContain(`${m} 合成方案 A`); expect(host.textContent).not.toContain(`${m === 'HK' ? 'US' : 'HK'} 合成`)
  expect(host.textContent).toContain('Synthetic Data · Read-only · Not production validation'); expect(host.textContent).toContain('is_production: false')
  expect(host.textContent).toContain('2026-09-16'); expect(host.textContent).toContain('synthetic-fixture'); expect(host.textContent).toContain(`fixture:backtest:${m}:A:v1`)
  expect(host.querySelectorAll('button:disabled')).toHaveLength(8)
  for (const b of host.querySelectorAll<HTMLButtonElement>('button:disabled')) {
    expect(b.type).toBe('button'); expect(b.title).toContain('Preview 模式不可执行'); b.click(); b.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  }
  await input('B'); await click(`[data-backtest-id="fixture-backtest-${m}-B"]`)
  expect(host.querySelector('[aria-label="合成方案结构"]')!.textContent).toContain('此验证样稿未定义窗口')
  expect(host.querySelector('[data-backtest-missing="total_return"]')!.textContent).toContain('— · 没有真实任务')
  for (const spy of [calls.strategy, calls.robustness, calls.candidates, calls.api, calls.toast, set, remove, clear, get, fetch, eventSource, notification]) expect(spy).not.toHaveBeenCalled()
})
it('CN → HK → US → CN and browser back reset searches, filters, details and preserve unrelated URL', async () => {
  await render('/backtest?keep=qa'); await market(1); await input('not found'); expect(host.textContent).toContain('暂无匹配')
  await market(2); expect(host.querySelector<HTMLInputElement>('input')!.value).toBe(''); expect(host.textContent).toContain('US 合成方案 A')
  await select('回测样稿类型', 'robustness'); await click('[data-backtest-id="fixture-backtest-US-B"]')
  await market(0); expect(host.querySelector('[data-cn-strategy]')).not.toBeNull(); expect(host.querySelector('[data-backtest-id]')).toBeNull()
  await click('[data-back]'); expect(host.querySelector<HTMLInputElement>('input')!.value).toBe(''); expect(host.querySelector<HTMLSelectElement>('select')!.value).toBe('ALL')
  expect(host.querySelector('[aria-label="回测样稿详情"]')!.textContent).toContain('fixture-backtest-US-A'); expect(host.querySelector('[data-url]')!.textContent).toContain('keep=qa')
})
it('direct refresh remount uses only the URL market and fresh local state', async () => {
  await render('/backtest?market=HK'); await input('not found'); await act(async () => root.unmount()); root = createRoot(host)
  await render('/backtest?market=US'); expect(host.querySelector<HTMLInputElement>('input')!.value).toBe(''); expect(host.textContent).toContain('fixture-backtest-US-A')
  expect(host.textContent).not.toContain('fixture-backtest-HK-')
})
it('search, quality/type filters, three-state sort and accessible detail buttons work locally', async () => {
  await render('/backtest?market=HK'); await select('回测样稿完整性', 'BLOCKED'); expect(host.querySelectorAll('[data-backtest-id]')).toHaveLength(1)
  await select('回测样稿完整性', 'ALL'); await select('回测样稿类型', 'strategy'); expect(host.querySelectorAll('[data-backtest-id]')).toHaveLength(1)
  await select('回测样稿类型', 'ALL'); await click('[aria-label="按合成方案 / 身份排序"]'); expect(host.querySelector('th')!.getAttribute('aria-sort')).toBe('ascending')
  await click('[aria-label="按合成方案 / 身份排序"]'); expect(host.querySelector('th')!.getAttribute('aria-sort')).toBe('descending')
  await click('[aria-label="按合成方案 / 身份排序"]'); expect(host.querySelector('th')!.getAttribute('aria-sort')).toBe('none')
  const sort = host.querySelector<HTMLButtonElement>('[aria-label="按合成方案 / 身份排序"]')!; sort.focus(); expect(document.activeElement).toBe(sort)
  expect(sort.type).toBe('button'); expect(host.querySelector('[role="note"]')).not.toBeNull()
  await input('fixture-backtest-HK-B'); expect(host.querySelectorAll('[data-backtest-id]')).toHaveLength(1)
})
it('error/loading/empty/opposite-market state remains readonly without production fallback', async () => {
  const states: BacktestPreviewState[] = [{ kind: 'error' }, { kind: 'loading' }, { kind: 'ready', data: { ...loadBacktestPreview('HK'), rows: [] } }, { kind: 'ready', data: loadBacktestPreview('US') }]
  for (const state of states) {
    await render('/backtest', <BacktestPreview market="HK" state={state} />)
    expect(host.querySelector('[role="note"]')!.textContent).toContain('不运行回测'); expect(host.querySelectorAll('button:disabled')).toHaveLength(8)
    expect(host.querySelector('[data-backtest-id]')).toBeNull()
  }
  expect(host.textContent).toContain('回测样稿加载失败'); expect(calls.api).not.toHaveBeenCalled()
})
it('fixed fixture dates/parameters ignore clock and returned envelopes are isolated', () => {
  const hk = loadBacktestPreview('HK'), us = loadBacktestPreview('US'); vi.useFakeTimers(); vi.setSystemTime(new Date('2040-01-01T00:00:00Z'))
  expect(loadBacktestPreview('HK')).toEqual(hk); expect(loadBacktestPreview('US')).toEqual(us)
  expect(hk.rows[0].plan).not.toEqual(us.rows[0].plan); expect(loadBacktestPreview('HK').rows).not.toBe(hk.rows)
})
it.each(['HK', 'US'] as const)('%s contract accepts independent synthetic envelope and unknown results remain null', market => {
  const data = loadBacktestPreview(market); expect(validateBacktestPreview(data)).toBe(data)
  expect(data.rows.every(r => Object.values(r.unknown).every(v => v === null) && r.execution_status === 'BLOCKED')).toBe(true)
})
const invalid: [string, (data: BacktestPreviewData) => void][] = [
  ['mixed market', d => { Object.assign(d.rows[0], { market: 'US' }) }],
  ['production identity', d => { Object.assign(d.rows[0], { id: 'real-run' }) }],
  ['duplicate ID', d => { Object.assign(d.rows[1], d.rows[0]) }],
  ['currency conflict', d => { Object.assign(d.rows[0], { currency: 'USD' }) }],
  ['not synthetic', d => { Object.assign(d.rows[0], { synthetic: false }) }],
  ['execution READY', d => { Object.assign(d.rows[0], { execution_status: 'READY' }) }],
  ['wrong evidence', d => { d.rows[0].evidence = 'production-report' }],
  ['unknown to zero', d => { Object.assign(d.rows[0].unknown, { total_return: 0 }) }],
  ['missing reason', d => { delete d.rows[0].missing_reasons.total_return }],
  ['missing window reason', d => { delete d.rows[1].missing_reasons.lookback_sessions }],
  ['NaN', d => { d.rows[0].plan.lookback_sessions = NaN }],
  ['Infinity', d => { d.rows[0].plan.lookback_sessions = Infinity }],
  ['numeric string', d => { Object.assign(d.rows[0].plan, { lookback_sessions: '20' }) }],
  ['invalid date', d => { d.trading_date = '2026-02-31' }],
  ['reversed dates', d => { d.rows[0].plan.start = '2027-01-01' }],
  ['OR semantics', d => { Object.assign(d.rows[0].plan, { combination: 'OR' }) }],
  ['execution extra field', d => { Object.assign(d.rows[0], { run: true }) }],
]
it.each(invalid)('contract rejects %s', (_label, mutate) => { const data = loadBacktestPreview('HK'); mutate(data); expect(() => validateBacktestPreview(data)).toThrow() })
