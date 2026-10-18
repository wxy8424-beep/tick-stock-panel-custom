import { afterEach, expect, it, vi } from 'vitest'
import { streamDamonChat } from '@/lib/api'
import { acceptTextEvent, type TextTurn } from './text'

afterEach(() => vi.unstubAllGlobals())
const input = { profile_id: 'alpha', conversation_id: null, messages: [{ role: 'user' as const, content: 'hello' }] }
const envelope = { conversation_id: 'a'.repeat(32), turn_id: 'b'.repeat(32), request_id: 'c'.repeat(32) }
const initial: TextTurn = { conversationId: null, turnId: null, requestId: null, sequence: 0,
  text: '', terminal: false, error: null, profileId: 'alpha' }

it('releases the reader on a validated terminal without waiting for EOF or consuming trailing packets', async () => {
  const cancel = vi.fn()
  const events = [{ ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 },
    { ...envelope, type: 'delta', text: 'complete', sequence: 2 },
    { ...envelope, type: 'done', code: 'completed', sequence: 3 },
    { ...envelope, type: 'delta', text: 'late', sequence: 4 }]
  const body = new ReadableStream<Uint8Array>({ start(controller) {
    controller.enqueue(new TextEncoder().encode(events.map(e => JSON.stringify(e) + '\n').join('')))
    // Deliberately no close(): a proxy can keep the body open after done.
  }, cancel })
  const response = new Response(body)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
  let state = initial
  const received: unknown[] = []
  await streamDamonChat(input, new AbortController().signal, event => {
    received.push(event); state = acceptTextEvent(state, event)
    if (state.terminal) return false
  })
  expect(received).toHaveLength(3)
  expect(state).toMatchObject({ terminal: true, error: null, text: 'complete' })
  expect(cancel).toHaveBeenCalledOnce()
  expect(body.locked).toBe(false)
})

it('transports a valid full-size emoji body without confusing UTF-16 with code points', async () => {
  const text = '😀'.repeat(16000)
  const events = [{ ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 },
    { ...envelope, type: 'delta', text, sequence: 2 },
    { ...envelope, type: 'done', code: 'completed', sequence: 3 }]
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(events.map(e => JSON.stringify(e) + '\n').join(''))))
  let state = initial
  await streamDamonChat(input, new AbortController().signal, event => { state = acceptTextEvent(state, event) })
  expect(state.text).toBe(text)
  expect(state).toMatchObject({ terminal: true, error: null })
})

it('cancels the real reader after cumulative overflow before a queued done can succeed', async () => {
  const cancel = vi.fn()
  const events = [{ ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 },
    { ...envelope, type: 'delta', text: '😀'.repeat(15999), sequence: 2 },
    { ...envelope, type: 'delta', text: '😀😀', sequence: 3 },
    { ...envelope, type: 'done', code: 'completed', sequence: 4 }]
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode(events.map(e => JSON.stringify(e) + '\n').join(''))) }, cancel,
  }))))
  const controller = new AbortController()
  let state = initial
  await expect(streamDamonChat(input, controller.signal, event => {
    state = acceptTextEvent(state, event)
    if (state.terminal && state.error) { controller.abort(); throw new Error(state.error) }
  })).rejects.toThrow('output_limit')
  expect(controller.signal.aborted).toBe(true)
  expect(cancel).toHaveBeenCalledOnce()
  expect(state).toMatchObject({ terminal: true, error: 'output_limit', sequence: 3 })
})

it('decodes split UTF-8 NDJSON through the centralized client', async () => {
  const encoded = new TextEncoder().encode(JSON.stringify({ text: '中文' }) + '\n')
  const fetch = vi.fn().mockResolvedValue(new Response(new ReadableStream({ start(controller) {
    controller.enqueue(encoded.slice(0, 11)); controller.enqueue(encoded.slice(11)); controller.close()
  } })))
  vi.stubGlobal('fetch', fetch)
  const receive = vi.fn()
  await streamDamonChat(input, new AbortController().signal, receive)
  expect(receive).toHaveBeenCalledExactlyOnceWith({ text: '中文' })
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(input)
})
it('cancels the response reader on malformed input or consumer failure', async () => {
  const cancel = vi.fn()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode('invalid json\n')) }, cancel,
  }))))
  await expect(streamDamonChat(input, new AbortController().signal, vi.fn())).rejects.toThrow()
  expect(cancel).toHaveBeenCalledOnce()
})
it('rejects unfinished lines and only exposes safe preflight request IDs', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('{"type":"unfinished"}'))
    .mockResolvedValueOnce(new Response(JSON.stringify({ request_id: 'a'.repeat(32), detail: 'FAKE_SECRET https://private.example' }), { status: 400 })))
  await expect(streamDamonChat(input, new AbortController().signal, vi.fn())).rejects.toThrow('incomplete_stream')
  await expect(streamDamonChat(input, new AbortController().signal, vi.fn())).rejects.toMatchObject({ message: 'request_failed_400', requestId: 'a'.repeat(32) })
})
it('accepts a large network chunk of small frames and rejects one oversized frame', async () => {
  const line = JSON.stringify({ text: 'a', envelope: 'x'.repeat(200) }) + '\n'
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(line.repeat(1000)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ text: 'x'.repeat(20001) }) + '\n')))
  const receive = vi.fn()
  await streamDamonChat(input, new AbortController().signal, receive)
  expect(receive).toHaveBeenCalledTimes(1000)
  await expect(streamDamonChat(input, new AbortController().signal, vi.fn())).rejects.toThrow('stream_limit')
})
