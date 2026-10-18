import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, cancelDamonChat, streamDamonChat, type DamonMessage } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { acceptTextEvent, type TextTurn } from './text'

const control = 'rounded border border-cyan-500/40 bg-slate-900 p-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-200 disabled:opacity-40'
function failureNotice(code: string | null | undefined) {
  const labels: Record<string, string> = { local_timeout: '浏览器本地超时（70 秒）', timeout: '服务端超时',
    connection_error: '连接错误', request_error: '服务端请求错误', upstream_error: '上游服务错误', stream_error: '流式协议错误',
    output_limit: '正文超过 16000 Unicode 码点上限' }
  return `生成失败：${labels[code || ''] || '连接或上游错误'}。可重试；未完成回复不进入后续上下文。`
}
export function TextChatPanel() {
  const profiles = useQuery({ queryKey: QK.damonProfiles, queryFn: api.damonProfiles, retry: false })
  const [selected, setSelected] = useState('')
  const [draft, setDraft] = useState('')
  const [history, setHistory] = useState<(DamonMessage & { model?: string })[]>([])
  const [pendingUser, setPendingUser] = useState('')
  const [turn, setTurn] = useState<TextTurn | null>(null)
  const [status, setStatus] = useState<'idle' | 'sending' | 'stopping' | 'stopped' | 'error'>('idle')
  const [notice, setNotice] = useState('')
  const conversation = useRef<string | null>(null)
  const current = useRef<TextTurn | null>(null)
  const controller = useRef<AbortController | null>(null)
  const streamTimeout = useRef<number | null>(null)
  const epoch = useRef(0)
  const profileId = selected || profiles.data?.profiles.find(p => p.enabled && p.text_stream && p.configured)?.profile_id || ''
  const busy = status === 'sending' || status === 'stopping'
  useEffect(() => () => {
    epoch.current++; controller.current?.abort()
    if (streamTimeout.current !== null) window.clearTimeout(streamTimeout.current)
  }, [])

  async function send(event: FormEvent) {
    event.preventDefault()
    if (busy || !profileId || !draft.trim()) return
    const user = draft.trim(), generation = ++epoch.current
    const initial: TextTurn = { conversationId: conversation.current, turnId: null, requestId: null,
      sequence: 0, text: '', terminal: false, error: null, profileId }
    current.current = initial; setTurn(initial); setPendingUser(user); setDraft(''); setNotice('')
    setStatus('sending')
    const ctl = new AbortController(); controller.current = ctl
    const timeout = window.setTimeout(() => {
      if (generation !== epoch.current || current.current?.terminal) return
      // First terminal wins, even before React commits the next render. Retire
      // both the request generation and turn before abort can reject the reader.
      epoch.current++
      const failed = { ...current.current!, terminal: true, error: 'local_timeout' }
      current.current = failed; setTurn(failed); setStatus('error'); setDraft(user)
      setNotice(failureNotice('local_timeout'))
      clearDeadline()
      ctl.abort()
    }, 70000)
    const clearDeadline = () => {
      window.clearTimeout(timeout)
      if (streamTimeout.current === timeout) streamTimeout.current = null
    }
    streamTimeout.current = timeout
    const messages: DamonMessage[] = [...history.slice(-22).map(({ role, content }) => ({ role, content })), { role: 'user', content: user }]
    // Drop whole old pairs so a long successful reply remains usable next turn.
    while (messages.length > 1 && messages.reduce((sum, m) => sum + m.content.length, 0) > 20000) messages.splice(0, 2)
    try {
      await streamDamonChat({ conversation_id: conversation.current, profile_id: profileId, messages }, ctl.signal, event => {
        if (generation !== epoch.current || current.current?.terminal) return
        const next = acceptTextEvent(current.current!, event)
        current.current = next; setTurn(next)
        conversation.current = next.conversationId
        if (next.terminal) clearDeadline()
        if (next.terminal && next.error) {
          // Retire before aborting; even callbacks already queued for this turn
          // cannot revive it or put its partial body in successful history.
          ctl.abort()
          throw new Error(next.error)
        }
        if (next.terminal) return false
      })
      if (generation !== epoch.current) return
      const result = current.current!
      if (!result.terminal || result.error) throw new Error(result.error || 'disconnected')
      setHistory(previous => [...previous, { role: 'user', content: user },
        { role: 'assistant', content: result.text, model: profileId }].slice(-22) as typeof previous)
      setPendingUser(''); setTurn(null); setStatus('idle')
    } catch (error) {
      if (generation !== epoch.current) return
      if (current.current && !current.current.terminal) {
        const code = error instanceof Error && /^request_failed_\d{3}$/.test(error.message) ? 'request_error' : 'connection_error'
        current.current = { ...current.current, terminal: true, error: code }
        setTurn(current.current)
      }
      const requestId = (error as { requestId?: unknown } | null)?.requestId
      if (typeof requestId === 'string' && /^[a-f0-9]{32}$/.test(requestId) && current.current) {
        current.current = { ...current.current, requestId }; setTurn(current.current)
      }
      setStatus('error'); setDraft(user)
      setNotice(failureNotice(current.current?.error))
    } finally {
      clearDeadline()
    }
  }
  async function stop() {
    if (status !== 'sending' || current.current?.terminal) return
    const generation = ++epoch.current
    setStatus('stopping')
    setDraft(pendingUser)
    const previous = current.current
    if (previous) { current.current = { ...previous, terminal: true }; setTurn(current.current) }
    if (streamTimeout.current !== null) { window.clearTimeout(streamTimeout.current); streamTimeout.current = null }
    controller.current?.abort()
    try {
      if (!previous?.conversationId || !previous.turnId) throw new Error('pending_start')
      const result = await cancelDamonChat(previous.conversationId, previous.turnId)
      if (generation !== epoch.current) return
      if (result.cleanup_state !== 'finished' && result.cleanup_state !== 'still_running') throw new Error('invalid_cleanup_state')
      setNotice(result.cleanup_state === 'still_running' ? '已停止接收；上游清理未完成，请稍后重试。' : '已停止接收，上游请求已退出。')
    } catch {
      if (generation !== epoch.current) return
      setNotice('已停止接收；上游退出状态未确认，请稍后重试。')
    }
    setStatus('stopped')
  }
  return <section aria-label="真实模型文字对话" className="space-y-4 rounded-xl border border-cyan-400/25 bg-slate-950 p-4 text-slate-100">
    <p>真实模型文字模式 · 无语音、工具或行情证据</p>
    <label className="block">后续轮次模型 <select aria-label="真实模型配置" value={profileId} onChange={e => setSelected(e.target.value)} className={`${control} max-w-full`}>
      {profiles.data?.profiles.map(p => <option key={p.profile_id} value={p.profile_id} disabled={!p.enabled || !p.text_stream || !p.configured}>
        {p.display_name} · {p.model} · {p.protocol}{!p.enabled || !p.text_stream || !p.configured ? '（不可用）' : '（凭证已配置，连接未验证）'}</option>)}
    </select></label>
    {profiles.isError && <p role="alert">模型配置不可用。<button onClick={() => profiles.refetch()} className={control}>重新加载配置</button></p>}
    {!profiles.isLoading && !profileId && <p role="status">无可用模型，请由管理员配置服务端 Profile。</p>}
    <p role="status" aria-live="polite">{status === 'sending' ? '生成中' : status === 'stopping' ? '停止中' : status === 'stopped' ? '已停止' : status === 'error' ? '生成错误' : '就绪'}{busy && ` · 本轮固定模型：${turn?.profileId}`}</p>
    <div aria-label="真实消息历史" className="max-h-96 space-y-3 overflow-auto break-words whitespace-pre-wrap">
      {history.map((m, i) => <article key={i}><strong>{m.role === 'user' ? '你' : `Damon · ${m.model}`}</strong><p>{m.content}</p></article>)}
      {pendingUser && <article><strong>你</strong><p>{pendingUser}</p></article>}
      {turn?.text && <article><strong>Damon · {turn.profileId}{status !== 'idle' && ' · 当前轮次'}</strong><p>{turn.text}</p></article>}
    </div>
    {notice && <p role="alert">{notice} {turn?.requestId && `request ID：${turn.requestId}`}</p>}
    <form onSubmit={send} className="space-y-2">
      <label htmlFor="damon-real-input">文字消息</label>
      <textarea id="damon-real-input" maxLength={2000} rows={3} value={draft} onChange={e => setDraft(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit() } }} className={`w-full ${control}`} />
      <div className="flex flex-wrap gap-3"><button disabled={busy || !profileId || !draft.trim()} className={control}>发送文字</button>
        <button type="button" disabled={status !== 'sending'} onClick={stop} className={control}>停止生成</button>
        <button type="button" disabled={busy} onClick={() => { conversation.current = null; setHistory([]); setPendingUser(''); setTurn(null); setNotice(''); setStatus('idle') }} className={control}>新对话</button></div>
    </form>
    <p className="text-xs text-slate-400">成功轮次才进入上下文；按条数和字符预算保留最近完整轮次，历史仅在内存保留。模型切换不修改旧助手设置。</p>
  </section>
}
