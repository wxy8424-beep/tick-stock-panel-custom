// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AnomalyMonitoring } from './AnomalyMonitoring'
import { QK } from '@/lib/queryKeys'
import type { AnomalyEvent, AnomalyHealth } from '@/lib/api'
import { AttentionLedger, filterEvents, monitoringState } from '@/lib/anomalyPresentation'
import { readFileSync } from 'node:fs'

const mock = vi.hoisted(() => ({ rows: [] as AnomalyEvent[], health: { state: 'observing', diagnostics: [], market_sessions: { US: { session_state: 'regular' } } } as AnomalyHealth, fail: false }))
vi.mock('@/lib/api', () => ({ api: {
  anomalyRecent: async () => { if (mock.fail) throw new Error('offline'); return { rows: mock.rows, next_before_id: null } },
  anomalyHealth: async () => mock.health,
  anomalyEpisodes: async () => ({ rows: [] }),
} }))
vi.mock('@/components/StockPreviewDialog', () => ({ StockPreviewDialog: () => null }))
export function fixture(id = 'event-1', severity: AnomalyEvent['severity'] = 'low', status: AnomalyEvent['status'] = 'first_trigger'): AnomalyEvent {
  const snapshot = { snapshot_id: 1, price: '100', quote_timestamp: 1000, receive_timestamp: 1001, quality_state: 'unknown', warning_codes: ['volume_unknown'] }
  return { store_id: 1, event_id: id, episode_id: 'episode-1', symbol: 'AAPL.US', market: 'US', event_type: 'rapid_price_move', direction: 'up', severity, status,
    detected_at: '2026-10-09T14:05:00Z', window_start: '2026-10-09T14:00:00Z', window_end: '2026-10-09T14:05:00Z', observed_value: '104.3', baseline_value: '100', change_value: '4.3', change_pct: '0.043', threshold: '0.02', rule_id: 'rapid_move_5m', rule_version: '1-test', source: 'longbridge_snapshot_archive',
    evidence: { current: snapshot, baseline: [snapshot], sample_count: 11, maximum_gap_ms: 30000, baseline_scope: 'timestamp_boundary', volume_used: false, volume_status: 'unsupported_unit_unverified', history_truncated: false, medium_multiple: '1.5', high_multiple: '2', trigger_multiple: '2.15' } }
}
let host: HTMLDivElement, root: Root, client: QueryClient
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  mock.rows = []; mock.fail = false; mock.health = { state: 'observing', diagnostics: [], market_sessions: { US: { session_state: 'regular' } } }
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
})
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove() })
async function settle() { for (let i = 0; i < 6; i++) await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)) }) }
async function mount() { await act(async () => root.render(<QueryClientProvider client={client}><AnomalyMonitoring /></QueryClientProvider>)); await settle() }
async function update(rows: AnomalyEvent[]) { mock.rows = rows; await act(async () => { await client.refetchQueries({ queryKey: QK.anomalyRecent() }) }); await settle() }
async function click(text: string) { const button = [...host.querySelectorAll('button')].find(item => item.textContent?.includes(text) || item.getAttribute('aria-label') === text); expect(button).toBeTruthy(); await act(async () => button!.click()); await settle() }
async function select(label: string, value: string) { const input = host.querySelector<HTMLSelectElement>(`[aria-label="${label}"]`)!; await act(async () => { input.value = value; input.dispatchEvent(new Event('change', { bubbles: true })) }); await settle() }

