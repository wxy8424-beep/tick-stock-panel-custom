// @vitest-environment jsdom
import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import { ProviderCapabilityStatus } from './ProviderCapabilityStatus'
import type { MarketCapability } from '@/lib/api'

function text(status: MarketCapability['status'], reason?: string) {
  return renderToStaticMarkup(<ProviderCapabilityStatus markets={{
    CN: { status, reason }, HK: { status, reason }, US: { status, reason },
  }} serving available />)
}
it('shows supported realtime from metadata', () => {
  expect(text('supported')).toContain('服务中')
  expect(text('supported')).toContain('CN')
})
it('shows contract and safe reason', () => {
  expect(text('contract_blocked', 'quantity_unit_unknown')).toContain('契约阻塞')
  expect(text('contract_blocked', 'quantity_unit_unknown')).toContain('数量单位尚未确认')
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
    const html = text('contract_blocked', reason)
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
    US: { status: 'unavailable', reason: 'requires_us_token_or_market_context' },
  }} serving available />)
  expect(html).toContain('部分支持')
  expect(html).toContain('当前无数据')
  expect(html).toContain('当前凭证或市场上下文不可用')
})
