// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { LongbridgeCredentials } from './LongbridgeCredentials'
import { SettingsDataSourcesPanel } from './DataSources'

const mock = vi.hoisted(() => ({
  status: { app_key_masked: '', app_secret_configured: false, access_token_configured: false, status: 'unconfigured' },
  save: vi.fn(), clear: vi.fn(), update: vi.fn(),
}))
vi.mock('@/lib/api', () => ({ api: {
  longbridgeCredentials: async () => mock.status,
  saveLongbridgeCredentials: mock.save, clearLongbridgeCredentials: mock.clear,
  updateDataProviders: mock.update,
  dataSources: async () => ({ builtin: [{ name: 'tickflow', display_name: 'TickFlow', datasets: ['realtime'] }],
    plugins: ['fuyao', 'stock-sdk', 'longbridge'].map(name => ({ name, display_name: name === 'longbridge' ? 'Longbridge' : name,
      datasets: ['realtime'], runtime: 'python', available: true, status: 'ok', description: '', install_hint: '' })), custom: [], errors: [] }),
  capabilityMatrix: async () => ({ capabilities: [{ id: 'realtime', label: '实时行情', tf_available: true, current: 'longbridge',
    candidates: [], pending: [], usable: true, field: 'realtime_data_provider', tf_tier: 'starter',
    default: 'tickflow', current_display: 'Longbridge', effective: 'longbridge', effective_display: 'Longbridge' }] }),
} }))
vi.mock('@/lib/useSharedQueries', () => ({ usePreferences: () => ({ data: { realtime_data_provider: 'longbridge' } }), useCapabilities: () => ({ data: { capabilities: {} } }) }))
vi.mock('./Keys', () => ({ TickFlowKeySection: () => null, TierHelpPopover: () => null, useInvalidateTierRelated: () => () => {} }))

let root: Root
let host: HTMLDivElement
let qc: QueryClient
beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  vi.clearAllMocks()
  mock.status = { app_key_masked: '', app_secret_configured: false, access_token_configured: false, status: 'unconfigured' }
  host = document.createElement('div'); document.body.appendChild(host)
  root = createRoot(host)
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})
afterEach(async () => { await act(async () => root.unmount()); qc.clear(); host.remove() })
async function render(panel = false) {
  await act(async () => { root.render(<QueryClientProvider client={qc}>{panel ? <SettingsDataSourcesPanel /> : <LongbridgeCredentials />}</QueryClientProvider>); await new Promise(resolve => setTimeout(resolve, 30)) })
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)) })
}
async function click(label: string) {
  const button = Array.from(host.querySelectorAll('button')).find(button => button.textContent === label)!
  expect(button).toBeTruthy()
  await act(async () => { button.click(); await new Promise(resolve => setTimeout(resolve, 20)) })
}
async function fill() {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  for (const input of host.querySelectorAll('input')) {
    await act(async () => { setter.call(input, 'fake-ui-secret-only'); input.dispatchEvent(new Event('input', { bubbles: true })) })
  }
}
it('renders all existing cards and Longbridge market/config/current indicators', async () => {
  await render(true)
  for (const name of ['TickFlow', 'fuyao', 'stock-sdk', 'Longbridge', 'CN / HK / US', '配置凭证', '已套用']) expect(host.textContent).toContain(name)
})
it('uses three password inputs without reveal and keeps candidate secrets out of browser storage/cache', async () => {
  await render(); await click('配置凭证')
  expect(host.querySelectorAll('input[type=password]')).toHaveLength(3)
  expect(host.textContent).toContain('仅用于本机 Longbridge OpenAPI 行情认证。')
  expect(host.textContent).not.toContain('查看明文')
  await fill()
  expect(JSON.stringify(qc.getQueryCache().getAll().map(query => query.state.data))).not.toContain('fake-ui-secret-only')
  expect(JSON.stringify(localStorage)).not.toContain('fake-ui-secret-only')
  expect(JSON.stringify(sessionStorage)).not.toContain('fake-ui-secret-only')
  await click('取消'); await click('配置凭证')
  expect(Array.from(host.querySelectorAll('input')).every(input => input.value === '')).toBe(true)
})
it('failed probe keeps dialog open and shows authentication failure', async () => {
  mock.save.mockResolvedValue({ ok: false, reason: 'authentication' })
  await render(); await click('配置凭证'); await fill(); await click('验证并保存')
  expect(mock.save).toHaveBeenCalledWith({ app_key: 'fake-ui-secret-only', app_secret: 'fake-ui-secret-only', access_token: 'fake-ui-secret-only' })
  expect(host.querySelector('[role=dialog]')).not.toBeNull()
  expect(host.textContent).toContain('认证失败')
})
it('successful probe closes dialog and refreshes masked status', async () => {
  mock.save.mockImplementation(async () => {
    mock.status = { app_key_masked: 'fake••••1234', app_secret_configured: true, access_token_configured: true, status: 'available' }
    return { ok: true }
  })
  await render(); await click('配置凭证'); await fill(); await click('验证并保存')
  expect(host.querySelector('[role=dialog]')).toBeNull()
  expect(host.textContent).toContain('可用')
  expect(host.textContent).toContain('APP SECRET: 已配置')
  expect(host.textContent).toContain('ACCESS TOKEN: 已配置')
  expect(host.textContent).not.toContain('fake-ui-secret-only')
})
