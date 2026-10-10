// @vitest-environment jsdom
import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import { ProviderCapabilityStatus } from './ProviderCapabilityStatus'
import type { MarketCapability } from '@/lib/api'

function text(status: MarketCapability['status'], reason?: string, message?: string) {
  return renderToStaticMarkup(<ProviderCapabilityStatus markets={{
    CN: { status, reason, message }, HK: { status, reason, message }, US: { status, reason, message },
  }} serving available />)
}
it('shows supported realtime from metadata', () => {
  expect(text('supported')).toContain('服务中')
  expect(text('supported')).toContain('CN')
})
it('shows contract and safe reason', () => {
  expect(text('contract_blocked', 'quantity_unit_unknown')).toContain('契约阻塞')
  expect(text('contract_blocked', 'quantity_unit_unknown', '数量单位尚未确认')).toContain('数量单位尚未确认')
})
it('shows unsupported without enabling a route', () => {
  expect(text('unsupported')).toContain('暂不支持')
})
it('explains endpoint-specific unit evidence without showing supported', () => {
  for (const [reason, label] of [
    ['candlestick_volume_unit_evidence_missing', '日K成交量'],
    ['minute_candlestick_volume_unit_evidence_missing', '分钟K成交量'],
    ['depth_volume_unit_evidence_missing', '盘口挂单量'],
  ]) {
    const html = text('contract_blocked', reason, `${label}缺少官方单位证据`)
    expect(html).toContain(label)
    expect(html).toContain('官方单位证据')
    expect(html).toContain('契约阻塞')
    expect(html).not.toContain('服务中')
    expect(html).not.toContain('已适配')
  }
})
it('shows partial financial support and current context unavailability', () => {
  const html = renderToStaticMarkup(<ProviderCapabilityStatus markets={{
    CN: { status: 'empty' }, HK: { status: 'supported' },
    US: { status: 'unavailable', reason: 'requires_us_token_or_market_context', message: '当前凭证或市场上下文不可用' },
  }} serving available />)
  expect(html).toContain('部分支持')
  expect(html).toContain('当前无数据')
  expect(html).toContain('当前凭证或市场上下文不可用')
})

it('renders backend health status and runtime independently', () => {
  const html = renderToStaticMarkup(<ProviderCapabilityStatus markets={{
    CN: { status: 'empty', status_label: '无数据', message: '代表标的无数据' },
    HK: { status: 'contract_blocked', status_label: '契约阻塞', message: '报告期证据不足' },
    US: { status: 'contract_blocked', status_label: '契约阻塞', message: '报告期证据不足', usable: false,
      runtime: { availability: 'available', diagnostic_code: 'upstream_available', message: '上游请求成功，仍需满足数据契约', last_checked: null, symbol: 'AAPL.US' } },
  }} serving available />)
  expect(html).toContain('无数据')
  expect(html).toContain('报告期证据不足')
  expect(html).toContain('最近运行：上游请求成功')
  expect(html).not.toContain('服务中')
  expect(html).not.toContain('已适配')
  expect(html).toContain('aria-label="US 能力状态"')
})

it('runtime unavailable cannot display serving or empty', () => {
  const html = renderToStaticMarkup(<ProviderCapabilityStatus markets={{
    US: { status: 'supported', status_label: '可用', usable: false,
      runtime: { availability: 'unavailable', diagnostic_code: 'financial_rate_limited', message: '接口限流，请稍后再试', last_checked: null, symbol: null } },
  }} serving available />)
  expect(html).toContain('接口限流')
  expect(html).not.toContain('服务中')
  expect(html).not.toContain('无数据')
})

it('unknown status and reason fall back safely', () => {
  expect(text('future' as MarketCapability['status'], 'fake-secret-marker')).toContain('状态未知')
  expect(text('future' as MarketCapability['status'], 'fake-secret-marker')).not.toContain('fake-secret-marker')
})

it('renders supplied capability irrespective of provider or market identity', () => {
  expect(text('supported')).toContain('服务中')
  expect(text('empty')).toContain('当前无数据')
  expect(text('unavailable')).toContain('当前不可用')
})
