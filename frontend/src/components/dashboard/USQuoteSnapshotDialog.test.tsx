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

const metadata = () => ({ symbol: 'AAPL.US', status: 'available' as const, source: 'Synthetic finite quote source', source_reason: null,
  acquired_at: '2026-10-08T14:01:00Z', acquired_at_reason: null, reason: null })
it('separates acquisition, vendor quote and response times without claiming freshness', async () => {
  await render({ ...props(), metadata: metadata(), responseTime: '2026-10-08T14:02:00Z' })
  const value = host.textContent!
  expect(value).toContain('Synthetic finite quote source')
  for (const text of ['10:00:00', '10:01:00', '10:02:00', '成功获取完成时间', '缓存命中保留原时间', '不代表实时', '新鲜度无法判定']) expect(value).toContain(text)
})
it('keeps old response metadata explicitly unknown', async () => {
  await render()
  expect(host.textContent).toContain('旧接口未提供独立元数据')
  expect(host.textContent).not.toContain('Longbridge')
})
it.each(['NVDA.US', null])('rejects metadata identity %s without leaking its provenance or timestamp', async symbol => {
  await render({ ...props(), metadata: { ...metadata(), symbol } })
  expect(host.textContent).toContain('元数据证券身份或状态不一致')
  expect(host.textContent).not.toContain('Synthetic finite quote source')
  expect(host.textContent).not.toContain('10:01:00')
})
it.each(['not-a-time', '2026-10-08T14:01:00', null])('does not invent an acquisition time for %s', async acquired_at => {
  await render({ ...props(), metadata: { ...metadata(), acquired_at } })
  expect(host.textContent).toContain('时间无效/缺少时区')
  expect(host.textContent).not.toMatch(/Invalid Date|NaN/)
})
it.each(['empty', 'error', 'unavailable'] as const)('shows %s reasons with nullable source and acquisition', async status => {
  await render({ ...props(), quote: null, metadata: { ...metadata(), status, source: null, acquired_at: null, source_reason: '合成来源缺失原因', acquired_at_reason: '合成获取时间缺失原因', reason: '合成状态原因' } })
  for (const reason of ['合成来源缺失原因', '合成获取时间缺失原因', '合成状态原因']) expect(host.textContent).toContain(reason)
})
it('keeps a failed HTTP refresh distinct from cached successful acquisition metadata', async () => {
  await render({ ...props(), failed: true, metadata: metadata() })
  expect(host.textContent).toContain('保留同证券缓存报价')
  expect(host.textContent).toContain('已取得匹配报价（不代表实时）')
  expect(host.textContent).toContain('10:01:00')
})
it('does not accept available provenance without a matching quote', async () => {
  await render({ ...props(), quote: null, metadata: metadata() })
  expect(host.textContent).toContain('元数据证券身份或状态不一致')
  expect(host.textContent).not.toContain('Synthetic finite quote source')
})
