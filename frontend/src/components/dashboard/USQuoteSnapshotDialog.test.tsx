// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { USQuoteSnapshotDialog, type USQuoteSnapshotDialogProps } from './USQuoteSnapshotDialog'

let host: HTMLDivElement, root: Root
const props = (): USQuoteSnapshotDialogProps => ({ symbol: 'AAPL.US', quote: { symbol: 'AAPL.US', market: 'US', close: 102, change_pct: .02, amount: 0, timestamp: 1791468000000 }, loading: false, fetching: false, failed: false, invalid: false, onClose: vi.fn(), onRetry: vi.fn(), onNavigate: vi.fn() })
beforeEach(() => { Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); host = document.createElement('div'); document.body.append(host); root = createRoot(host) })
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.restoreAllMocks() })
async function render(p = props()) { await act(async () => root.render(<USQuoteSnapshotDialog {...p} />)) }
it('maps actual quote values and shows missing metadata without inferring USD or a real-time state', async () => {
  await render()
  for (const text of ['102.00', '2.00%', '0.00', '2026', 'America/New_York', '币种', '接口未提供', '新鲜度无法判定', '非完整个股技术分析']) expect(host.textContent).toContain(text)
  expect(host.textContent).not.toContain('USD')
  expect(host.querySelector('[role="dialog"]')).not.toBeNull()
})
it.each([null, NaN, Infinity])('does not render an invalid numeric value %s as zero', async value => {
  const p = props(); p.quote = { symbol: 'AAPL.US', close: value, timestamp: value }
  await render(p)
  expect(host.textContent).toContain('未提供或无效')
  expect(host.textContent).not.toMatch(/NaN|Infinity|0\.00/)
})
it('keeps loading, missing quote, API failure, and cached-refresh failure distinct', async () => {
  const p = props(); p.quote = null; p.loading = true; p.fetching = true; await render(p)
  expect(host.textContent).toContain('正在获取')
  p.loading = false; p.fetching = false; await render(p)
  expect(host.textContent).toContain('未返回该证券报价')
  p.failed = true; await render(p)
  expect(host.textContent).toContain('请求失败')
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '重试报价')!.click())
  expect(p.onRetry).toHaveBeenCalledTimes(1)
  p.quote = props().quote; await render(p)
  expect(host.textContent).toContain('保留同证券缓存报价')
})
it('rejects response identity mismatch and malformed URL without showing a different security', async () => {
  const p = props(); p.quote = { symbol: 'NVDA.US', close: 999 }; await render(p)
  expect(host.textContent).not.toContain('999')
  p.invalid = true; await render(p)
  expect(host.textContent).toContain('参数错误')
  expect([...host.querySelectorAll('button')].some(b => b.textContent === '重试报价')).toBe(false)
})
it('exposes disabled navigation reasons and supports Escape with focus restoration', async () => {
  const opener = document.createElement('button'); host.before(opener); opener.focus()
  const p = props(); await render(p)
  expect([...host.querySelectorAll('button')].filter(b => b.textContent === '上一只' || b.textContent === '下一只').every(b => b.disabled && !!b.title)).toBe(true)
  await act(async () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
  expect(p.onClose).toHaveBeenCalledTimes(1)
  await act(async () => root.render(null)); expect(document.activeElement).toBe(opener); opener.remove()
})
