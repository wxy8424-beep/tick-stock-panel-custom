// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it } from 'vitest'
import type { AnomalyIntelligence, IntelligenceStatus } from '@/lib/api'
import { IntelligenceEvidence } from './IntelligenceContext'

const fixture: AnomalyIntelligence = { event_id: 'fixture', status: 'READY', policy: { policy_id: 'fixture-policy', version: 'v1' },
  historical: { status: 'READY', atr14: '5.4', reference_close: '100', pit_capable: true, move_atr_ratio: null },
  market: { status: 'READY', benchmark_symbol: '.SPX.US', benchmark_change_pct: '0.01', relative_move_pct: '0.02', context_class: 'mixed' },
  factor: { status: 'READY', snapshot_id: 'fixture-snapshot', definition_id: 'fixture-definition', total_score: 0.5 },
  blockers: [], generated_at: '2026-10-09T15:00:00Z', version: 'anomaly-intelligence-v1' }
async function render(context?: AnomalyIntelligence) {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  const host = document.createElement('div'), root = createRoot(host)
  await act(async () => root.render(<IntelligenceEvidence context={context} />))
  const text = host.textContent!
  const status = host.querySelector('[data-intelligence-status]')?.getAttribute('data-intelligence-status')
  await act(async () => root.unmount())
  return { text, status }
}
for (const [state, label] of Object.entries({ READY: '证据齐备', PARTIAL: '部分证据', BLOCKED: '契约阻塞', UNAVAILABLE: '暂不可用' })) {
  it(`renders ${state} without declaring an analysis complete`, async () => {
    const result = await render({ ...fixture, status: state as IntelligenceStatus })
    expect(result.status).toBe(state); expect(result.text).toContain(label)
    expect(result.text).not.toContain('分析完成'); expect(result.text).toContain('不代表因果解释')
  })
}
it('missing snapshot and null ratio have no fake zero', async () => {
  const result = await render({ ...fixture, status: 'PARTIAL', factor: { status: 'UNAVAILABLE' },
    historical: { ...fixture.historical, status: 'PARTIAL', pit_capable: false }, blockers: ['factors:snapshot_not_available_at_requested_time'] })
  expect(result.text).toContain('事件时刻没有可用因子快照')
  expect(result.text).toContain('未验证 · 仅可作回溯上下文')
  expect(result.text).not.toContain('0x'); expect(result.text).not.toContain('fixture-snapshot')
})
it('missing policy remains blocked with human-readable blocker', async () => {
  const result = await render({ ...fixture, status: 'BLOCKED', policy: null, blockers: ['no_applicable_evidence_policy'] })
  expect(result.text).toContain('未配置适用的证据策略')
  expect((await render()).text).toContain('Unavailable')
})
it('blocked snapshot values are never presented as accepted evidence', async () => {
  const result = await render({ ...fixture, status: 'BLOCKED', factor: { ...fixture.factor, status: 'BLOCKED' },
    market: { ...fixture.market, status: 'BLOCKED' } })
  expect(result.text).not.toContain('fixture-snapshot')
  expect(result.text).not.toContain('.SPX.US')
})
it('distinguishes disabled factor from unavailable without a score', async () => {
  const result = await render({ ...fixture, factor: { status: 'NOT_SELECTED', total_score: null } })
  expect(result.text).toContain('策略未启用（Disabled by policy）')
  expect(result.text).not.toContain('fixture-snapshot')
  expect(result.text).not.toContain('0.5')
  const unavailable = await render({ ...fixture, factor: { status: 'UNAVAILABLE' } })
  expect(unavailable.text).not.toContain('Disabled by policy')
})
