/** Text transport has server-owned identifiers, separate from the offline voice protocol. */
// Unicode code points, matching Python len(str); not UTF-16 units or graphemes.
export const TEXT_MAX_CODE_POINTS = 16000
export interface TextTurn {
  conversationId: string | null; turnId: string | null; requestId: string | null
  sequence: number; text: string; terminal: boolean; error: string | null; profileId: string
}
const id = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value)
export function acceptTextEvent(state: TextTurn, input: unknown): TextTurn {
  if (state.terminal || !input || typeof input !== 'object' || Array.isArray(input)) return state
  const e = input as Record<string, unknown>
  if (!id(e.conversation_id) || !id(e.turn_id) || !id(e.request_id) ||
      !Number.isSafeInteger(e.sequence) || (e.sequence as number) <= state.sequence) return state
  if (state.conversationId && state.conversationId !== e.conversation_id) return state
  if (state.turnId && (state.turnId !== e.turn_id || state.requestId !== e.request_id)) return state
  if (!state.turnId && (e.type !== 'start' || e.profile_id !== state.profileId)) return state
  if (state.turnId && e.type === 'start') return state
  const next = { ...state, conversationId: e.conversation_id, turnId: e.turn_id, requestId: e.request_id, sequence: e.sequence as number }
  switch (e.type) {
    case 'start': case 'ping': return next
    case 'delta': {
      if (typeof e.text !== 'string') return { ...next, terminal: true, error: 'stream_error' }
      const text = state.text + e.text
      if (Array.from(text).length > TEXT_MAX_CODE_POINTS) return { ...next, terminal: true, error: 'output_limit' }
      return { ...next, text }
    }
    case 'done':
      if (e.code !== 'completed' || !state.text) return state
      return { ...next, terminal: true }
    case 'error': case 'cancelled':
      return { ...next, terminal: true, error: e.type === 'cancelled' ? 'cancelled' :
        ['timeout', 'output_limit', 'upstream_error'].includes(e.code as string) ? e.code as string : 'stream_error' }
    default: return state
  }
}
