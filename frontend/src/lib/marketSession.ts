/** Display only: all dates, states and coverage decisions come from the backend. */
export interface CalendarCoverage {
  calendar_year: number
  coverage_start: string
  coverage_end: string
  source: string[]
  last_updated: string
}
export interface MarketSessionInfo {
  session_state: string
  calendar_status: string
  calendar_coverage?: CalendarCoverage
  confirmed_trading_day?: boolean | null
  half_day?: boolean
  early_close?: string | null
  session_detail?: string | null
  state_source?: string
  runtime_status?: string
  diagnostic_code?: string | null
}
const LABELS: Record<string, string> = {
  regular: '交易中', pre_open: '盘前', break: '午休', post_market: '盘后',
  closed: '收盘 / 休市', holiday: '节假日休市', unknown: '市场状态未确认',
}
export function marketSessionLabel(session?: Pick<MarketSessionInfo, 'session_state' | 'half_day' | 'early_close' | 'session_detail'>): string {
  if (!session) return '市场状态未确认'
  const label = session.session_detail === 'closing_auction_window' ? '收盘竞价窗口' : LABELS[session.session_state] ?? LABELS.unknown
  return `${label}${session.half_day ? ` · 半日市${session.early_close ? ` ${session.early_close}提早收盘` : ''}` : ''}`
}
export function calendarLabel(session?: MarketSessionInfo): string {
  if (session?.calendar_status !== 'covered') return '交易日历未确认或超出覆盖范围'
  return `官方${session.calendar_coverage?.calendar_year ?? ''}日历 · 计划时段（临时休市状态${session.runtime_status === 'verified' ? '已核验' : '未核验'}）`
}
