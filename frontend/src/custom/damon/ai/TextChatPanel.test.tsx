// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, cancelDamonChat, streamDamonChat } from '@/lib/api'
import { TextChatPanel } from './TextChatPanel'
import { DamonAIPage } from './DamonAIPage'

vi.mock('@/lib/api', () => ({ api: { damonProfiles: vi.fn() }, streamDamonChat: vi.fn(), cancelDamonChat: vi.fn() }))
let host: HTMLDivElement, root: Root, query: QueryClient
beforeEach(async () => {
  vi.clearAllMocks()
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.mocked(api.damonProfiles).mockResolvedValue({ profiles: ['alpha', 'beta'].map(profile_id => ({ profile_id,
    display_name: profile_id, model: profile_id, protocol: 'chat_completions', enabled: true, text_stream: true, configured: true })) })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  query = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  await act(async () => { root.render(<QueryClientProvider client={query}><TextChatPanel /></QueryClientProvider>) })
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
})
afterEach(async () => {
  await act(async () => root.unmount()); query.clear(); host.remove()
  vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks()
})
const button = (text: string) => [...host.querySelectorAll('button')].find(b => b.textContent === text)!
async function send(text: string) {
  const input = host.querySelector('textarea')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(input, text)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
}
const envelope = { conversation_id: 'a'.repeat(32), turn_id: 'b'.repeat(32), request_id: 'c'.repeat(32) }
it('commits a validated done and becomes idle even if the response never sends EOF', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  const cancel = vi.fn()
  const events = [{ ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 },
    { ...envelope, type: 'delta', text: 'complete reply', sequence: 2 },
    { ...envelope, type: 'done', code: 'completed', sequence: 3 }]
  const body = new ReadableStream<Uint8Array>({ start(controller) {
    controller.enqueue(new TextEncoder().encode(events.map(e => JSON.stringify(e) + '\n').join('')))
  }, cancel })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body)))
  vi.mocked(streamDamonChat).mockImplementation(actual.streamDamonChat)
  vi.useFakeTimers()
  await send('complete question')
  expect(host.textContent).toContain('就绪')
  expect(host.textContent).toContain('complete reply')
  expect(cancel).toHaveBeenCalledOnce()
  expect(body.locked).toBe(false)
  expect(vi.getTimerCount()).toBe(0)
  vi.mocked(streamDamonChat).mockResolvedValue()
  await send('next question')
  expect(vi.mocked(streamDamonChat).mock.calls[1][0].messages).toEqual([
    { role: 'user', content: 'complete question' }, { role: 'assistant', content: 'complete reply' },
    { role: 'user', content: 'next question' },
  ])
})

function holdTurn() {
  let receive!: (event: unknown) => void, finish!: () => void
  vi.mocked(streamDamonChat).mockImplementation(async (_input, _signal, callback) => {
    receive = callback
    callback({ ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 })
    callback({ ...envelope, type: 'delta', text: 'partial reply', sequence: 2 })
    await new Promise<void>(resolve => { finish = resolve })
  })
  return { emit: (event: unknown) => receive(event), finish: () => finish() }
}

it('retires a local timeout before abort, fences late events and excludes failed history', async () => {
  vi.useFakeTimers()
  const held = holdTurn()
  await send('local timeout question')
  const signal = vi.mocked(streamDamonChat).mock.calls[0][1]
  const atAbort = vi.fn(() => {
    held.emit({ ...envelope, type: 'done', code: 'completed', sequence: 3 })
  })
  signal.addEventListener('abort', atAbort, { once: true })
  await act(async () => { await vi.advanceTimersByTimeAsync(69999) })
  expect(signal.aborted).toBe(false)
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  expect(signal.aborted).toBe(true)
  expect(atAbort).toHaveBeenCalledOnce()
  expect(host.textContent).toContain('浏览器本地超时（70 秒）')
  expect(host.textContent).toContain('生成错误')
  expect(vi.getTimerCount()).toBe(0)
  await act(async () => {
    held.emit({ ...envelope, type: 'delta', text: 'LATE_TIMEOUT_TEXT', sequence: 4 })
    held.emit({ ...envelope, type: 'done', code: 'completed', sequence: 5 })
    held.finish()
  })
  expect(host.textContent).not.toContain('LATE_TIMEOUT_TEXT')
  expect(host.textContent).toContain('浏览器本地超时')
  vi.mocked(streamDamonChat).mockResolvedValue()
  await send('retry after timeout')
  expect(vi.mocked(streamDamonChat).mock.calls[1][0].messages)
    .toEqual([{ role: 'user', content: 'retry after timeout' }])
})