it('restores recent history silently and maps values/severity/direction', async () => {
  mock.rows = [fixture('history', 'high')]; await mount()
  expect(host.textContent).toContain('快速价格异动'); expect(host.textContent).toContain('+4.30%')
  expect(host.querySelector('article')?.getAttribute('data-severity')).toBe('high')
  expect(host.querySelector('[role="alert"]')).toBeNull()
})
it('first HIGH and backend escalation each draw attention once; sustained does not', async () => {
  await mount(); const first = fixture('first', 'high'); await update([first])
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('首次触发')
  await click('关闭提醒'); await update([first]); expect(host.querySelector('[role="alert"]')).toBeNull()
  await update([fixture('sustained', 'high', 'sustained'), first]); expect(host.querySelector('[role="alert"]')).toBeNull()
  await update([fixture('upgrade', 'high', 'escalation'), first]); expect(host.querySelector('[role="alert"]')?.textContent).toContain('严重程度升级')
})
it('LOW and MEDIUM arrivals use finite card emphasis without a notification', async () => {
  await mount(); await update([fixture('low'), fixture('medium', 'medium')])
  expect(host.querySelector('[role="alert"]')).toBeNull()
  expect(host.querySelectorAll('[data-arrival="medium"]')).toHaveLength(1)
  expect(host.querySelectorAll('[data-arrival="low"]')).toHaveLength(1)
})
it('market/severity/type/search filters only change the visible events', async () => {
  mock.rows = [fixture(), { ...fixture('hk', 'high'), symbol: '700.HK', market: 'HK', event_type: 'intraday_breakout', direction: 'down', change_pct: '-0.03' }]
  await mount(); await click('港股'); expect(host.querySelectorAll('article')).toHaveLength(1); expect(host.textContent).toContain('↓ 向下')
  await select('严重程度', 'low'); expect(host.querySelectorAll('article')).toHaveLength(0)
  await select('严重程度', 'high'); await select('异动类型', 'rapid_price_move'); expect(host.querySelectorAll('article')).toHaveLength(0)
  await select('异动类型', 'intraday_breakout'); expect(host.querySelectorAll('article')).toHaveLength(1)
  expect(filterEvents(mock.rows, 'ALL', 'ALL', 'ALL', 'aapl')).toHaveLength(1)
})
it('evidence expands, preserves raw fields and collapses', async () => {
  mock.rows = [fixture()]; await mount(); await click('查看证据')
  expect(host.textContent).toContain('1-test'); expect(host.textContent).toContain('volume_unknown')
  expect(host.querySelector('pre')?.textContent).toContain('"volume_used": false')
  await click('查看证据'); expect(host.querySelector('pre')).toBeNull()
})
it('empty state is quiet and closed market does not pretend to be trading', async () => {
  mock.health.market_sessions = { US: { session_state: 'closed' } }; await mount(); await click('美股')
  expect(host.textContent).toContain('暂无异动事件'); expect(host.textContent).toContain('当前市场关闭或时段未确认')
})
it('degraded and unknown health never masquerade as healthy', async () => {
  mock.health.diagnostics = [{ state: 'unknown', reason: 'window_boundary_missing' }]; await mount()
  expect(host.querySelector('[data-health="degraded"]')).not.toBeNull()
  expect(monitoringState(undefined, false).state).toBe('unknown')
  expect(monitoringState({ state: 'unavailable', diagnostics: [] }, false).state).toBe('unavailable')
  expect(monitoringState({ state: 'observing', diagnostics: [] }, false).state).toBe('unknown')
  expect(monitoringState({ state: 'observing', diagnostics: [], market_sessions: { US: { session_state: 'closed' } } }, false).state).toBe('closed')
  expect(monitoringState({ state: 'observing', diagnostics: [], market_sessions: { US: { session_state: 'regular', diagnostic_code: 'calendar_provider_conflict' } } }, false).state).toBe('degraded')
})
it('API failure retains history and reports unavailable', async () => {
  mock.rows = [fixture()]; await mount(); mock.fail = true
  client.setQueryDefaults(QK.anomalyRecent(), { retry: false })
  await act(async () => { await client.refetchQueries({ queryKey: QK.anomalyRecent() }) }); await settle()
  expect(host.querySelector('[data-health="unavailable"]')).not.toBeNull(); expect(host.querySelectorAll('article')).toHaveLength(1)
})
it('ledger handles duplicates, initial restore and backend-only escalation', () => {
  const ledger = new AttentionLedger(); expect(ledger.accept([fixture('old', 'high')]).high).toHaveLength(0)
  expect(ledger.accept([fixture('new', 'high')]).high).toHaveLength(1)
  expect(ledger.accept([fixture('new', 'high')]).high).toHaveLength(0)
  expect(ledger.accept([fixture('next', 'medium', 'escalation')]).high).toHaveLength(0)
})
it('motion is finite and explicitly disabled for reduced motion', () => {
  const animationCSS = readFileSync('src/pages/AnomalyMonitoring.css', 'utf8')
  expect(animationCSS).toContain('prefers-reduced-motion: reduce')
  expect(animationCSS).toContain('animation: none !important')
  expect(animationCSS).not.toContain('infinite')
})
