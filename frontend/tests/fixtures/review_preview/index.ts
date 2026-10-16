/** Authored synthetic recap examples, not AI output, archived reports or market evidence. */
import { validateReviewPreview, type ReviewMarket, type ReviewObservation, type ReviewPreviewData } from '../../../src/custom/damon/review-preview/contract'
const provenance = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false,
  is_investment_signal: false, fixture_only: true, synthetic: true } as const
export function loadReviewPreview(market: ReviewMarket): ReviewPreviewData {
  const names = market === 'HK' ? [['HSI', '恒生指数', 'INDEX'], ['HSTECH', '恒生科技指数', 'INDEX'],
    ['0700.HK', '腾讯控股', 'STOCK'], ['9988.HK', '阿里巴巴', 'STOCK'], ['3690.HK', '美团', 'STOCK']]
    : [['SPX', 'S&P 500', 'INDEX'], ['IXIC', 'Nasdaq Composite', 'INDEX'], ['DJI', 'Dow Jones Industrial Average', 'INDEX'],
      ['AAPL.US', 'Apple', 'STOCK'], ['NVDA.US', 'NVIDIA', 'STOCK'], ['MSFT.US', 'Microsoft', 'STOCK']]
  return validateReviewPreview({ ...provenance, market, reports: ['2026-09-16', '2026-09-15'].map((day, dayIndex) => {
    const rows: ReviewObservation[] = names.map(([symbol, name, kind], index) => ({
      ...provenance, market, symbol, name, kind: kind as 'INDEX' | 'STOCK',
      change_pct: index === names.length - 1 ? null : index === 0 ? (dayIndex === 0 ? .012 : .008) : index === 1 ? -.01 : 0,
      turnover: index === names.length - 1 ? null : 10000000,
      turnover_unit: index === names.length - 1 ? null : `${market === 'HK' ? 'HKD' : 'USD'}（合成）`,
      missing_reason: index === names.length - 1 ? '本演示未提供涨跌幅/成交额；不补零、不推断真实表现' : null,
      evidence_reference: `fixture:review:${market}:${day}:${symbol}:v1`,
    }))
    return { ...provenance, id: `fixture-review-${market}-${day}`, market, trading_date: day,
      title: `${market === 'HK' ? '港股' : '美股'}复盘样稿 · ${day}`,
      summary: `${market} 独立合成样稿；仅用于报告、列表和缺失状态的界面验收。`,
      content: `## ${market === 'HK' ? '港股' : '美股'}演示复盘\n\n这是固定编写的 synthetic fixture，**不是 AI 生成，也不描述真实盘面**。\n\n### 样本观察\n\n- 列表演示指数与股票的独立展示、筛选和排序。\n- 仅为合成展示集合，不代表全市场覆盖或市场广度。\n- ${day} 是固定 Preview 日期，不证明供应商日线已最终定版。\n\n### 证据缺口\n\n成交量口径、split-only、finality、PIT/vintage 与正式 Universe 等生产 blocker 不因本页展示而解除。主题/催化剂暂无可靠数据，不作推断。\n\n### 使用限制\n\n不提供真实排名、买卖建议或投资信号；不保存报告、不推送、不自动执行生产任务。`,
      generated_at: dayIndex === 0 ? '2026-09-17T00:00:00Z' : '2026-09-16T00:00:00Z', available_at: null, rows }
  }) })
}