it.each(['timeout', 'upstream_error'] as const)('preserves the server terminal instead of local timeout: %s', async code => {
  vi.useFakeTimers()
  vi.mocked(streamDamonChat).mockImplementation(async (_input, _signal, receive) => {
    receive({ ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 })
    receive({ ...envelope, type: 'error', code, sequence: 2 })
  })
  await send('server error')
  expect(host.textContent).toContain(code === 'timeout' ? '服务端超时' : '上游服务错误')
  expect(vi.getTimerCount()).toBe(0)
  await act(async () => { await vi.advanceTimersByTimeAsync(70000) })
  expect(host.textContent).not.toContain('浏览器本地超时')
})

it.each(['stop', 'timeout'] as const)('chooses one terminal when stop races with timeout: %s first', async first => {
  vi.useFakeTimers()
  const held = holdTurn()
  vi.mocked(cancelDamonChat).mockResolvedValue({ cleanup_state: 'finished' })
  await send('race')
  await act(async () => { await vi.advanceTimersByTimeAsync(69999) })
  if (first === 'stop') {
    await act(async () => button('停止生成').click())
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    expect(host.textContent).toContain('上游请求已退出')
    expect(host.textContent).not.toContain('生成失败')
    expect(cancelDamonChat).toHaveBeenCalledOnce()
  } else {
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    await act(async () => button('停止生成').click())
    expect(host.textContent).toContain('浏览器本地超时')
    expect(host.textContent).not.toContain('上游请求已退出')
    expect(cancelDamonChat).not.toHaveBeenCalled()
  }
  await act(async () => held.finish())
  expect(vi.getTimerCount()).toBe(0)
})

it.each(['network', 'http'] as const)('classifies a rejected request, retires its turn and clears the deadline: %s', async failure => {
  vi.useFakeTimers()
  let receive!: (event: unknown) => void
  vi.mocked(streamDamonChat).mockImplementation(async (_input, _signal, callback) => {
    receive = callback
    callback({ ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 })
    if (failure === 'http') throw new Error('request_failed_403')
    throw new TypeError('FAKE_PRIVATE_NETWORK_ERROR')
  })
  await send('connection failure')
  await act(async () => receive({ ...envelope, type: 'delta', text: 'LATE_NETWORK_TEXT', sequence: 2 }))
  expect(host.textContent).toContain(failure === 'http' ? '服务端请求错误' : '连接错误')
  expect(host.textContent).not.toContain('FAKE_PRIVATE_NETWORK_ERROR')
  expect(host.textContent).not.toContain('LATE_NETWORK_TEXT')
  expect(vi.getTimerCount()).toBe(0)
})

it('cancels and releases the actual NDJSON reader when the local deadline aborts', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  let source!: ReadableStreamDefaultController<Uint8Array>
  const body = new ReadableStream<Uint8Array>({ start(controller) {
    source = controller
    controller.enqueue(new TextEncoder().encode(JSON.stringify({ ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 }) + '\n'))
  } })
  const response = new Response(body)
  const reader = body.getReader()
  vi.spyOn(body, 'getReader').mockReturnValue(reader)
  const cancel = vi.spyOn(reader, 'cancel'), release = vi.spyOn(reader, 'releaseLock')
  vi.stubGlobal('fetch', vi.fn(async (_url, options: RequestInit) => {
    options.signal!.addEventListener('abort', () => source.error(new DOMException('aborted', 'AbortError')), { once: true })
    return response
  }))
  vi.mocked(streamDamonChat).mockImplementation(actual.streamDamonChat)
  vi.useFakeTimers()
  await send('reader timeout')
  await act(async () => { await vi.advanceTimersByTimeAsync(70000) })
  expect(host.textContent).toContain('浏览器本地超时')
  expect(cancel).toHaveBeenCalled()
  expect(release).toHaveBeenCalledOnce()
  expect(body.locked).toBe(false)
  expect(vi.getTimerCount()).toBe(0)
})

it('aborts an overflowing turn, ignores late events and never sends partial history on retry', async () => {
  let receive!: (event: unknown) => void
  vi.mocked(streamDamonChat).mockImplementation(async (_input, _signal, callback) => {
    receive = callback
    callback({ ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 })
    callback({ ...envelope, type: 'delta', text: 'partial', sequence: 2 })
    callback({ ...envelope, type: 'delta', text: '😀'.repeat(16000), sequence: 3 })
    callback({ ...envelope, type: 'done', code: 'completed', sequence: 4 })
  })
  await send('overflow question')
  expect(vi.mocked(streamDamonChat).mock.calls[0][1].aborted).toBe(true)
  expect(host.textContent).toContain('正文超过 16000 Unicode 码点上限')
  await act(async () => {
    receive({ ...envelope, type: 'delta', text: 'LATE_TEXT', sequence: 5 })
    receive({ ...envelope, type: 'done', code: 'completed', sequence: 6 })
  })
  expect(host.textContent).not.toContain('LATE_TEXT')
  expect(host.textContent).toContain('生成错误')
  vi.mocked(streamDamonChat).mockResolvedValue()
  await send('retry question')
  expect(vi.mocked(streamDamonChat).mock.calls[1][0].messages)
    .toEqual([{ role: 'user', content: 'retry question' }])
})

