import { validateFactorPreview, type FactorPreviewData, type FactorPreviewMarket, type FactorPreviewRow } from '../../../src/custom/damon/factor-preview/contract'

const flags = { status: 'PREVIEW', source: 'synthetic-fixture', data_mode: 'preview', is_production: false, is_investment_signal: false, fixture_only: true, synthetic: true } as const

/** Authored display values; no input bars, Factor registry, evaluation or production imports. */
export function loadFactorPreview(market: FactorPreviewMarket): FactorPreviewData {
  const rows: FactorPreviewRow[] = [0, 1, 2, 3].map(i => {
    const evidence = `fixture:factor:${market}:${i}:metadata:v1`
    return {
      ...flags, id: `fixture-factor-${market}-${i}`, version: i === 3 ? 'preview-v2' : 'preview-v1', market,
      label: `${market} ${['价格变化样稿', '波动观察样稿', '组合定义缺失样稿', '量能阻塞样稿'][i]}`,
      description: '独立手写合成因子元数据，不是 CN 因子注册表的副本；不运行公式或检验',
      kind: (['base', 'virtual', 'composite', 'custom'] as const)[i], group: i === 3 ? '量能样稿' : '价格样稿',
      direction: i === 1 ? 'low' : i === 2 ? 'none' : 'high',
      formula: i === 0 ? 'C_D / C_(D-5) - 1（仅展示文字，不求值）' : i === 1 ? 'sigma20：20个对数收益样本标准差，不年化（仅展示）' : null,
      unit: i < 2 ? 'fraction（合成值，不是实测结果）' : null,
      warmup_bars: i === 0 ? 6 : i === 1 ? 21 : null,
      dependencies: i === 0 ? ['close', 'exact calendar', 'completed bars', 'split-only price basis'] : i === 1 ? ['close', '20 log return observations', 'exact calendar', 'completed bars'] : null,
      sample_value: i === 0 ? market === 'HK' ? .035 : .052 : i === 1 ? market === 'HK' ? .018 : .024 : null,
      definition_status: (['READY', 'PARTIAL', 'UNAVAILABLE', 'BLOCKED'] as const)[i],
      validation_status: 'BLOCKED', execution_status: 'BLOCKED', pit: null, evaluated_at: null,
      ic_mean: null, ic_ir: null, coverage_count: null, universe_identity: null, input_contract_identity: null,
      sample_symbols: market === 'HK' ? ['0700.HK', '9988.HK'] : ['AAPL.US', 'MSFT.US'],
      missing_reasons: {
        formula: '没有已确认的样稿公式；不代选生产公式或合成权重', unit: '未定义数量单位，不猜测 shares / lots',
        warmup_bars: '未定义完整历史窗口', dependencies: '依赖未定义，不自动解析或补齐',
        sample_value: '未编写此项样稿值，保留 null，不填0或运行计算', pit: '历史 PIT / source vintage BLOCKED，未知不能标为已满足',
        evaluated_at: '没有真实检验任务；generated_at 是样稿编写时间', ic_mean: '没有实际因子检验结果',
        ic_ir: '没有实际 IC 序列，不计算 IR', coverage_count: '没有真实数据覆盖统计，固定样稿行数不是证券覆盖数',
        universe_identity: '未绑定正式 Universe 或历史 membership', input_contract_identity: '未绑定生产输入契约',
      }, evidence,
      blockers: ['Volume/VR20 BLOCKED；split-only BLOCKED；historical PIT/vintage BLOCKED；正式 Universe BLOCKED', 'Daily finality PARTIAL；corporate actions UNKNOWN；不运行 Factor producer 或解除 Input Gate'],
      warnings: ['READY 仅指样稿定义字段齐全，不代表生产因子、输入或执行 READY', '所有数值为固定合成展示值，不是 FactorSnapshot、排名、回测或投资信号'],
    }
  })
  return validateFactorPreview({ ...flags, market, trading_date: '2026-09-16', generated_at: '2026-09-17T09:00:00Z', rows })
}
