import { describe, expect, it, vi } from 'vitest'
import { calendarLabel, marketSessionLabel } from './marketSession'

describe('backend session presentation', () => {
  it.each([
    ['regular', '交易中'], ['pre_open', '盘前'], ['break', '午休'],
    ['post_market', '盘后'], ['closed', '收盘 / 休市'],
    ['holiday', '节假日休市'], ['unknown', '市场状态未确认'],
    ['new_unverified_state', '市场状态未确认'],
  ])('%s has a Chinese label', (session_state, expected) => {
    expect(marketSessionLabel({ session_state })).toBe(expected)
  })
  it('does not recompute backend state using the browser clock', () => {
    vi.useFakeTimers()
    try {
      vi.setSystemTime(new Date('2040-01-01T00:00:00Z'))
      expect(marketSessionLabel({ session_state: 'regular' })).toBe('交易中')
      vi.setSystemTime(new Date('2000-01-01T00:00:00Z'))
      expect(marketSessionLabel({ session_state: 'regular' })).toBe('交易中')
    } finally { vi.useRealTimers() }
  })
  it('shows backend half-day and bounded closing-auction metadata', () => {
    expect(marketSessionLabel({ session_state: 'regular', half_day: true, early_close: '13:00' })).toContain('半日市 13:00提早收盘')
    expect(marketSessionLabel({ session_state: 'post_market', session_detail: 'closing_auction_window' })).toBe('收盘竞价窗口')
  })
  it('old payloads, missing states and expired coverage remain honest', () => {
    expect(marketSessionLabel()).toBe('市场状态未确认')
    expect(calendarLabel({ session_state: 'regular', calendar_status: 'unknown' })).toContain('未确认')
    expect(calendarLabel({ session_state: 'unknown', calendar_status: 'out_of_coverage' })).toContain('超出覆盖范围')
    expect(calendarLabel({ session_state: 'regular', calendar_status: 'covered' })).toContain('临时休市状态未核验')
  })
})
