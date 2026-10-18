import { expect, it } from 'vitest'
import { acceptTextEvent, type TextTurn } from './text'

const envelope = { conversation_id: 'a'.repeat(32), turn_id: 'b'.repeat(32), request_id: 'c'.repeat(32) }
const initial: TextTurn = { conversationId: null, turnId: null, requestId: null, sequence: 0, text: '', terminal: false, error: null, profileId: 'alpha' }
it('accumulates deltas once and fences retired turns and other identities', () => {
  let state = acceptTextEvent(initial, { ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 })
  const delta = { ...envelope, type: 'delta', text: 'hello', sequence: 2 }
  state = acceptTextEvent(state, delta)
  expect(acceptTextEvent(state, delta)).toBe(state)
  for (const sequence of [-1, 1.5, Infinity, Number.MAX_SAFE_INTEGER + 1]) expect(acceptTextEvent(state, { ...delta, sequence })).toBe(state)
  expect(acceptTextEvent(state, { ...delta, sequence: 9, turn_id: 'd'.repeat(32) })).toBe(state)
  state = acceptTextEvent(state, { ...delta, sequence: 3, text: ' world' })
  expect(state.text).toBe('hello world')
  state = acceptTextEvent(state, { ...envelope, sequence: 4, type: 'done', code: 'completed' })
  expect(state.terminal).toBe(true)
  expect(acceptTextEvent(state, { ...delta, sequence: 99 })).toBe(state)
})
it('rejects unexpected starts and bounds output and errors', () => {
  expect(acceptTextEvent(initial, { ...envelope, type: 'start', sequence: 1, profile_id: 'other' })).toBe(initial)
  const state = acceptTextEvent(initial, { ...envelope, type: 'start', sequence: 1, profile_id: 'alpha' })
  expect(acceptTextEvent(state, { ...envelope, type: 'delta', sequence: 2, text: 'x'.repeat(16001) }))
    .toMatchObject({ terminal: true, error: 'output_limit', text: '' })
  const error = acceptTextEvent(state, { ...envelope, type: 'error', sequence: 2, code: 'RAW_SECRET_URL' })
  expect(error.error).toBe('stream_error')
})

it.each(['中', '😀'])('counts Unicode code points at the 16000 boundary: %s', character => {
  let state = acceptTextEvent(initial, { ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 })
  state = acceptTextEvent(state, { ...envelope, type: 'delta', sequence: 2, text: character.repeat(15999) })
  expect(state.terminal).toBe(false)
  expect(Array.from(state.text)).toHaveLength(15999)
  state = acceptTextEvent(state, { ...envelope, type: 'delta', sequence: 3, text: character })
  expect(Array.from(state.text)).toHaveLength(16000)
  expect(state.terminal).toBe(false)
  const completed = acceptTextEvent(state, { ...envelope, type: 'done', sequence: 4, code: 'completed' })
  expect(completed).toMatchObject({ terminal: true, error: null })
  const overflow = { ...envelope, type: 'delta', sequence: 4, text: character }
  const failed = acceptTextEvent(state, overflow)
  expect(failed).toMatchObject({ terminal: true, error: 'output_limit', sequence: 4, text: state.text })
  for (const event of [overflow, { ...overflow, sequence: 5 },
    { ...envelope, type: 'done', sequence: 6, code: 'completed' }]) {
    expect(acceptTextEvent(failed, event)).toBe(failed)
  }
})

it('fails an oversized first emoji delta and never accepts its done', () => {
  const started = acceptTextEvent(initial, { ...envelope, type: 'start', profile_id: 'alpha', sequence: 1 })
  const failed = acceptTextEvent(started, { ...envelope, type: 'delta', sequence: 2, text: '😀'.repeat(16001) })
  expect(failed).toMatchObject({ terminal: true, error: 'output_limit', text: '' })
  expect(acceptTextEvent(failed, { ...envelope, type: 'done', sequence: 3, code: 'completed' })).toBe(failed)
})
