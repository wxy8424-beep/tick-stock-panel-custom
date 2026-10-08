import { cn } from '@/lib/cn'

export type Market = 'CN' | 'HK' | 'US'

interface Props {
  value?: Market
  onChange?: (market: Market) => void
  className?: string
}

const markets: { value: Market; label: string }[] = [
  { value: 'CN', label: 'A股' },
  { value: 'HK', label: '港股' },
  { value: 'US', label: '美股' },
]

/** Only CN page content is implemented; unavailable markets never trigger a change. */
export function MarketSwitcher({ value = 'CN', onChange, className }: Props) {
  return (
    <div role="group" aria-label="市场选择" className={cn('inline-flex max-w-full items-center rounded-btn border border-border bg-base/60 p-0.5', className)}>
      {markets.map(market => (
        <button
          key={market.value}
          type="button"
          disabled={market.value !== 'CN'}
          aria-pressed={value === market.value}
          title={market.value === 'CN' ? 'A股' : `${market.label} · 待开发`}
          onClick={() => onChange?.(market.value)}
          className={cn('inline-flex h-7 items-center gap-1 whitespace-nowrap rounded-[5px] px-2.5 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent disabled:cursor-not-allowed',
            market.value === 'CN' && value === 'CN' ? 'bg-accent text-white shadow-sm' : 'text-secondary',
          )}
        >
          {market.label}
          {market.value !== 'CN' && <span className="text-[10px] text-muted">待开发</span>}
        </button>
      ))}
    </div>
  )
}

/** First toolbar beneath a market page's existing title and actions. */
export function MarketSwitcherBar({ className }: { className?: string }) {
  return (
    <div className={cn('min-w-0 shrink-0 border-b border-border px-5 py-1.5', className)}>
      <MarketSwitcher value="CN" />
    </div>
  )
}
