import type { IndexPreviewProvenance } from '../index-preview/contract'

export type MonitorMarket = 'HK' | 'US'
export type SampleState = 'NORMAL' | 'WARNING' | 'ERROR' | 'UNAVAILABLE'
export type SampleSeverity = 'INFO' | 'WARN' | 'CRITICAL'
export const sampleStateLabel: Record<SampleState, string> = { NORMAL: '正常样例', WARNING: '警告样例', ERROR: '异常样例', UNAVAILABLE: '不可用样例' }
interface SampleEvidence extends IndexPreviewProvenance {
  id: string
  market: MonitorMarket
  symbol: string
  evidence: string
  missing_fields: readonly string[]
  reasons: readonly string[]
}
export interface MonitorTaskSample extends SampleEvidence {
  name: string
  type: string
  sample_state: SampleState
  severity: SampleSeverity | null
  checked_at: string | null
  condition_description: string
  completeness: 'SAMPLE_COMPLETE' | 'SAMPLE_PARTIAL'
  blockers: readonly string[]
  warnings: readonly string[]
}
export interface MonitorAlertSample extends SampleEvidence {
  title: string
  category: string
  severity: SampleSeverity | null
  occurred_at: string
  sample_alert_state: 'OPEN_SAMPLE' | 'ACKNOWLEDGED_SAMPLE' | null
  condition_description: string
}
export interface MonitorPreviewData extends IndexPreviewProvenance {
  market: MonitorMarket
  trading_date: string
  generated_at: string
  updated_at: string | null
  updated_reason: string | null
  evidence: string
  tasks: readonly MonitorTaskSample[]
  alerts: readonly MonitorAlertSample[]
  /** Explicit fixture counts, never live worker or alert health. */
  counts: Record<'total' | SampleState, { value: number | null; reason: string | null }>
}
export type MonitorPreviewState = { kind: 'ready'; data: MonitorPreviewData } | { kind: 'loading' } | { kind: 'error' }
export function validateMonitorPreview(data: MonitorPreviewData): MonitorPreviewData {
  const preview = (v: IndexPreviewProvenance) => v.status === 'PREVIEW' && v.source === 'synthetic-fixture' && v.data_mode === 'preview'
    && v.is_production === false && v.is_investment_signal === false && v.fixture_only === true && v.synthetic === true
  const timestamp = (s: string) => /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(s) && Number.isFinite(Date.parse(s))
  if (!preview(data) || !['HK', 'US'].includes(data.market) || !/^\d{4}-\d{2}-\d{2}$/.test(data.trading_date)
    || !timestamp(data.generated_at) || !data.evidence) throw new Error('monitor_fixture_required')
  if (data.updated_at === null ? !data.updated_reason : !timestamp(data.updated_at)) throw new Error('monitor_update_evidence_required')
  for (const rows of [data.tasks, data.alerts]) {
    if (new Set(rows.map(r => r.id)).size !== rows.length) throw new Error('duplicate_monitor_sample')
    for (const row of rows) {
      if (!preview(row) || row.market !== data.market || !row.id.startsWith('fixture-') || !row.evidence.startsWith('fixture:')) throw new Error('mixed_monitor_sample')
      if (row.severity !== null && !['INFO', 'WARN', 'CRITICAL'].includes(row.severity)) throw new Error('invalid_sample_severity')
      if (row.missing_fields.length && !row.reasons.length) throw new Error('monitor_missing_reason_required')
    }
  }
  for (const task of data.tasks) {
    if (!Object.hasOwn(sampleStateLabel, task.sample_state)) throw new Error('invalid_sample_state')
    const missing = [task.severity === null ? 'severity' : '', task.checked_at === null ? 'checked_at' : ''].filter(Boolean)
    if (task.checked_at !== null && !timestamp(task.checked_at)) throw new Error('invalid_sample_check_time')
    if (missing.sort().join() !== [...task.missing_fields].sort().join() || (missing.length && !task.reasons.length)) throw new Error('monitor_missing_fields_conflict')
  }
  for (const alert of data.alerts) {
    if (!timestamp(alert.occurred_at) || ![null, 'OPEN_SAMPLE', 'ACKNOWLEDGED_SAMPLE'].includes(alert.sample_alert_state)) throw new Error('invalid_sample_alert')
    const missing = [alert.severity === null ? 'severity' : '', alert.sample_alert_state === null ? 'sample_alert_state' : ''].filter(Boolean)
    if (missing.sort().join() !== [...alert.missing_fields].sort().join() || (missing.length && !alert.reasons.length)) throw new Error('monitor_missing_fields_conflict')
  }
  for (const key of ['total', 'NORMAL', 'WARNING', 'ERROR', 'UNAVAILABLE'] as const) {
    const count = data.counts[key]
    const expected = key === 'total' ? data.tasks.length : data.tasks.filter(t => t.sample_state === key).length
    if (count.value === null ? !count.reason : !Number.isInteger(count.value) || count.value < 0 || count.value !== expected) throw new Error('invalid_monitor_sample_count')
  }
  return data
}
