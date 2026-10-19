export type PreviewNoticeProps = {
  statement: string
  description: string
  className?: string
}

export type PreviewDisabledActionProps = {
  label: string
  reason: string
  className?: string
}

export function PreviewNotice({ statement, description, className = 'rounded-xl border border-warning/30 bg-warning/5 p-4 text-sm text-warning' }: PreviewNoticeProps) {
  return <div role="note" className={className}><strong>{statement}</strong><p>{description}</p></div>
}

export function PreviewDisabledAction({ label, reason, className = 'rounded-btn border border-border px-3 py-1 text-xs text-muted' }: PreviewDisabledActionProps) {
  return <button type="button" disabled title={reason} className={className}>{label}（Preview 不可执行）</button>
}
