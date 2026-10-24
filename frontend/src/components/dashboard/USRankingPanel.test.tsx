// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { USSection } from '@/lib/api'
import { USRankingPanel } from './USRankingPanel'

let host: HTMLDivElement, root: Root
const rows = [
  { symbol: 'AAPL.US', name: '苹果', close: 20, change_pct: .02, amount: 0, timestamp: 1791468000000 },
  { symbol: 'NVDA.US', name: '英伟达', close: 10, change_pct: -.01, amount: null, currency: 'USD' },
  { symbol: 'MISSING.US', close: null, change_pct: null, amount: NaN, timestamp: Infinity },
]
const section = (): USSection => ({ status: 'ok', mode: 'DERIVED', source: 'synthetic ranking section', updated_at: '2026-10-08T14:01:00Z', error: null, data: rows })
const onOpen = vi.fn(), onClose = vi.fn()
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  onOpen.mockClear(); onClose.mockClear()
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
async function render(value: USSection | undefined = section(), flags = {}) {
  await act(async () => root.render(<USRankingPanel title="合成榜单" section={value} loading={false} failed={false} href={symbol => '/?market=US&quote_symbol=' + symbol} onOpen={onOpen} onClose={onClose} {...flags} />))
}
const order = () => [...host.querySelectorAll('tbody a')].map(a => a.textContent)
it('shows actual section provenance and nulls, retains zero and never labels the list as full-market screening', async () => {
  await render()
  for (const text of ['synthetic ranking section', '10:01:00', 'America/New_York', '不是全市场筛选', '未提供或无效', '2%', '-1%']) expect(host.textContent).toContain(text)
  expect(host.querySelectorAll('tbody tr')).toHaveLength(3)
  expect(host.querySelectorAll('tbody tr')[0].querySelectorAll('td')[4].textContent).toBe('0')
  expect(host.querySelector('tbody tr')?.textContent).not.toContain('USD')
  expect(host.textContent).not.toMatch(/NaN|Infinity|Invalid Date/)
})
it('supports native sort buttons with three-state aria-sort and nulls last in both directions', async () => {
  await render()
  const button = host.querySelector<HTMLButtonElement>('button[aria-label="按快照价排序"]')!
  button.focus(); expect(document.activeElement).toBe(button)
  await act(async () => button.click())
  expect(button.closest('th')?.getAttribute('aria-sort')).toBe('ascending')
  expect(order()).toEqual(['NVDA.US', 'AAPL.US', 'MISSING.US'])
  await act(async () => button.click())
  expect(button.closest('th')?.getAttribute('aria-sort')).toBe('descending')
  expect(order()).toEqual(['AAPL.US', 'NVDA.US', 'MISSING.US'])
  await act(async () => button.click())
  expect(button.closest('th')?.getAttribute('aria-sort')).toBe('none')
  expect(order()).toEqual(rows.map(row => row.symbol))
})
it('filters invalid/mixed market identities and duplicates without pretending to verify listings', async () => {
  await render({ ...section(), data: [...rows, rows[0], { symbol: '700.HK' }, { symbol: 'WRONG.US', market: 'CN' }, null, { symbol: 'bad' }] })
  expect(order()).toEqual(rows.map(row => row.symbol))
  expect(host.textContent).toContain('排除格式/市场冲突或重复 5 条')
})
it('searches locally, opens only the filtered list, and preserves modifier-key navigation', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  const notification = vi.fn(); vi.stubGlobal('Notification', notification)
  const write = vi.spyOn(Storage.prototype, 'setItem')
  await render()
  const input = host.querySelector('input')!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, ' 英伟达 '); input.dispatchEvent(new Event('input', { bubbles: true })) })
  expect(order()).toEqual(['NVDA.US'])
  const link = host.querySelector<HTMLAnchorElement>('tbody a')!
  const modified = new MouseEvent('click', { bubbles: true, cancelable: true, ctrlKey: true })
  // Observe the component's native-link behavior, then stop jsdom's unsupported
  // full navigation in this test harness only.
  document.addEventListener('click', event => { expect(event.defaultPrevented).toBe(false); event.preventDefault() }, { once: true })
  await act(async () => link.dispatchEvent(modified))
  expect(onOpen).not.toHaveBeenCalled()
  await act(async () => link.click())
  expect(onOpen).toHaveBeenCalledWith(rows[1], [rows[1]])
  expect(write).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled(); expect(notification).not.toHaveBeenCalled()
})
it('shows empty search, missing and malformed data with no retry placeholder button', async () => {
  await render()
  const input = host.querySelector('input')!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, 'no matching row'); input.dispatchEvent(new Event('input', { bubbles: true })) })
  expect(host.textContent).toContain('没有匹配的已返回证券')
  await render({ ...section(), data: [] }); expect(host.textContent).toContain('接口没有返回可展示记录')
  await render({ ...section(), data: {} }); expect(host.textContent).toContain('榜单暂不可用')
  await render({ ...section(), status: 'unavailable', error: '合成缺失原因', data: null }); expect(host.textContent).toContain('合成缺失原因')
  expect(host.textContent).toContain('记录数量：—')
  expect([...host.querySelectorAll('button')].map(button => button.textContent)).toEqual(['关闭榜单', '应用条件', '重置条件'])
  expect([...host.querySelectorAll('button')].some(button => button.textContent === '重试')).toBe(false)
  await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="关闭已返回榜单"]')!.click())
  expect(onClose).toHaveBeenCalledTimes(1)
})
it('keeps loading, retained placeholder and failed cached data distinct', async () => {
  await render(section(), { loading: true }); expect(host.textContent).toContain('榜单加载中')
  await render(section(), { retained: true }); expect(host.textContent).toContain('暂保留前次接口已返回记录')
  await render(section(), { failed: true }); expect(host.querySelector('[role="alert"]')?.textContent).toContain('保留的缓存记录')
  expect(order()).toEqual(rows.map(row => row.symbol))
  expect(host.querySelector('[role="region"]')?.getAttribute('tabindex')).toBe('0')
  expect(host.querySelector('[role="region"] > div')?.className).not.toContain('overflow-x-auto')
})

