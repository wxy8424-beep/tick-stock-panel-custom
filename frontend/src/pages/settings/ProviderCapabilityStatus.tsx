import type { MarketCapability, ProviderHealthCapability } from '@/lib/api'

const LABELS: Record<MarketCapability['status'], string> = {
  supported: '已适配', unsupported: '暂不支持', contract_blocked: '契约阻塞',
  entitlement_denied: '当前不可用', unavailable: '当前不可用', empty: '当前无数据',
}

export function ProviderCapabilityStatus({ markets, serving, available }: {
  markets: Partial<Record<'CN' | 'HK' | 'US', MarketCapability & Partial<ProviderHealthCapability>>>
  serving: boolean
  available: boolean
}) {
  const values = Object.values(markets)
  const supported = values.filter(value => value.status === 'supported').length
  const allSupported = supported === 3
  const label = !available ? '当前不可用' : allSupported ? (serving && values.every(value => value.usable !== false) ? '服务中' : '已适配')
    : supported ? '部分支持' : values.some(value => value.status === 'contract_blocked') ? '契约阻塞'
      : values.every(value => value.status === 'unsupported') ? '暂不支持' : '当前不可用'
  return <div className="min-w-0 max-w-[65%] text-right text-[10px] text-secondary">
    <div>{label}</div>
    <div className="flex flex-wrap justify-end gap-x-2 gap-y-1 text-muted">
      {(['CN', 'HK', 'US'] as const).map(market => {
        const entry = markets[market]
        if (!entry) return <span key={market}>{market} 未声明</span>
        const state = entry.status === 'supported' && serving && available && entry.usable !== false
          ? '服务中' : entry.status_label ?? LABELS[entry.status] ?? '状态未知'
        return <span key={market} className="min-w-0 break-words" aria-label={`${market} 能力状态`}>
          {market} {state}{entry.message ? ` · ${entry.message}` : entry.reason ? ' · 能力契约尚未满足' : ''}
          {entry.runtime && <span className="block" title={entry.runtime.last_checked ?? undefined}>
            最近运行：{entry.runtime.message}{entry.runtime.symbol ? `（${entry.runtime.symbol}）` : ''}
          </span>}
        </span>
      })}
    </div>
  </div>
}
