import type { HistoricalAnomalyContext } from '@/lib/api'

const reliable = (context?: HistoricalAnomalyContext | null) => context?.status === 'available'
  && context.atr14 != null && Number.isFinite(Number(context.atr14)) && Number(context.atr14) > 0
  && context.move_atr_ratio != null && Number.isFinite(Number(context.move_atr_ratio))

export function HistoricalContextSummary({ context }: { context?: HistoricalAnomalyContext | null }) {
  return <p className="mt-2 text-xs text-muted">{reliable(context) ? `本次移动 ≈ ${Number(context!.move_atr_ratio).toFixed(2)} × ATR14` : '历史基准暂不可用'}</p>
}

export function HistoricalContextEvidence({ context }: { context?: HistoricalAnomalyContext | null }) {
  return <section aria-label="历史波动上下文" className="mt-4 rounded-card border border-border bg-base p-3">
    <h3 className="mb-3 font-semibold">历史波动上下文</h3>
    {reliable(context) ? <dl className="grid grid-cols-2 gap-2 text-xs">
      <dt>ATR14</dt><dd>{Number(context!.atr14).toFixed(2)}</dd>
      <dt>本次绝对移动</dt><dd>{context!.move_absolute ?? '—'}</dd>
      <dt>ATR 比例</dt><dd>{Number(context!.move_atr_ratio).toFixed(2)}x</dd>
      <dt>基准截止</dt><dd>{context!.baseline_as_of ?? '—'}</dd>
      <dt>来源</dt><dd className="break-all">{context!.source ?? '—'}</dd>
      <dt>调整口径</dt><dd className="break-all">{context!.adjustment_method ?? '—'}</dd>
      <dt>样本数 / 版本</dt><dd className="break-all">{context!.observations ?? '—'} / {context!.baseline_version}</dd>
    </dl> : <p>历史基准暂不可用 · {context?.blocker ?? 'enrichment_pending'}</p>}
    <p className="mt-3 text-xs text-muted">相对于日级 ATR 的移动尺度，不是分钟波动率、分位数或发生概率。历史来源不保证完整 PIT 版本。</p>
  </section>
}
