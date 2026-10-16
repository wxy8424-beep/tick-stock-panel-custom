/** Independent fixed monitoring examples. Not MonitorRule / AlertEvent or production worker evidence. */
import { validateMonitorPreview, type MonitorMarket, type MonitorPreviewData, type SampleState, type SampleSeverity } from '../../../src/custom/damon/monitor-preview/contract'
const provenance = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false,
  is_investment_signal: false, fixture_only: true, synthetic: true } as const
export function loadMonitorPreview(market: MonitorMarket): MonitorPreviewData {
  const hk = market === 'HK'
  const symbols = hk ? ['0700.HK', '9988.HK', 'HSI', '3690.HK'] : ['AAPL.US', 'NVDA.US', 'SPX', 'MSFT.US']
  const states: SampleState[] = hk ? ['NORMAL', 'WARNING', 'ERROR', 'UNAVAILABLE'] : ['NORMAL', 'WARNING', 'NORMAL', 'UNAVAILABLE']
  return validateMonitorPreview({ ...provenance, market, trading_date: '2026-09-16', generated_at: '2026-09-17T02:00:00Z',
    updated_at: hk ? '2026-09-17T01:55:00Z' : null, updated_reason: hk ? null : 'US 样稿未提供最近更新时间，不读取真实 Worker 检查时间',
    evidence: `fixture:monitor:${market}:2026-09-16:v1`,
    counts: { total: { value: 4, reason: null }, NORMAL: { value: hk ? 1 : 2, reason: null }, WARNING: { value: 1, reason: null }, ERROR: { value: hk ? 1 : 0, reason: null }, UNAVAILABLE: { value: 1, reason: null } },
    tasks: symbols.map((symbol, i) => ({ ...provenance, id: `fixture-monitor-${market}-${i}`, market, symbol,
      name: `${market} ${['价格观察', '样本完整性', '指数观察', '数量口径检查'][i]}（演示）`, type: ['价格样例', '数据质量样例', '指数样例', '数量样例'][i],
      sample_state: states[i], severity: i === 3 ? null : (i === 1 ? 'WARN' : hk && i === 2 ? 'CRITICAL' : 'INFO') as SampleSeverity,
      checked_at: i === 3 ? null : '2026-09-17T01:50:00Z', condition_description: '固定编写的界面状态案例，不执行规则、不比较真实价格、不证明触发条件成立。',
      completeness: i === 3 ? 'SAMPLE_PARTIAL' : 'SAMPLE_COMPLETE', missing_fields: i === 3 ? ['severity', 'checked_at'] : [],
      reasons: i === 3 ? ['未编写严重程度及检查时间，不以正常状态或当前时间代替'] : [],
      evidence: `fixture:monitor:${market}:task:${i}:v1`, blockers: ['生产 Momentum 输入 BLOCKED；数量/VR20、split-only、PIT/vintage 未闭合'],
      warnings: ['只表示样稿字段完整性，不表示真实服务健康', 'Daily finality PARTIAL；真实 Universe 未建立'],
    })),
    alerts: symbols.slice(0, hk ? 2 : 3).map((symbol, i) => ({ ...provenance, id: `fixture-alert-${market}-${i}`, market, symbol,
      title: `${market} 合成告警样本 ${i + 1}`, category: i === 0 ? '价格观察样例' : '数据质量样例', severity: i === 2 ? null : i === 0 ? 'WARN' : 'INFO',
      occurred_at: i === 0 ? '2026-09-16T13:00:00Z' : '2026-09-16T12:00:00Z', sample_alert_state: i === 2 ? null : i === 0 ? 'OPEN_SAMPLE' : 'ACKNOWLEDGED_SAMPLE',
      condition_description: '合成触发说明：为验收列表和详情预先编写，不对应真实事件、计算或通知。',
      evidence: `fixture:monitor:${market}:alert:${i}:v1`, missing_fields: i === 2 ? ['severity', 'sample_alert_state'] : [],
      reasons: i === 2 ? ['样稿未提供告警状态及严重程度，不推断为未确认或低风险'] : [],
    })),
  })
}
