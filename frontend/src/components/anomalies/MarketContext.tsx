import type { MarketAnomalyContext } from '@/lib/api'
import { eventTime, percent } from '@/lib/anomalyPresentation'

const labels: Record<string, string> = { idiosyncratic: '个股独立幅度突出', market_aligned: '与大盘同向',
  market_opposed: '与大盘反向', mixed: '市场背景混合', unknown: '证据不足' }
const reliable = (context?: MarketAnomalyContext | null) => context?.status === 'available'
  && [context.stock_change_pct, context.benchmark_change_pct, context.relative_move_pct]
    .every(value => value != null && Number.isFinite(Number(value)))

export function MarketContextSummary({ context }: { context?: MarketAnomalyContext | null }) {
  return <p className="mt-2 break-words text-xs text-muted">{reliable(context)
    ? `同期${context!.benchmark_name} ${percent(context!.benchmark_change_pct!)}，个股相对 ${percent(context!.relative_move_pct!)} · ${labels[context!.context_class] ?? '证据不足'}`
    : '市场背景暂不可用'}</p>
}

export function MarketContextEvidence({ context }: { context?: MarketAnomalyContext | null }) {
  return <section aria-label="市场背景" className="mt-4 rounded-card border border-border bg-base p-3">
    <h3 className="mb-3 font-semibold">市场背景</h3>
    {reliable(context) ? <dl className="grid grid-cols-2 gap-2 text-xs">
      <dt>基准指数</dt><dd>{context!.benchmark_name} · {context!.benchmark_symbol}</dd>
      <dt>股票窗口涨跌</dt><dd>{percent(context!.stock_change_pct!)}</dd>
      <dt>指数窗口涨跌</dt><dd>{percent(context!.benchmark_change_pct!)}</dd>
      <dt>相对涨跌</dt><dd>{percent(context!.relative_move_pct!)}</dd>
      <dt>背景分类</dt><dd>{labels[context!.context_class] ?? '证据不足'}</dd>
      <dt>观察窗口</dt><dd>{eventTime(context!.window_start!)} → {eventTime(context!.window_end!)}</dd>
      <dt>来源 / 版本</dt><dd className="break-all">{context!.source} / {context!.context_version}</dd>
    </dl> : <p>市场背景暂不可用 · {context?.blocker ?? 'enrichment_pending'}</p>}
    <p className="mt-3 text-xs text-muted">同期方向与幅度比较，不代表因果解释、交易建议或发生概率，不改变异动严重程度。</p>
  </section>
}
