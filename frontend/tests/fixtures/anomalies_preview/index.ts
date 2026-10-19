import { unknownKeys, validateAnomaliesPreview, type AnomaliesMarket, type AnomaliesPreviewData, type AnomalySample } from '../../../src/custom/damon/anomalies-preview/contract'

const flags = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false, is_investment_signal: false, fixture_only: true, synthetic: true } as const
function sample(market: AnomaliesMarket, key: 'A' | 'B'): AnomalySample {
  return { ...flags, sample_id: `fixture-anomaly-${market}-${key}`, market, symbol: `SYNTH-${key}.${market}`, name: `${market} 合成证券 ${key}`,
    event_type: key === 'A' ? 'rapid_price_move' : 'intraday_breakout', direction: market === 'HK' ? 'up' : 'down', severity: key === 'A' ? 'high' : 'low',
    sample_state: 'SYNTHETIC_SAMPLE', event_time: `2026-09-16T${market === 'HK' ? '06' : '18'}:${key === 'A' ? '05' : '10'}:00Z`,
    change_pct: key === 'A' ? market === 'HK' ? 0.024 : -0.031 : null,
    condition: { window_minutes: key === 'A' ? 5 : null, description: '固定合成触发说明，仅展示类别和样稿参数；不执行价格比较或生产检测规则' },
    execution_status: 'BLOCKED', unknown: Object.fromEntries(unknownKeys.map(k => [k, null])) as AnomalySample['unknown'],
    missing_reasons: { production_event_id: '样稿从未写入生产事件库，没有真实 event_id', episode_id: '没有生产 episode 或持续交付证据',
      rule_version: '未绑定生产检测规则版本', health_state: '未请求真实 Worker 健康状态，不能判断是否运行',
      delivery_sequence: '没有连接真实交付，不存在生产水位', last_success_at: '没有发生真实读取，不使用样稿时间冒充最近成功时间',
      intelligence: '未查询或聚合生产 Intelligence、历史或因子证据', change_pct: '此合成样稿未定义涨跌幅，不填零', window_minutes: '此样稿未定义窗口，不推导或补默认值' },
    evidence: `fixture:anomalies:${market}:${key}:v1`, blockers: ['真实检测与交付未在 Preview 启用；Volume/VR20、split-only、finality、PIT/vintage 和正式 Universe 既有 blocker 不变'],
    warnings: ['严重程度、方向和事件时间均为固定合成样例，不是真实异动、通知或投资信号'] }
}
const hk: AnomaliesPreviewData = { ...flags, market: 'HK', trading_date: '2026-09-16', generated_at: '2026-09-17T09:00:00Z', rows: [sample('HK', 'A'), sample('HK', 'B')] }
const us: AnomaliesPreviewData = { ...flags, market: 'US', trading_date: '2026-09-16', generated_at: '2026-09-17T10:00:00Z', rows: [sample('US', 'A'), sample('US', 'B')] }
export function loadAnomaliesPreview(market: AnomaliesMarket): AnomaliesPreviewData {
  return validateAnomaliesPreview(structuredClone(market === 'HK' ? hk : us))
}
