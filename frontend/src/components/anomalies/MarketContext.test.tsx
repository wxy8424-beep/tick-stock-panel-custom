// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it } from 'vitest'
import type { MarketAnomalyContext } from '@/lib/api'
import { MarketContextEvidence, MarketContextSummary } from './MarketContext'

const fixture: MarketAnomalyContext = { event_id: 'a', market: 'US', benchmark_symbol: '.SPX.US', benchmark_name: '标普500',
  status: 'available', blocker: null, stock_change_pct: '0.032', benchmark_change_pct: '0.011', relative_move_pct: '0.021',
  direction_relation: 'same', context_class: 'idiosyncratic', observed_at: '2026-10-09T14:05:00Z', source: 'longbridge',
  context_version: 'market-context-v1', window_start: '2026-10-09T14:00:00Z', window_end: '2026-10-09T14:05:00Z' }
async function render(context?: MarketAnomalyContext) {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const host = document.createElement('div'), root = createRoot(host)
  await act(async () => root.render(<><MarketContextSummary context={context} /><MarketContextEvidence context={context} /></>))
  const text = host.textContent!
  await act(async () => root.unmount())
  return text
}
it('renders aligned-window figures and Chinese classification without deriving data', async () => {
  const text = await render(fixture)
  expect(text).toContain('同期标普500 +1.10%'); expect(text).toContain('个股相对 +2.10%')
  expect(text).toContain('个股独立幅度突出'); expect(text).toContain('longbridge'); expect(text).toContain('不改变异动严重程度')
})
it('unavailable and old evidence render no fake zero', async () => {
  expect(await render()).toContain('市场背景暂不可用')
  const text = await render({ ...fixture, status: 'unavailable', blocker: 'benchmark_boundary_missing', relative_move_pct: null })
  expect(text).toContain('benchmark_boundary_missing'); expect(text).not.toContain('+0.00%')
})
it('opposed context has no automatic escalation or advice', async () => {
  expect(await render({ ...fixture, context_class: 'market_opposed', benchmark_change_pct: '-0.011', relative_move_pct: '0.043' })).toContain('与大盘反向')
})
