// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it } from 'vitest'
import type { HistoricalAnomalyContext } from '@/lib/api'
import { HistoricalContextEvidence, HistoricalContextSummary } from './HistoricalContext'

const fixture: HistoricalAnomalyContext = { status: 'available', blocker: null, atr14: '5.40', move_absolute: '4.10',
  move_atr_ratio: '0.759259259', baseline_as_of: '2026-10-09', observations: 60, source: 'yfinance.Ticker.history/yahoo',
  adjustment_method: 'yfinance_auto_adjust_false', baseline_version: 'historical-baseline-v1' }

async function render(context?: HistoricalAnomalyContext | null) {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const host = document.createElement('div'), root = createRoot(host)
  await act(async () => root.render(<><HistoricalContextSummary context={context} /><HistoricalContextEvidence context={context} /></>))
  const text = host.textContent
  await act(async () => root.unmount())
  return text!
}
it('renders daily ATR context without recalculating it', async () => {
  const text = await render(fixture)
  expect(text).toContain('本次移动 ≈ 0.76 × ATR14'); expect(text).toContain('5.40'); expect(text).toContain('4.10')
  expect(text).toContain('2026-10-09'); expect(text).toContain('yfinance'); expect(text).toContain('yfinance_auto_adjust_false')
  expect(text).toContain('不是分钟波动率、分位数或发生概率')
})
it('unavailable renders blocker, never a fake zero ratio', async () => {
  const text = await render({ ...fixture, status: 'unavailable', blocker: 'insufficient_atr_history', atr14: null, move_atr_ratio: null })
  expect(text).toContain('历史基准暂不可用'); expect(text).toContain('insufficient_atr_history'); expect(text).not.toContain('0.00x')
})
it('old event without optional context stays readable', async () => { expect(await render()).toContain('历史基准暂不可用') })
it('invalid/zero ATR and unknown context cannot show a reliable summary', async () => {
  expect(await render({ ...fixture, atr14: '0' })).not.toContain('0.76 ×')
  expect(await render({ ...fixture, status: 'unknown' })).toContain('历史基准暂不可用')
})
