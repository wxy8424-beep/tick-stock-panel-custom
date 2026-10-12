import type { AnomalyEvent, AnomalyHealth } from './api'

export const ANOMALY_TYPES = { rapid_price_move: '快速价格异动', intraday_breakout: '日内观测突破', volatility_expansion: '波动扩张' }
export const SEVERITY_LABELS = { high: '高 · HIGH', medium: '中 · MEDIUM', low: '低 · LOW' }
export const EVENT_STATUS = { first_trigger: '首次触发', escalation: '严重程度升级', sustained: '持续观察' }
export const percent = (value: string) => Number.isFinite(Number(value)) ? `${Number(value) >= 0 ? '+' : ''}${(Number(value) * 100).toFixed(2)}%` : '—'
export const eventTime = (value: string) => Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
export function filterEvents(rows: AnomalyEvent[], market: string, severity: string, type: string, symbol: string) {
  return rows.filter(row => (market === 'ALL' || row.market === market) && (severity === 'ALL' || row.severity === severity)
    && (type === 'ALL' || row.event_type === type) && row.symbol.toUpperCase().includes(symbol.trim().toUpperCase()))
    .sort((a, b) => Date.parse(b.detected_at) - Date.parse(a.detected_at) || b.store_id - a.store_id)
}
/** Event IDs, never price deltas, determine alert eligibility. Initial history is silent. */
export class AttentionLedger {
  private initialized = false
  private seen = new Set<string>()
  accept(rows: AnomalyEvent[]) {
    const fresh = rows.filter(row => !this.seen.has(row.event_id))
    for (const row of fresh) this.seen.add(row.event_id)
    if (!this.initialized) { this.initialized = true; return { fresh: [], high: [] } }
    return { fresh, high: fresh.filter(row => row.severity === 'high' && ['first_trigger', 'escalation'].includes(row.status)) }
  }
}
export function monitoringState(health: AnomalyHealth | undefined, failed: boolean) {
  if (failed) return { label: '暂不可用 · API 请求失败', state: 'unavailable' }
  if (!health || health.state === 'not_started') return { label: '状态未确认', state: 'unknown' }
  if (health.state !== 'observing') return { label: '异动引擎暂不可用', state: 'unavailable' }
  const sessions = Object.values(health.market_sessions ?? {})
  if (sessions.some(session => session?.diagnostic_code)) return { label: '观察受限 · 市场状态存在诊断', state: 'degraded' }
  if (!sessions.length || sessions.every(session => session?.session_state === 'unknown')) return { label: '市场状态未确认', state: 'unknown' }
  if (health.diagnostics.some(item => item.state === 'unknown')) return { label: '观察受限 · 部分证据不足', state: 'degraded' }
  if (sessions.every(session => ['closed', 'holiday', 'break', 'post_market', 'pre_open'].includes(session?.session_state ?? ''))) return { label: '市场关闭 · 保留历史事件', state: 'closed' }
  return { label: '观察中 · 轮询连接正常', state: 'live' }
}
