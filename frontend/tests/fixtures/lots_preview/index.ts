/** Entirely authored account-free examples; no real Lot, broker account, quote or reminder producer. */
import { validateLotsPreview, type LotPreviewRow, type LotsPreviewData, type LotsPreviewMarket } from '../../../src/custom/damon/lots-preview/contract'
const provenance = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false,
  is_investment_signal: false, fixture_only: true, synthetic: true } as const
export function loadLotsPreview(market: LotsPreviewMarket): LotsPreviewData {
  const hk = market === 'HK', currency = hk ? 'HKD' : 'USD'
  const names = hk ? [['0700.HK', '腾讯控股'], ['9988.HK', '阿里巴巴'], ['3690.HK', '美团']] : [['AAPL.US', 'Apple'], ['NVDA.US', 'NVIDIA'], ['MSFT.US', 'Microsoft']]
  const rows: LotPreviewRow[] = names.map(([symbol, name], i) => ({ ...provenance, sample_id: `fixture-lot-${market}-${i}`, symbol, name, market, currency, qty_unit: 'synthetic-shares',
    values: i === 2 ? { qty: null, cost_price: null, reference_price: null, pnl_amount: null, pnl_pct: null, stop_price: null, target_price: null, drawdown_pct: null, concentration_pct: null }
      : i === 0 ? { qty: hk ? 100 : 10, cost_price: hk ? 300 : 180, reference_price: hk ? 315 : 189, pnl_amount: hk ? 1500 : 90, pnl_pct: .05, stop_price: hk ? 285 : 171, target_price: hk ? 330 : 198, drawdown_pct: .02, concentration_pct: null }
        : { qty: hk ? 50 : 5, cost_price: hk ? 80 : 120, reference_price: hk ? 76 : 114, pnl_amount: hk ? -200 : -30, pnl_pct: -.05, stop_price: hk ? 72 : 108, target_price: hk ? 88 : 132, drawdown_pct: null, concentration_pct: null },
    rule_sample: i === 2 ? { target_pct: null, stop_pct: null, remind_date: null, lead_days: null }
      : { target_pct: 10, stop_pct: i === 0 ? 5 : 10, remind_date: '2026-09-30', lead_days: 2 },
    reminder: { ...provenance, name: `${market} ${i === 0 ? '目标/止损' : i === 1 ? '到期' : '缺失字段'}提醒样例`,
      condition_description: '预编写演示说明：仅展示止盈/止损百分数与到期字段，不执行比较、不判定真实触发、不发送通知。',
      sample_state: i === 2 ? null : i === 0 ? 'PENDING_SAMPLE' : 'BLOCKED_SAMPLE', checked_at: i === 2 ? null : '2026-09-17T01:00:00Z',
      evidence: `fixture:lots:${market}:reminder:${i}:v1` },
    evidence: `fixture:lots:${market}:position:${i}:v1`,
    missing_fields: i === 2 ? ['values.qty', 'values.cost_price', 'values.reference_price', 'values.pnl_amount', 'values.pnl_pct', 'values.stop_price', 'values.target_price', 'values.drawdown_pct', 'values.concentration_pct', 'rule_sample.target_pct', 'rule_sample.stop_pct', 'rule_sample.remind_date', 'rule_sample.lead_days', 'reminder.sample_state', 'reminder.checked_at']
      : i === 0 ? ['values.concentration_pct'] : ['values.drawdown_pct', 'values.concentration_pct'],
    reasons: i === 2 ? ['本样稿未提供数量、成本、参考价、盈亏、风险线、规则及提醒状态/检查时间；均保留 null，不补零或默认正常']
      : i === 0 ? ['完整组合未知，不计算集中度'] : ['未提供回撤；完整组合未知，不计算集中度；阻塞样例不代表真实风险结论'],
    blockers: ['真实账户/持仓未接入', '生产数量、split-only、finality、PIT/vintage 与正式 Universe 尚未闭合'],
    warnings: ['数量为合成股数，不证明供应商数量单位', '成本/价格/盈亏/风险线均为固定演示结果，非券商数据；不含手续费、汇率或真实收益计算'],
  }))
  return validateLotsPreview({ ...provenance, market, currency, trading_date: '2026-09-16', generated_at: '2026-09-17T04:00:00Z', rows,
    overview: { position_count: 3, valued_count: 2, known_cost_amount: hk ? 34000 : 2400, known_reference_amount: hk ? 35300 : 2460, known_pnl_amount: hk ? 1300 : 60,
      total_pnl_amount: null, missing_reason: '第三份样稿缺成本和参考价；全部持仓盈亏未知，不把已知子集冒充总额' } })
}