async function filterInput(label: string, value: string) {
  const input = host.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })) })
}
async function applyConditions() { await act(async () => host.querySelector<HTMLFormElement>('form[aria-label="已返回记录条件"]')!.requestSubmit()) }
async function chooseCurrency(value: string) {
  const select = host.querySelector<HTMLSelectElement>('select[aria-label="按接口币种过滤"]')!
  await act(async () => { select.value = value; select.dispatchEvent(new Event('change', { bubbles: true })) })
}
it('applies percentage bounds as percent units with inclusive edges and excludes unknowns only while constrained', async () => {
  await render()
  await filterInput('涨跌幅下限（%）', '-1'); await filterInput('涨跌幅上限（%）', '2')
  expect(order()).toEqual(rows.map(row => row.symbol))
  await applyConditions()
  expect(order()).toEqual(['AAPL.US', 'NVDA.US'])
  await filterInput('涨跌幅下限（%）', '2'); await applyConditions()
  expect(order()).toEqual(['AAPL.US'])
  await act(async () => host.querySelector<HTMLButtonElement>('button[type="reset"]')!.click())
  expect(order()).toEqual(rows.map(row => row.symbol))
})
it('requires a reported currency for price bounds and never mixes unknown or other currencies', async () => {
  await render({ ...section(), data: [...rows, { symbol: 'HKDPRICE.US', currency: 'HKD', close: 10 }] })
  await filterInput('价格下限（原币）', '10'); await filterInput('价格上限（原币）', '10'); await applyConditions()
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('先选择明确币种')
  expect(order()).toHaveLength(4)
  await chooseCurrency('USD'); await applyConditions()
  expect(order()).toEqual(['NVDA.US'])
  await chooseCurrency('HKD'); await applyConditions()
  expect(order()).toEqual(['HKDPRICE.US'])
})
it.each(['NaN', 'Infinity', '0x10', '2%', 'abc'])('rejects invalid bound %s without applying it or replacing existing results', async bound => {
  await render()
  await filterInput('涨跌幅下限（%）', '2'); await applyConditions()
  expect(order()).toEqual(['AAPL.US'])
  await filterInput('涨跌幅下限（%）', bound); await applyConditions()
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('条件未应用')
  expect(order()).toEqual(['AAPL.US'])
})
it('rejects reversed ranges, preserves search on reset, and performs no requests/persistence/notification', async () => {
  const fetch = vi.fn(), notification = vi.fn(); vi.stubGlobal('fetch', fetch); vi.stubGlobal('Notification', notification)
  const write = vi.spyOn(Storage.prototype, 'setItem')
  await render()
  await filterInput('涨跌幅下限（%）', '3'); await filterInput('涨跌幅上限（%）', '2'); await applyConditions()
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('下限不能大于上限')
  const search = host.querySelector<HTMLInputElement>('[aria-label="搜索已返回证券"]')!
  await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(search, 'NVDA'); search.dispatchEvent(new Event('input', { bubbles: true })) })
  await act(async () => host.querySelector<HTMLButtonElement>('button[type="reset"]')!.click())
  expect(order()).toEqual(['NVDA.US']); expect(search.value).toBe('NVDA')
  expect(fetch).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled(); expect(notification).not.toHaveBeenCalled()
})
it('keeps actual zero distinct from missing values and keeps a disappearing currency selection explicit', async () => {
  await render({ ...section(), data: [...rows, { symbol: 'ZERO.US', currency: 'USD', close: 0, change_pct: 0 }, { symbol: 'NULL.US', currency: 'USD', close: null, change_pct: null }] })
  await chooseCurrency('USD')
  await filterInput('价格下限（原币）', '0'); await filterInput('价格上限（原币）', '0')
  await filterInput('涨跌幅下限（%）', '0'); await filterInput('涨跌幅上限（%）', '0'); await applyConditions()
  expect(order()).toEqual(['ZERO.US'])
  await render({ ...section(), data: [] })
  expect(host.querySelector<HTMLSelectElement>('select')?.value).toBe('USD')
  expect(host.querySelector('select')?.textContent).toContain('USD（本次未返回）')
  expect(host.textContent).toContain('币种 USD')
})
