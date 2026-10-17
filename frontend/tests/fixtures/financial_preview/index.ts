/** Invented company reports; the display symbols do not make these real issuer filings. */
import { validateFinancialPreview, type FinancialPreviewData, type FinancialMarket, type FinancialCompanySample, type FinancialField, type FinancialReportSample, type FinancialSampleValue } from '../../../src/custom/damon/financial-preview/contract'
const flags = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false, is_investment_signal: false, fixture_only: true, synthetic: true } as const
export function loadFinancialPreview(market: FinancialMarket): FinancialPreviewData {
  const hk = market === 'HK', currency = hk ? 'HKD' : 'USD'
  const companies: FinancialCompanySample[] = (hk ? ['0700.HK', '9988.HK'] : ['AAPL.US', 'MSFT.US']).map((symbol, ci) => {
    const base = (hk ? 1000 : 2000) + ci * 400, prefix = `fixture:financial:${market}:${ci}`
    const reports: FinancialReportSample[] = ['2023', '2024', '2025', '2026Q1', '2026Q2'].map((p, i) => {
      const annual = i < 3, year = annual ? p : '2026', end = annual ? `${year}-12-31` : i === 3 ? '2026-03-31' : '2026-06-30'
      const revenue = base + (annual ? i * 100 : -650 + i * 50), net = ci === 1 && i === 4 ? null : revenue / 10
      const ocf = i === 1 ? null : revenue / 8, capex = revenue / 20
      const input = (key: string, v: number | null): FinancialSampleValue => ({ value: v, status: v === null ? 'UNAVAILABLE' : 'READY', reason: v === null ? `${key} 样稿未提供，不填零、不拼接其他期` : null, origin: 'SYNTHETIC_INPUT', formula: '独立合成输入；不是供应商原始字段', evidence: `${prefix}:${p}:${key}` })
      const values = Object.fromEntries(Object.entries({ revenue, operating_profit: revenue / 5, net_income: net, total_assets: base * 4 + i * 100, total_liabilities: base * 2 + i * 40, total_equity: base * 2 + i * 60, operating_cash_flow: ocf, capex }).map(([k, v]) => [k, input(k, v)])) as Record<FinancialField, FinancialSampleValue>
      values.free_cash_flow = { ...input('free_cash_flow', ocf === null ? null : ocf - capex), origin: 'DERIVED_SAMPLE', formula: 'FCF = 同期经营现金流 - 同期资本开支（正数流出）' }
      values.net_margin = { ...input('net_margin', net === null ? null : 100 * net / revenue), origin: 'DERIVED_SAMPLE', formula: '净利率 = 同期净利润 / 同期营业收入 × 100（百分点）' }
      const at = annual ? `${Number(year) + 1}-04-15T08:00:00Z` : i === 3 ? '2026-05-15T08:00:00Z' : '2026-08-15T08:00:00Z'
      return { id: `fixture-report-${market}-${ci}-${p}`, period_start: annual ? `${year}-01-01` : i === 3 ? '2026-01-01' : '2026-04-01', period_end: end, report_type: annual ? 'ANNUAL' : 'QUARTER', flow_basis: annual ? 'FULL_YEAR' : 'SINGLE_QUARTER', balance_basis: 'PERIOD_END', announce_at: ci === 1 && i === 4 ? null : at, available_at: ci === 1 && i === 4 ? null : at, time_reason: ci === 1 && i === 4 ? '该期公告/可得时间未提供；不以报告期或 generated_at 代替' : null, values }
    })
    const annual = reports[2], price = hk ? 24 : 48, shares = hk ? 100 : 200, eps = annual.values.net_income.value! / shares
    const defs = [
      ['PE', price / eps, '倍', 'FY2025 PE = 固定价格 / FY2025 合成 EPS（不是 TTM）'],
      ['PB', ci === 1 ? null : price * shares / annual.values.total_equity.value!, '倍', 'PB = 固定价格 × 同口径股数 / FY2025 期末权益'],
      ['PS', price * shares / annual.values.revenue.value!, '倍', 'FY2025 PS = 固定样稿市值 / FY2025 全年营收（不是 TTM）'],
      ['DIVIDEND_YIELD', null, '%', '现金股息 / 同时点价格；股息区间与币种证据缺失，不计算'],
      ['MARKET_CAP', price * shares, `百万 ${currency}`, '样稿市值 = 固定价格 × 样稿当期股数（百万股）'],
      ['EPS', eps, `${currency}/股`, 'FY2025 EPS = FY2025 合成净利润（百万）/ 加权平均普通股数（百万股）'],
    ] as const
    return { ...flags, symbol, name: `${market} 演示企业${ci ? '乙' : '甲'}（虚构财报）`, market, currency, amount_unit: 'MILLION', reports,
      valuations: defs.map(([key, v, unit, formula]) => ({ key, value: v, unit, currency, input_source: 'synthetic-fixture', origin: 'DERIVED_SAMPLE', formula, evidence: `${prefix}:valuation:${key}:v1`, status: v === null ? 'BLOCKED' : 'READY', reason: v === null ? key === 'PB' ? '期末权益对应的股数口径未提供，不用当期市值股数或 EPS 加权股数替代' : '股息观察区间、币种与分配口径未定义，不能填零' : null,
        price_at: key === 'EPS' ? null : hk ? '2026-09-16T08:00:00Z' : '2026-09-16T20:00:00Z', price: key === 'EPS' ? null : price, report_id: annual.id, financial_period: annual.period_end,
        inputs: `固定价格 ${price} ${currency}；合成当期股数 ${shares} 百万股；FY2025 EPS 加权平均股数 ${shares} 百万股；${ci ? '期末权益对应股数未知' : `期末权益对应股数 ${shares} 百万股`}。独立样稿设定，不推断真实公司股本或除权。`,
      })) }
  })
  return validateFinancialPreview({ ...flags, market, trading_date: '2026-09-16', generated_at: '2026-09-17T07:00:00Z', companies,
    blockers: ['真实 HK/US 财报来源、币种/会计口径、发布日期/历史可得性和估值价格基准未在本页生产闭合', '本页不解除 Longbridge volume/VR20、split-only、finality、PIT/vintage 或正式 Universe blocker'],
    warnings: ['全部财务数字、报告日期、公告时间和价格为独立合成样稿，不是对应代码公司的真实财报', '年度为 FULL_YEAR，季度为 SINGLE_QUARTER；不从年初累计拆季，不插值，不做币种转换', 'READY 只限定样稿字段可展示；不表示真实供应商、财务风险模型或生产输入就绪'],
  })
}
