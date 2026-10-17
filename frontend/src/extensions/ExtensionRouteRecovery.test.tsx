// @vitest-environment jsdom
import { act } from 'react'
import { transferableAbortController } from 'node:util'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { expect, it, vi } from 'vitest'

vi.mock('@/components/Layout', async () => {
  const { Outlet } = await import('react-router-dom')
  return { Layout: () => <Outlet /> }
})
vi.mock('@/lib/useSharedQueries', () => ({ useSettings: () => ({ data: { onboarding_completed: true } }) }))
vi.mock('@/pages/Dashboard', () => ({ Dashboard: () => <p>原 Dashboard</p> }))
vi.mock('@/extensions/registry', async () => {
  const { useState } = await import('react')
  function Damon() {
    const [broken, setBroken] = useState(false)
    if (broken) throw new Error('offline render failure')
    return <button onClick={() => setBroken(true)}>Damon AI 正常 · 触发错误</button>
  }
  return {
    finalizeFrontendExtensions: () => {}, getFrontendExtensionLoadErrors: () => [],
    getFrontendExtensionRoutes: () => [
      { id: 'damon-ai', path: '/damon/ai', extensionId: 'damon.anomaly-monitoring', component: Damon },
      { id: 'damon-anomalies', path: '/anomalies', extensionId: 'damon.anomaly-monitoring', component: () => <p>异动页已恢复</p> },
    ],
  }
})

it('recovers through the real router from failed Damon to anomalies and preserves core redirects', async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  // The router uses Node's native Request, which requires a same-realm signal.
  vi.stubGlobal('AbortController', class { constructor() { return transferableAbortController() } })
  const error = vi.spyOn(console, 'error').mockImplementation(() => {})
  const host = document.createElement('div'); document.body.append(host)
  const root = createRoot(host)
  const { router } = await import('@/router')
  try {
    await router.navigate('/damon/ai')
    await act(async () => root.render(<RouterProvider router={router} />))
    expect(host.textContent).toContain('Damon AI 正常')
    await act(async () => host.querySelector('button')!.click())
    expect(host.textContent).toContain('暂时不可用')
    await act(async () => { await router.navigate('/anomalies') })
    expect(host.textContent).toBe('异动页已恢复')
    await act(async () => { await router.navigate('/damon/ai') })
    expect(host.textContent).toContain('Damon AI 正常')
    await act(async () => { await router.navigate('/overview') })
    expect(router.state.location.pathname).toBe('/')
    expect(host.textContent).toBe('原 Dashboard')
  } finally {
    await act(async () => root.unmount())
    router.dispose(); host.remove(); error.mockRestore(); vi.unstubAllGlobals()
  }
})
