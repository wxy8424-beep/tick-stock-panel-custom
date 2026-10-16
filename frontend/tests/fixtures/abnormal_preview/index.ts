/** Independent anomaly presentation samples; never AnomalyEvent or monitoring-center alerts. */
import { validateAbnormalPreview, type AbnormalPreviewData, type AbnormalPreviewMarket, type AbnormalPreviewRow } from '../../../src/custom/damon/abnormal-preview/contract'
const provenance = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false,
  is_investment_signal: false, fixture_only: true, synthetic: true } as const
export function loadAbnormalPreview(market: AbnormalPreviewMarket): AbnormalPreviewData {
  const hk = market === 'HK'
  const names = hk ? [['0700.HK', '腾讯控股'], ['9988.HK', '阿里巴巴'], ['3690.HK', '美团']]
    : [['AAPL.US', 'Apple'], ['NVDA.US', 'NVIDIA'], ['MSFT.US', 'Microsoft'], ['AMZN.US', 'Amazon']]
  const rows: AbnormalPreviewRow[] = names.map(([symbol, name], i) => ({ ...provenance, sample_id: `fixture-abnormal-${market}-${i}`, symbol, name, market, trading_date: '2026-09-16',
    event_type: i === 1 ? 'intraday_breakout' : i === 2 ? 'volatility_expansion' : 'rapid_price_move',
    severity: i === 3 ? null : i === 0 ? 'high' : i === 1 ? 'medium' : 'low',
    event_time: i === 3 ? null : `2026-09-16T${hk ? '06' : '14'}:0${5 - i}:00Z`,
    change_pct: i === 2 ? null : i === 0 ? (hk ? .025 : .032) : i === 1 ? (hk ? -.018 : -.021) : 0,
    sample_state: i === 3 ? null : i === 2 ? 'BLOCKED_SAMPLE' : 'OBSERVATION_SAMPLE',
    condition_description: i === 2 ? '波动扩张仅为合成类别样例；无历史波动率或真实检测结果，不能据此判定生产触发。' : '固定演示说明：用于价格变化或突破样例的界面验收，不计算阈值、不证明任何真实触发。',
    evidence: `fixture:abnormal:${market}:2026-09-16:${i}:v1`,
    missing_fields: i === 3 ? ['severity', 'event_time', 'sample_state'] : i === 2 ? ['change_pct'] : [],
    reasons: i === 3 ? ['未编写事件时间、严重程度和状态；不以当前时间、低风险或正常状态补齐'] : i === 2 ? ['波动样例未提供演示涨跌幅，不补零、不计算历史波动指标'] : [],
    blockers: ['真实 HK/US 异动生产验证仍 BLOCKED', 'Volume / VR20、split-only、PIT/vintage 与正式 Universe 未闭合'],
    warnings: ['合成样本不是 AnomalyEvent，不进入生产告警、注意力队列或数据库', 'Daily finality PARTIAL；无实时行情、真实阈值或常规时段确认'],
  }))
  return validateAbnormalPreview({ ...provenance, market, trading_date: '2026-09-16', generated_at: '2026-09-17T03:00:00Z', rows })
}
