import { validateAnalysisPreview, type AnalysisMarket, type AnalysisPreviewData, type AnalysisSample } from '../../../src/custom/damon/stock-analysis-preview/contract'

const flags = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false, is_investment_signal: false, fixture_only: true, synthetic: true } as const
export function loadAnalysisPreview(market: AnalysisMarket): AnalysisPreviewData {
  // Authored examples, not downloaded quotes, account data, or computed indicators.
  const quotes = market === 'HK'
    ? [{ last: 102, change: 2, changePercent: 2, open: 100, high: 104, low: 99, previousClose: 100 },
      { last: 49, change: -1, changePercent: -2, open: 50, high: 51, low: 48, previousClose: 50 }]
    : [{ last: 204, change: 4, changePercent: 2, open: 200, high: 206, low: 198, previousClose: 200 },
      { last: null, change: null, changePercent: null, open: 75, high: 76, low: 73, previousClose: 75 }]
  const rows: AnalysisSample[] = (['A', 'B'] as const).map((letter, i) => ({
    ...flags, id: `fixture-stock-${market}-${letter}`, symbol: `SYNTH-${letter}.${market}`,
    name: `${market} 合成证券 ${letter}`, english_name: `${market} Synthetic Security ${letter}`, market,
    currency: market === 'HK' ? 'HKD' : 'USD', exchange: `${market}-SYNTHETIC-VENUE`, security_type: 'SYNTHETIC_SAMPLE',
    quote: quotes[i], technical: { ma20: i === 0 ? (market === 'HK' ? 98 : 196) : null, volume_ratio_20: null },
    unknown: { sector: null, industry: null, price_basis: null, volume_unit: null, available_at: null, source_vintage: null, production_report: null },
    missing_reasons: { last: '此合成样稿未定义参考价', change: '此合成样稿未定义涨跌额', changePercent: '此合成样稿未定义涨跌幅',
      ma20: '此样稿没有编写 MA20，不临时计算', volume_ratio_20: 'Volume/VR20 生产数量语义 BLOCKED；本样稿不提供量比',
      sector: '虚构证券没有真实行业归属', industry: '没有已验证的生产行业分类', price_basis: 'split-only 价格基础尚未闭合',
      volume_unit: '成交量单位未闭合', available_at: '没有已证明的上游可得时间；generated_at 仅为样稿编写时间',
      source_vintage: '没有历史 PIT/vintage 证据', production_report: '没有生成或读取真实研究报告' },
    evidence: `fixture:stock-analysis:${market}:${letter}:v1`, execution_status: 'BLOCKED',
    blockers: ['Volume/VR20、split-only、historical PIT/vintage、正式 Universe 仍 BLOCKED', 'Daily finality PARTIAL；corporate actions UNKNOWN'],
    warnings: ['所有报价及 MA20 均为独立编写的合成展示值；没有历史序列或生产计算', '不代表真实证券、真实行情或投资信号'],
  }))
  return validateAnalysisPreview({ ...flags, market, trading_date: '2026-09-16', generated_at: '2026-09-17T09:00:00Z', rows })
}
