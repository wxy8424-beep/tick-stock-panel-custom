import { useQuery } from '@tanstack/react-query'
import { api, type AnomalyIntelligence, type IntelligenceStatus } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { percent } from '@/lib/anomalyPresentation'

const labels: Record<IntelligenceStatus | 'NOT_SELECTED', string> = { READY: '证据齐备', PARTIAL: '部分证据', UNAVAILABLE: '暂不可用', BLOCKED: '契约阻塞', NOT_SELECTED: '策略未启用（Disabled by policy）' }
const blockers: Record<string, string> = {
  no_applicable_evidence_policy: '未配置适用的证据策略', multiple_matching_policies: '多个证据策略冲突',
  execution_binding_missing: '缺少执行绑定', calendar_binding_missing: '缺少指定日历版本',
  intelligence_not_collected: '证据尚未聚合', event_baseline_price_scale_unverified: '事件与历史价格尺度未验证',
  source_vintage_unverified: '历史来源版本及可得时间未验证', snapshot_not_available_at_requested_time: '事件时刻没有可用因子快照',
  market_context_missing: '缺少市场上下文', historical_context_missing: '缺少历史上下文',
}
function reason(code: string) {
  const leaf = code.includes(':') ? code.slice(code.indexOf(':') + 1) : code
  return blockers[leaf] ?? `证据未满足契约（${code}）`
}
const number = (value?: string | number | null) => value == null || !Number.isFinite(Number(value)) ? 'Unavailable' : String(value)

export function IntelligenceEvidence({ context }: { context?: AnomalyIntelligence }) {
  const history = context?.historical
  const market = context?.market.status === 'READY' ? context.market : undefined
  const factor = context?.factor.status === 'READY' ? context.factor : undefined
  return <section aria-label="Intelligence Context" className="mt-4 min-w-0 rounded-card border border-border bg-base p-3">
    <h3 className="mb-3 font-semibold">Intelligence Context · 结构化证据</h3>
    <p className="mb-3" data-intelligence-status={context?.status ?? 'UNAVAILABLE'}>{context ? labels[context.status] : '暂不可用'}</p>
    <dl className="grid grid-cols-1 gap-2 break-words sm:grid-cols-2">
      <dt>Evidence Policy</dt><dd>{context?.policy?.policy_id ?? 'Unavailable'} / {context?.policy?.version ?? '—'}</dd>
      <dt>历史证据</dt><dd>{history ? labels[history.status] : 'Unavailable'}</dd>
      <dt>ATR14 / 参考收盘价</dt><dd>{number(history?.atr14)} / {number(history?.reference_close)}</dd>
      <dt>PIT 状态</dt><dd>{history?.pit_capable === true && history.status === 'READY' ? '可得性证据已验证' : '未验证 · 仅可作回溯上下文'}</dd>
      <dt>移动 / ATR</dt><dd>{history?.move_atr_ratio != null ? `${number(history.move_atr_ratio)}x` : 'Unavailable · 价格尺度或证据未验证'}</dd>
      <dt>市场证据</dt><dd>{context?.market ? labels[context.market.status] : 'Unavailable'}</dd>
      <dt>基准 / 同期移动</dt><dd>{market?.benchmark_symbol ?? 'Unavailable'} / {market?.benchmark_change_pct != null ? percent(market.benchmark_change_pct) : 'Unavailable'}</dd>
      <dt>相对移动 / 分类</dt><dd>{market?.relative_move_pct != null ? percent(market.relative_move_pct) : 'Unavailable'} / {({ market_aligned: '与大盘同向', market_opposed: '与大盘反向', idiosyncratic: '个股独立幅度突出', mixed: '混合' } as Record<string, string>)[market?.context_class ?? ''] ?? 'Unavailable'}</dd>
      <dt>因子证据</dt><dd>{context?.factor ? labels[context.factor.status] : 'Unavailable'}</dd>
      <dt>快照 / 定义</dt><dd>{factor?.snapshot_id ?? 'Unavailable'} / {factor?.definition_id ?? 'Unavailable'}</dd>
      <dt>综合评分</dt><dd>{number(factor?.total_score)}</dd>
    </dl>
    {!!context?.blockers.length && <ul className="mt-3 space-y-1">{context.blockers.map(code => <li key={code}>{reason(code)}</li>)}</ul>}
    <p className="mt-3 text-muted">仅聚合已有证据，不代表因果解释、预测或交易建议。</p>
  </section>
}

export function IntelligenceContext({ eventId }: { eventId: string }) {
  const query = useQuery({ queryKey: QK.anomalyIntelligence(eventId), queryFn: () => api.anomalyIntelligence(eventId), retry: false,
    refetchInterval: query => query.state.data?.status === 'UNAVAILABLE' && !query.state.data.generated_at ? 3000 : false })
  return <IntelligenceEvidence context={query.data} />
}
