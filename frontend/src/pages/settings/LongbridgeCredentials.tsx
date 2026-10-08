import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Modal } from '@/components/Modal'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

const statusLabels: Record<string, string> = {
  unconfigured: '未配置', sdk_missing: 'SDK缺失', available: '可用',
  authentication: '认证失败', quote_permission: '不可用：行情权限不足',
  network: '不可用：网络连接失败', storage_error: '不可用：保存失败',
  reload_failed: '凭证已保存，数据源重载失败',
}

export function LongbridgeCredentials() {
  const qc = useQueryClient()
  const status = useQuery({ queryKey: QK.longbridgeCredentials, queryFn: api.longbridgeCredentials })
  const [open, setOpen] = useState(false)
  const [fields, setFields] = useState({ app_key: '', app_secret: '', access_token: '' })
  const [pending, setPending] = useState(false)
  const [reason, setReason] = useState('')
  const reset = () => { setOpen(false); setFields({ app_key: '', app_secret: '', access_token: '' }) }
  const invalidate = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: QK.longbridgeCredentials }),
      qc.invalidateQueries({ queryKey: QK.dataSources }),
      qc.invalidateQueries({ queryKey: QK.capabilityMatrix }),
      qc.invalidateQueries({ queryKey: QK.capabilities }),
      qc.invalidateQueries({ queryKey: QK.quoteStatus }),
    ])
  }
  const save = async () => {
    setPending(true)
    setReason('')
    try {
      const result = await api.saveLongbridgeCredentials(fields)
      if (result.ok) {
        reset()
        await invalidate()
        setReason(result.reason || '')
      } else setReason(result.reason || 'unavailable')
    } catch { setReason('network') }
    finally { setPending(false) }
  }
  const clear = async () => {
    setPending(true)
    try { await api.clearLongbridgeCredentials(); setReason(''); await invalidate() }
    catch { setReason('storage_error') }
    finally { setPending(false) }
  }
  const label = pending ? '验证中' : statusLabels[reason || status.data?.status || 'unconfigured'] || '不可用'
  return (
    <div className="mt-2 text-xs" onClick={event => event.stopPropagation()}>
      <div className="flex items-center gap-2">
        <span role="status" className="text-secondary">{label}</span>
        <button type="button" className="rounded px-2 py-1 bg-accent/10 text-accent" disabled={pending} onClick={() => setOpen(true)}>配置凭证</button>
      </div>
      {status.data?.app_key_masked && <div className="mt-2 text-secondary font-mono">APP KEY: {status.data.app_key_masked}</div>}
      {status.data?.app_secret_configured && <div className="text-secondary">APP SECRET: 已配置</div>}
      {status.data?.access_token_configured && <div className="text-secondary">ACCESS TOKEN: 已配置</div>}
      {status.data?.app_key_masked && <button type="button" disabled={pending} className="mt-2 text-muted hover:text-danger" onClick={clear}>清除凭证</button>}
      {open && <Modal ariaLabel="Longbridge 凭证配置" onClose={() => { if (!pending) reset() }}>
        <div className="p-5 space-y-4">
          <h3 className="font-medium">Longbridge 行情凭证</h3>
          {([['app_key', 'App Key'], ['app_secret', 'App Secret'], ['access_token', 'Access Token']] as const).map(([key, name]) => (
            <label key={key} className="block text-xs text-secondary">
              {name}
              <input aria-label={name} type="password" autoComplete="new-password" value={fields[key]} disabled={pending}
                onChange={event => setFields(previous => ({ ...previous, [key]: event.target.value }))}
                className="mt-1 block w-full rounded border border-border bg-elevated px-3 py-2 text-foreground" />
              {key === 'access_token' && <span className="mt-1 block text-muted">仅用于本机 Longbridge OpenAPI 行情认证。</span>}
            </label>
          ))}
          <p className="text-xs text-muted">先验证行情权限，成功后保存到本机。清除本地凭证后，已有环境配置仍可生效。</p>
          <div className="text-xs text-secondary" role="status">{label}</div>
          <div className="flex justify-end gap-2">
            <button type="button" disabled={pending} onClick={reset}>取消</button>
            <button type="button" disabled={pending || Object.values(fields).some(value => !value.trim())}
              className="rounded bg-accent/10 px-3 py-2 text-accent disabled:opacity-50" onClick={save}>验证并保存</button>
          </div>
        </div>
      </Modal>}
    </div>
  )
}
