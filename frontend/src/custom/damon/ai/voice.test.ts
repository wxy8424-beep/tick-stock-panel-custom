import { afterEach, describe, expect, it, vi } from 'vitest'
import { acceptVoiceEvent, initialVoiceState, MockVoiceAdapter, newTurn, stopVoice, type VoiceEvent, type VoiceState } from './voice'

afterEach(() => vi.useRealTimers())
describe('Damon mock voice boundary', () => {
  it('starts, produces transcript and mock states, ends and releases timers', () => {
    vi.useFakeTimers()
    const events: VoiceEvent[] = []
    const adapter = new MockVoiceAdapter()
    adapter.start('s', event => events.push(event))
    adapter.listen()
    adapter.beginTurn('t', '问题', new AbortController().signal)
    vi.advanceTimersByTime(1600)
    expect(events.map(e => e.type)).toContain('transcript')
    expect(events.filter(e => e.type === 'state').map(e => e.state)).toEqual(['listening', 'thinking', 'speaking'])
    expect(events.at(-1)?.type).toBe('turn_done')
    expect(events.some(e => e.type === 'audio_chunk')).toBe(false)
    adapter.end()
    expect(events.at(-1)?.type).toBe('disconnected')
    expect(vi.getTimerCount()).toBe(0)
  })
  it('abort and duplicate cancellation stop all future output', () => {
    vi.useFakeTimers()
    const receive = vi.fn(), adapter = new MockVoiceAdapter(), controller = new AbortController()
    adapter.start('s', receive); adapter.beginTurn('t', 'hello', controller.signal)
    controller.abort(); adapter.cancel('t'); adapter.cancel('t')
    const count = receive.mock.calls.length
    vi.runAllTimers()
    expect(receive).toHaveBeenCalledTimes(count)
    expect(receive.mock.calls.filter(([event]) => event.type === 'cancelled')).toHaveLength(1)
    expect(vi.getTimerCount()).toBe(0)
  })
  it('stopping playback and disposing mid-turn prevent queued speech', () => {
    vi.useFakeTimers()
    const receive = vi.fn(), adapter = new MockVoiceAdapter()
    adapter.start('s', receive); adapter.beginTurn('t', 'hello', new AbortController().signal)
    vi.advanceTimersByTime(700); adapter.stopPlayback()
    const count = receive.mock.calls.length
    vi.runAllTimers(); expect(receive).toHaveBeenCalledTimes(count)
    adapter.dispose(); adapter.dispose(); expect(vi.getTimerCount()).toBe(0)
  })
  it('rejects wrong sessions, old turns, duplicate/out-of-order events and post-disconnect packets', () => {
    const state = newTurn({ ...initialVoiceState, sessionId: 's', sequence: 3, connection: 'connected' }, 't2')
    const event: VoiceEvent = { sessionId: 's', turnId: 't2', sequence: 4, type: 'assistant_delta', text: 'new' }
    const next = acceptVoiceEvent(state, event)
    expect(next.assistant).toBe('new')
    for (const packet of [{ ...event, sequence: 2 }, { ...event, sessionId: 'old', sequence: 99 }, { ...event, turnId: 't1', sequence: 99 }, event]) {
      expect(acceptVoiceEvent(next, packet)).toBe(next)
    }
    const stopped = stopVoice(next)
    expect(acceptVoiceEvent(stopped, { ...event, sequence: 100 })).toBe(stopped)
    const playbackStopped = acceptVoiceEvent(next, { sessionId: 's', turnId: 't2', type: 'playback_stopped', sequence: 5 })
    expect(acceptVoiceEvent(playbackStopped, { ...event, sequence: 100 })).toBe(playbackStopped)
    const disconnected = acceptVoiceEvent(next, { sessionId: 's', turnId: null, type: 'disconnected', sequence: 5 })
    expect(disconnected.connection).toBe('disconnected')
    expect(acceptVoiceEvent(disconnected, { ...event, sequence: 100 })).toBe(disconnected)
  })
  it('does not emit a turn when its signal was already aborted', () => {
    const receive = vi.fn(), adapter = new MockVoiceAdapter(), controller = new AbortController()
    controller.abort(); adapter.start('s', receive); adapter.beginTurn('t', 'hello', controller.signal)
    expect(receive.mock.calls.some(([event]) => event.type === 'transcript')).toBe(false)
    adapter.dispose()
  })
  it('accumulates deltas once and retires completed turns against every late event', () => {
    let state = newTurn({ ...initialVoiceState, sessionId: 's', connection: 'connected' }, 't')
    const delta = { sessionId: 's', turnId: 't', sequence: 1, type: 'assistant_delta', text: 'first' }
    state = acceptVoiceEvent(state, delta)
    expect(acceptVoiceEvent(state, delta)).toBe(state)
    state = acceptVoiceEvent(state, { ...delta, sequence: 2, text: ' second' })
    expect(state.assistant).toBe('first second')
    state = acceptVoiceEvent(state, { sessionId: 's', turnId: 't', sequence: 3, type: 'turn_done' })
    expect(state.turnId).toBeNull(); expect(state.core).toBe('idle')
    for (const payload of [{ type: 'state', state: 'speaking' }, { type: 'assistant_delta', text: 'late' }, { type: 'turn_done' }]) {
      expect(acceptVoiceEvent(state, { sessionId: 's', turnId: 't', sequence: 99, ...payload })).toBe(state)
    }
    const newer = newTurn(state, 'new')
    expect(acceptVoiceEvent(newer, { ...delta, sequence: 100 })).toBe(newer)
  })
  it('rejects malformed envelopes, payloads and unsupported audio at runtime', () => {
    const state = newTurn({ ...initialVoiceState, sessionId: 's', connection: 'connected' }, 't')
    const packet = { sessionId: 's', turnId: 't', sequence: 1, type: 'assistant_delta', text: 'safe' }
    const invalid = [null, [], 'event', ...[-1, 0, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, '1'].map(sequence => ({ ...packet, sequence })),
      { ...packet, sessionId: '' }, { ...packet, turnId: 'x'.repeat(129) }, { ...packet, text: 'x'.repeat(2001) },
      { ...packet, type: 'unknown' }, { ...packet, secret: 'not-allowed' },
      { sessionId: 's', turnId: 't', sequence: 2, type: 'audio_chunk', audio: new Uint8Array(), mimeType: 'audio/wav' }]
    for (const event of invalid) expect(acceptVoiceEvent(state, event)).toBe(state)
  })
  it('distinguishes turn failure from connection failure and restarts explicitly', () => {
    vi.useFakeTimers()
    let state: VoiceState = { ...initialVoiceState, sessionId: 's' }
    const adapter = new MockVoiceAdapter()
    adapter.start('s', event => { state = acceptVoiceEvent(state, event) })
    state = newTurn(state, 't')
    adapter.beginTurn('t', 'hello', new AbortController().signal)
    adapter.fail('turn')
    expect(state.connection).toBe('connected'); expect(state.turnId).toBeNull(); expect(state.core).toBe('error')
    state = newTurn(state, 't2')
    adapter.beginTurn('t2', 'retry', new AbortController().signal)
    adapter.fail('connection')
    expect(state.connection).toBe('disconnected'); expect(state.sessionId).toBeNull()
    expect(newTurn(state, 'blocked')).toBe(state)
    expect(vi.getTimerCount()).toBe(0)
    const failed = state
    adapter.listen(); adapter.beginTurn('bad', 'bad', new AbortController().signal)
    expect(state).toBe(failed)
    state = { ...initialVoiceState, sessionId: 'new-session' }
    adapter.start('new-session', event => { state = acceptVoiceEvent(state, event) })
    expect(state.connection).toBe('connected')
    adapter.dispose(); adapter.dispose()
  })
})
