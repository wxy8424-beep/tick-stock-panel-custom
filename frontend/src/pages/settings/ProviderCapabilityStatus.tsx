import type { MarketCapability } from '@/lib/api'

const LABELS: Record<MarketCapability['status'], string> = {
  supported: '已适配', unsupported: '暂不支持', contract_blocked: '契约阻塞',
  entitlement_denied: '当前不可用', unavailable: '当前不可用', empty: '当前无数据',
}
const REASONS: Record<string, string> = {
  quantity_unit_unknown: '数量单位尚未确认',
  quantity_unit_incompatible: '数量单位与现有契约不兼容',
  report_period_timestamp_unit_unverified: '报告期时间戳单位尚未确认',
  requires_us_token_or_market_context: '当前凭证或市场上下文不可用',
  representative_financial_response_empty: '已验证代表标的当前无财务数据',
  no_independent_adjustment_factor_series: '无独立除权因子序列',
  no_safe_full_market_bulk_minute_contract: '无可靠全市场批量分钟契约',
}

export function ProviderCapabilityStatus({ markets, serving, available }: {
  markets: Partial<Record<'CN' | 'HK' | 'US', MarketCapability>>
  serving: boolean
  available: boolean
}) {
  const values = Object.values(markets)
  const supported = values.filter(value => value.status === 'supported').length
  const allSupported = supported === 3
  const label = !available ? '当前不可用' : allSupported ? (serving ? '服务中' : '已适配')
    : supported ? '部分支持' : values.some(value => value.status === 'contract_blocked') ? '契约阻塞'
      : values.every(value => value.status === 'unsupported') ? '暂不支持' : '当前不可用'
  return <div className="min-w-0 max-w-[65%] text-right text-[10px] text-secondary">
    <div>{label}</div>
    <div className="flex flex-wrap justify-end gap-x-2 gap-y-1 text-muted">
      {(['CN', 'HK', 'US'] as const).map(market => {
        const entry = markets[market]
        if (!entry) return <span key={market}>{market} 未声明</span>
        const state = entry.status === 'supported' && serving && available ? '服务中' : LABELS[entry.status]
        return <span key={market}>{market} {state}{entry.reason ? ` · ${REASONS[entry.reason] ?? '能力契约尚未满足'}` : ''}</span>
      })}
    </div>
  </div>
}
