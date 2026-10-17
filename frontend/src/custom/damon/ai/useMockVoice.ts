import { useEffect, useRef, useState } from 'react'
import { acceptVoiceEvent, initialVoiceState, MockVoiceAdapter, newTurn, stopVoice } from './voice'

export function useMockVoice() {
  const [state, setState] = useState(initialVoiceState)
  const adapter = useRef<MockVoiceAdapter | null>(null)
  const abort = useRef<AbortController | null>(null)
  const turn = useRef<string | null>(null)
  const counter = useRef(0)
  useEffect(() => () => { adapter.current?.dispose(); abort.current?.abort() }, [])

  const stop = () => {
    const oldTurn = turn.current
    turn.current = null
    setState(previous => stopVoice(previous))
    abort.current?.abort(); abort.current = null
    if (oldTurn) adapter.current?.cancel(oldTurn)
  }
  const start = () => {
    stop(); adapter.current?.dispose()
    const sessionId = `mock-session-${++counter.current}`
    setState({ ...initialVoiceState, sessionId })
    adapter.current = new MockVoiceAdapter()
    adapter.current.start(sessionId, event => setState(previous => acceptVoiceEvent(previous, event)))
  }
  const send = (text: string) => {
    if (state.connection !== 'connected' || !text.trim() || text.length > 2000) return
    stop()
    const turnId = `mock-turn-${++counter.current}`
    turn.current = turnId; abort.current = new AbortController()
    setState(previous => newTurn(previous, turnId))
    adapter.current?.beginTurn(turnId, text, abort.current.signal)
  }
  return { state, start, send, stop,
    listen: () => { if (state.connection === 'connected') { stop(); adapter.current?.listen() } },
    end: () => { stop(); adapter.current?.end() },
    stopPlayback: () => { stop(); adapter.current?.stopPlayback() },
    fail: () => adapter.current?.fail(),
  }
}