it('streams deltas, pins an active profile and sends only completed history to the next turn', async () => {
  let finish!: () => void
  vi.mocked(streamDamonChat).mockImplementation(async (input, _signal, receive) => {
    receive({ ...envelope, type: 'start', profile_id: input.profile_id, sequence: 1 })
    receive({ ...envelope, type: 'delta', text: 'first', sequence: 2 })
    await new Promise<void>(resolve => { finish = resolve })
    receive({ ...envelope, type: 'delta', text: ' second', sequence: 3 })
    receive({ ...envelope, type: 'done', code: 'completed', sequence: 4 })
  })
  await send('question')
  expect(host.textContent).toContain('本轮固定模型：alpha')
  await act(async () => {
    const select = host.querySelector('select')!
    select.value = 'beta'; select.dispatchEvent(new Event('change', { bubbles: true }))
  })
  expect(host.textContent).toContain('本轮固定模型：alpha')
  await act(async () => finish())
  expect(host.textContent).toContain('first second')
  vi.mocked(streamDamonChat).mockResolvedValue()
  await send('next')
  const next = vi.mocked(streamDamonChat).mock.calls[1][0]
  expect(next.profile_id).toBe('beta')
  expect(next.conversation_id).toBe(envelope.conversation_id)
  expect(next.messages).toEqual([{ role: 'user', content: 'question' }, { role: 'assistant', content: 'first second' }, { role: 'user', content: 'next' }])
  expect(host.textContent).toContain('生成失败') // EOF without done is never success.
})
it.each(['still_running', 'unexpected'] as const)('retires before stopping and only reports verified cleanup states: %s', async cleanup => {
  let receive!: (event: unknown) => void, finish!: () => void
  vi.mocked(streamDamonChat).mockImplementation(async (_input, _signal, callback) => {
    receive = callback
    receive({ ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 })
    await new Promise<void>(resolve => { finish = resolve })
  })
  vi.mocked(cancelDamonChat).mockResolvedValue({ cleanup_state: cleanup } as never)
  await send('stop')
  const signal = vi.mocked(streamDamonChat).mock.calls[0][1]
  await act(async () => button('停止生成').click())
  expect(signal.aborted).toBe(true)
  await act(async () => { receive({ ...envelope, type: 'delta', text: 'LATE_CONTENT', sequence: 9 }); finish() })
  expect(host.textContent).not.toContain('LATE_CONTENT')
  expect(host.textContent).toContain(cleanup === 'still_running' ? '上游清理未完成' : '上游退出状态未确认')
  expect(host.textContent).not.toContain('上游请求已退出')
  expect(button('发送文字').disabled).toBe(false)
})
it('aborts in-flight requests on unmount without accepting queued callbacks', async () => {
  let receive!: (event: unknown) => void, finish!: () => void
  vi.mocked(streamDamonChat).mockImplementation(async (_input, _signal, callback) => {
    receive = callback; await new Promise<void>(resolve => { finish = resolve })
  })
  await send('leave')
  const signal = vi.mocked(streamDamonChat).mock.calls[0][1]
  await act(async () => root.render(<p>left</p>))
  expect(signal.aborted).toBe(true)
  await act(async () => { receive({ ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 }); finish() })
  expect(host.textContent).toBe('left')
})
it('keeps Mock explicit and cancels real text when switching back to the HUD demo', async () => {
  let finish!: () => void
  vi.mocked(streamDamonChat).mockImplementation(async () => { await new Promise<void>(resolve => { finish = resolve }) })
  await act(async () => root.render(<QueryClientProvider client={query}><DamonAIPage /></QueryClientProvider>))
  expect(host.textContent).toContain('麦克风未开启')
  await act(async () => button('真实模型文字').click())
  expect(host.textContent).toContain('真实模型文字模式')
  await send('switch mode')
  const signal = vi.mocked(streamDamonChat).mock.calls[0][1]
  await act(async () => button('离线 Mock 演示').click())
  expect(signal.aborted).toBe(true)
  await act(async () => finish())
  expect(host.textContent).toContain('无真实音频波形或声音')
})
