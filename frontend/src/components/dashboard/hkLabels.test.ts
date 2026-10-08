import { expect, it } from 'vitest'
import { getUnmappedHKLabels, HK_MODE_LABELS, hkIndustry, hkReason, hkStockName } from './hkLabels'

it.each([
  ['LIVE', '实时'], ['DAILY', '日频'], ['DERIVED', '派生'], ['UNAVAILABLE', '暂不可用'],
] as const)('localizes %s to %s', (mode, expected) => {
  expect(HK_MODE_LABELS[mode]).toBe(expected)
})
it('prefers an official Chinese reason, maps only known English, and records unknown originals', () => {
  expect(hkReason('Volatility exceeds 20-day avg')).toBe('波动率超过20日均值')
  expect(hkReason('Volatility exceeds 20-day avg', '官方中文原因')).toBe('官方中文原因')
  expect(hkReason('New official alert')).toBe('New official alert')
  expect(hkReason('constructor')).toBe('constructor')
  expect(hkIndustry('__proto__')).toBe('__proto__')
  expect(getUnmappedHKLabels()).toContainEqual({ kind: 'reason', text: 'New official alert' })
})
it('uses official names without translating company names', () => {
  expect(hkStockName({ name_cn: '美联集团', name_en: 'Midland Holdings', symbol: '1200.HK' })).toBe('美联集团')
  expect(hkStockName({ name_cn: '', name_en: 'Midland Holdings', symbol: '1200.HK' })).toBe('Midland Holdings')
  expect(hkStockName({ symbol: '1200.HK' })).toBe('1200.HK')
  expect(hkStockName({ name: 'Midland Holdings', symbol: '1200.HK' }, { name: '美联集团' })).toBe('美联集团')
})
it('prefers official Chinese industry, otherwise uses explicit mappings or the unchanged source', () => {
  expect(hkIndustry('Real Estate Services', '官方中文行业')).toBe('官方中文行业')
  expect(hkIndustry('Real Estate Services')).toBe('房地产服务')
  expect(hkIndustry('Media')).toBe('媒体')
  expect(hkIndustry('New Industry')).toBe('New Industry')
  expect(hkIndustry('官方中文行业')).toBe('官方中文行业')
})
it('bounds unknown-label diagnostics without changing fallback display', () => {
  for (let i = 0; i < 110; i++) expect(hkReason(`Unknown ${i}`)).toBe(`Unknown ${i}`)
  expect(getUnmappedHKLabels().length).toBeLessThanOrEqual(100)
})
