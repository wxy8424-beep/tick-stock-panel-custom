/** No audio devices, network, storage or speech APIs are used by this Mock. */
export type VoiceMode = 'chained' | 'realtime'
export type CoreState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'stopped' | 'error'
export interface VoiceState {
  sessionId: string | null
  turnId: string | null
  sequence: number
  core: CoreState
  connection: 'disconnected' | 'connected'
  microphone: 'off' | 'mock'
  recognition: 'idle' | 'transcribing'
  agent: 'idle' | 'running'
  playback: 'idle' | 'mock'
  transcript: string
  assistant: string
  assistantTurnId: string | null
  error: string | null
}
interface Envelope { sessionId: string; turnId: string | null; sequence: number }
export type VoiceEvent = Envelope & (
  | { type: 'connected' | 'disconnected' | 'cancelled' | 'playback_stopped' | 'turn_done' }
  | { type: 'transcript'; text: string; final: boolean }
  | { type: 'assistant_delta'; text: string }
  | { type: 'audio_chunk'; audio: Uint8Array; mimeType: string }
  | { type: 'state'; state: CoreState }
  | { type: 'error'; scope: 'turn' | 'connection'; code: 'mock_failure' | 'disconnected'; requestId: string }
)
export interface VoiceAdapter {
  readonly mode: VoiceMode
  readonly mock: boolean
  start(sessionId: string, receive: (event: VoiceEvent) => void): void
  beginTurn(turnId: string, text: string, signal: AbortSignal): void
  listen(): void
  stopPlayback(): void
  cancel(turnId: string): void
  end(): void
  dispose(): void
}
export const initialVoiceState: VoiceState = {
  sessionId: null, turnId: null, sequence: 0, core: 'idle', connection: 'disconnected',
  microphone: 'off', recognition: 'idle', agent: 'idle', playback: 'idle',
  transcript: '', assistant: '', assistantTurnId: null, error: null,
}
export function newTurn(state: VoiceState, turnId: string): VoiceState {
  if (state.connection !== 'connected' || !validId(turnId)) return state
  return { ...state, turnId, core: 'thinking', agent: 'running', playback: 'idle',
    recognition: 'idle', transcript: '', assistant: '', assistantTurnId: turnId, error: null }
}
const validId = (value: unknown): value is string => typeof value === 'string' && /^[\w-]{1,128}$/.test(value)
/** Current Mock protocol: bounded text deltas; audio is reserved and rejected. */
export function parseVoiceEvent(input: unknown): VoiceEvent | null {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return null
  const event = input as Record<string, unknown>
  if (!validId(event.sessionId) || (event.turnId !== null && !validId(event.turnId)) ||
      !Number.isSafeInteger(event.sequence) || (event.sequence as number) <= 0) return null
  let fields: string[] = []
  switch (event.type) {
    case 'connected': case 'disconnected':
      if (event.turnId !== null) return null
      break
    case 'cancelled': case 'turn_done': case 'playback_stopped':
      if (!validId(event.turnId)) return null
      break
    case 'transcript': case 'assistant_delta':
      if (!validId(event.turnId) || typeof event.text !== 'string' || event.text.length > 2000) return null
      fields = ['text']
      if (event.type === 'transcript') {
        if (typeof event.final !== 'boolean') return null
        fields.push('final')
      }
      break
    case 'state':
      if (!['listening', 'thinking', 'speaking'].includes(event.state as string)) return null
      if (event.state === 'listening' ? event.turnId !== null : !validId(event.turnId)) return null
      fields = ['state']; break
    case 'error':
      if (!['mock_failure', 'disconnected'].includes(event.code as string) || !validId(event.requestId)) return null
      if (event.scope === 'connection' ? event.turnId !== null : event.scope !== 'turn' || !validId(event.turnId)) return null
      fields = ['scope', 'code', 'requestId']; break
    default: return null
  }
  const allowed = ['sessionId', 'turnId', 'sequence', 'type', ...fields]
  if (Object.keys(event).some(key => !allowed.includes(key))) return null
  return event as unknown as VoiceEvent
}
export function acceptVoiceEvent(state: VoiceState, input: unknown): VoiceState {
  const event = parseVoiceEvent(input)
  if (!event || !state.sessionId || event.sessionId !== state.sessionId || event.sequence <= state.sequence) return state
  const lifecycle = event.type === 'disconnected' || (event.type === 'error' && event.scope === 'connection')
  if (!lifecycle && event.turnId !== state.turnId) return state
  if (event.type === 'connected' && state.connection === 'connected') return state
  if (event.type !== 'connected' && state.connection !== 'connected') return state
  // A cancelled turn is retired before cancelling its adapter. Late packets cannot revive it.
  let next = { ...state, sequence: event.sequence }
  if (event.type === 'connected') return { ...next, connection: 'connected' }
  if (event.type === 'disconnected') return { ...initialVoiceState,
    sequence: event.sequence, core: 'stopped' }
  if (event.type === 'cancelled') return stopVoice(next)
  if (event.type === 'playback_stopped') return stopVoice(next)
  if (event.type === 'turn_done') return { ...stopVoice(next), core: 'idle' }
  if (event.type === 'transcript') return { ...next, transcript: event.text,
    recognition: event.final ? 'idle' : 'transcribing' }
  if (event.type === 'assistant_delta') {
    if (state.assistant.length + event.text.length > 8000) return state
    return { ...next, assistant: state.assistant + event.text }
  }
  if (event.type === 'error') return { ...stopVoice(next), core: 'error',
    ...(event.scope === 'connection' ? { connection: 'disconnected' as const, sessionId: null } : {}),
    error: `演示${event.scope === 'connection' ? '连接' : '轮次'}错误（${event.requestId}）` }
  if (event.type === 'state') next = { ...next, core: event.state,
    microphone: event.state === 'listening' ? 'mock' : 'off',
    recognition: event.state === 'listening' ? 'transcribing' : 'idle',
    agent: event.state === 'thinking' ? 'running' : 'idle',
    playback: event.state === 'speaking' ? 'mock' : 'idle' }
  return next
}
export function stopVoice(state: VoiceState): VoiceState {
  return { ...state, turnId: null, core: 'stopped', microphone: 'off',
    recognition: 'idle', agent: 'idle', playback: 'idle' }
}

