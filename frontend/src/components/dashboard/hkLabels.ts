import type { HKRow, HKSection } from '@/lib/api'

export const HK_MODE_LABELS: Record<HKSection['mode'], string> = {
  LIVE: '实时', DAILY: '日频', DERIVED: '派生', UNAVAILABLE: '暂不可用',
}
const reasons: Record<string, string> = {
  'Volatility exceeds 20-day avg': '波动率超过20日均值',
}
const industries: Record<string, string> = {
  'Real Estate Services': '房地产服务',
  Media: '媒体',
}
const errors: Record<string, string> = {
  authentication: '认证失败', quote_permission: '行情权限不足',
  network: '网络连接失败', symbol: '股票代码不可用',
  sdk_or_response: '行情服务或响应异常',
}
const text = (value: unknown) => typeof value === 'string' ? value.trim() : ''

// Only source labels are recorded, in memory; bounded and never persisted.
const unmapped = new Map<string, { kind: 'reason' | 'industry'; text: string }>()
function mapped(kind: 'reason' | 'industry', value: unknown, chinese?: unknown): string {
  const preferred = text(chinese)
  if (preferred) return preferred
  const original = text(value)
  const labels = kind === 'reason' ? reasons : industries
  const translated = Object.hasOwn(labels, original) ? labels[original] : undefined
  if (translated) return translated
  if (/[A-Za-z]/.test(original) && !/[\u3400-\u9fff]/.test(original)) {
    const key = `${kind}:${original.slice(0, 256)}`
    if (!unmapped.has(key) && unmapped.size < 100) unmapped.set(key, { kind, text: original.slice(0, 256) })
  }
  return original
}
export const hkReason = (value: unknown, chinese?: unknown) => mapped('reason', value, chinese)
export const hkIndustry = (value: unknown, chinese?: unknown) => mapped('industry', value, chinese)
export const getUnmappedHKLabels = () => Array.from(unmapped.values(), value => ({ ...value }))
export const hkError = (value: string | null | undefined) => value ? Object.hasOwn(errors, value) ? errors[value] : value : ''

/** Metadata.name is already selected from official name_cn -> name_en by the API. */
export function hkStockName(row: HKRow, metadata?: HKRow): string {
  return text(row.name_cn) || text(metadata?.name_cn) || text(metadata?.name)
    || text(row.name_en) || text(metadata?.name_en) || text(row.name) || text(row.symbol) || '—'
}
