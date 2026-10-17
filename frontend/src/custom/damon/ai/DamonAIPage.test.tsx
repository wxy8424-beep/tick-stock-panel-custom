// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { DamonAIPage } from './DamonAIPage'
import extension from '../extension'
import { ExtensionBoundary } from '@/extensions/ExtensionBoundary'
import { finalizeFrontendExtensions, getFrontendExtensionRoutes, loadFrontendExtensions } from '@/extensions/registry'

let host: HTMLDivElement, root: Root
const network = vi.fn(), microphone = vi.fn()
beforeEach(() => {
  vi.useFakeTimers(); network.mockClear(); microphone.mockClear()
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.stubGlobal('fetch', network)
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: microphone } })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.useRealTimers() })
const button = (label: string) => [...host.querySelectorAll('button')].find(b => b.textContent === label)!
async function click(label: string) { await act(async () => button(label).click()) }
async function render() { await act(async () => root.render(<DamonAIPage />)) }
async function send(text = '演示问题') {
  const textarea = host.querySelector('textarea')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(textarea, text)
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
}
it('adds a unique extension route and preserves anomalies without claiming the homepage', async () => {
  expect(extension.routes?.map(r => r.path)).toEqual(['/anomalies', '/damon/ai'])
  expect(extension.navigation?.map(n => n.routeId)).toEqual(['damon-anomalies', 'damon-ai'])
  await loadFrontendExtensions({ damon: async () => ({ default: extension }) })
  finalizeFrontendExtensions(new Set(['/']))
  expect(getFrontendExtensionRoutes().map(r => r.path).sort()).toEqual(['/anomalies', '/damon/ai'])
})
it('renders all mock states, transcript, retained messages, stop and safe errors without I/O', async () => {
  await render(); expect(host.querySelector('[role="status"]')?.textContent).toBe('空闲')
  await click('开始演示会话'); await click('模拟聆听')
  expect(host.querySelector('[role="status"]')?.textContent).toBe('聆听演示')
  await send(); expect(host.querySelector('[role="status"]')?.textContent).toBe('思考演示')
  await act(async () => vi.advanceTimersByTime(700))
  expect(host.querySelector('[role="status"]')?.textContent).toBe('播报演示')
  expect(host.textContent).toContain('演示转写（来自文字输入）：演示问题')
  await click('停止播报'); expect(host.querySelector('[role="status"]')?.textContent).toBe('已停止')
  await send('第二轮'); await click('停止任务')
  await act(async () => vi.runAllTimers())
  expect(host.querySelector('[role="status"]')?.textContent).toBe('已停止')
  expect(host.textContent).toContain('这是离线演示回复')
  await click('模拟连接错误'); expect(host.querySelector('[role="alert"]')?.textContent).toContain('mock-offline')
  expect(button('模拟聆听').disabled).toBe(true)
  expect(button('发送演示消息').disabled).toBe(true)
  expect(host.textContent).toContain('未开始')
  await click('开始演示会话'); await click('结束会话')
  expect(network).not.toHaveBeenCalled(); expect(microphone).not.toHaveBeenCalled()
})
it('retains the final accumulated reply after completion and disposes in-flight work on unmount', async () => {
  await render(); await click('开始演示会话'); await send()
  await act(async () => vi.advanceTimersByTime(1600))
  expect(host.querySelector('[role="status"]')?.textContent).toBe('空闲')
  const replies = [...host.querySelectorAll('article')].filter(article => article.textContent?.includes('Damon · 演示回复'))
  expect(replies).toHaveLength(1)
  expect(replies[0].textContent).toContain('没有查询行情或生成生产证据。')
  await send('在途问题')
  expect(vi.getTimerCount()).toBeGreaterThan(0)
  await act(async () => root.render(<p>已离开</p>))
  expect(vi.getTimerCount()).toBe(0)
  await act(async () => vi.runAllTimers())
  expect(host.textContent).toBe('已离开')
  expect(network).not.toHaveBeenCalled(); expect(microphone).not.toHaveBeenCalled()
})
it('keeps market and preview labels explicit and cancels context-bound work', async () => {
  await render(); await click('开始演示会话'); await send()
  await click('港股')
  expect(host.querySelector('[role="status"]')?.textContent).toBe('已停止')
  const select = host.querySelector<HTMLSelectElement>('[aria-label="数据模式"]')!
  await act(async () => { select.value = 'preview'; select.dispatchEvent(new Event('change', { bubbles: true })) })
  expect(host.querySelector('[aria-label="证据摘要"]')?.textContent).toContain('HK · 合成 Preview')
  expect(host.textContent).toContain('不能标记为生产证据')
  await act(async () => vi.runAllTimers())
  expect(host.textContent).not.toContain('这是离线演示回复')
})
it('provides narrow-screen panels, keyboard form controls and a motion preference', async () => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 375 })
  await render(); await click('任务与证据')
  expect(button('任务与证据').getAttribute('aria-pressed')).toBe('true')
  expect(host.querySelector('[aria-label="文字对话"]')?.className).toContain('hidden lg:block')
  await click('对话'); await click('开始演示会话')
  const input = host.querySelector('textarea')!
  input.focus(); expect(document.activeElement).toBe(input)
  expect(input.id).toBe('damon-input')
  const checkbox = host.querySelector<HTMLInputElement>('input[type="checkbox"]')!
  await act(async () => checkbox.click()); expect(checkbox.checked).toBe(true)
  expect(host.textContent).toContain('麦克风未开启')
})
it('Enter sends via the form and Shift+Enter preserves multiline input', async () => {
  await render(); await click('开始演示会话')
  const input = host.querySelector('textarea')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(input, '键盘输入')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  const submit = vi.fn(() => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  Object.defineProperty(host.querySelector('form'), 'requestSubmit', { value: submit })
  await act(async () => input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true })))
  expect(submit).not.toHaveBeenCalled()
  await act(async () => input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
  expect(submit).toHaveBeenCalledOnce()
  expect(host.querySelector('[aria-label="消息历史"]')?.textContent).toContain('键盘输入')
})
it('the host extension boundary contains a page failure without unmounting adjacent content', async () => {
  const error = vi.spyOn(console, 'error').mockImplementation(() => {})
  function Broken(): never { throw new Error('mock render failure') }
  await act(async () => root.render(<><p>原有页面</p><ExtensionBoundary extensionId={extension.id}><Broken /></ExtensionBoundary></>))
  expect(host.textContent).toContain('原有页面')
  expect(host.textContent).toContain('暂时不可用')
  error.mockRestore()
})
