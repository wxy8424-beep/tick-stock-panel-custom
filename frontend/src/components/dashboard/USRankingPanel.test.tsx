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
  expect(host.querySelectorAll('button')).toHaveLength(1)
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