export class MockVoiceAdapter implements VoiceAdapter {
  readonly mode = 'chained' as const
  readonly mock = true
  private sessionId = ''
  private turnId: string | null = null
  private sequence = 0
  private receive: ((event: VoiceEvent) => void) | null = null
  private timers = new Set<ReturnType<typeof setTimeout>>()
  private removeAbort: (() => void) | null = null

  start(sessionId: string, receive: (event: VoiceEvent) => void) {
    this.dispose()
    this.sessionId = sessionId; this.sequence = 0; this.receive = receive
    this.emit({ type: 'connected' })
  }
  private emit(payload: VoicePayload) {
    this.receive?.({ ...payload, sessionId: this.sessionId, turnId: this.turnId,
      sequence: ++this.sequence } as VoiceEvent)
  }
  private later(ms: number, action: () => void) {
    const timer = setTimeout(() => { this.timers.delete(timer); action() }, ms)
    this.timers.add(timer)
  }
  private clear() {
    this.timers.forEach(clearTimeout); this.timers.clear()
    this.removeAbort?.(); this.removeAbort = null
  }
  listen() { if (this.receive && !this.turnId) this.emit({ type: 'state', state: 'listening' }) }
  beginTurn(turnId: string, text: string, signal: AbortSignal) {
    if (!this.receive || !validId(turnId) || text.length > 2000) return
    this.clear(); this.turnId = turnId
    if (!this.receive || signal.aborted) { this.cancel(turnId); return }
    const abort = () => this.cancel(turnId)
    signal.addEventListener('abort', abort, { once: true })
    this.removeAbort = () => signal.removeEventListener('abort', abort)
    this.emit({ type: 'transcript', text, final: true })
    this.emit({ type: 'state', state: 'thinking' })
    this.later(650, () => {
      this.emit({ type: 'assistant_delta', text: '这是离线演示回复。' })
      this.emit({ type: 'state', state: 'speaking' })
    })
    this.later(900, () => this.emit({ type: 'assistant_delta', text: '真实模型、语音和研究工具尚未接入；没有查询行情或生成生产证据。' }))
    this.later(1500, () => { this.clear(); this.emit({ type: 'turn_done' }); this.turnId = null })
  }
  stopPlayback() {
    if (!this.turnId) return
    this.clear(); this.emit({ type: 'playback_stopped' }); this.turnId = null
  }
  cancel(turnId: string) {
    if (this.turnId !== turnId) return
    this.clear(); this.emit({ type: 'cancelled' }); this.turnId = null
  }
  end() { this.clear(); this.turnId = null; if (this.receive) this.emit({ type: 'disconnected' }); this.dispose() }
  dispose() { this.clear(); this.receive = null; this.turnId = null; this.sessionId = '' }
  fail(scope: 'turn' | 'connection' = 'connection') {
    if (!this.receive || (scope === 'turn' && !this.turnId)) return
    this.clear()
    if (scope === 'connection') this.turnId = null
    this.emit({ type: 'error', scope, code: 'mock_failure', requestId: 'mock-offline' })
    this.turnId = null
    if (scope === 'connection') this.dispose()
  }
}
type VoicePayload = VoiceEvent extends infer E ? E extends VoiceEvent ? Omit<E, keyof Envelope> : never : never
