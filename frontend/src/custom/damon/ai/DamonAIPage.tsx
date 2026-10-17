import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Bot, Mic, Radio, ShieldCheck, Square } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { MarketSwitcher, type Market } from '@/components/MarketSwitcher'
import { useMockVoice } from './useMockVoice'
import type { CoreState } from './voice'

type DataMode = 'real_cache' | 'historical' | 'preview' | 'simulation'
const modes: Record<DataMode, string> = { real_cache: '真实缓存（未接入）', historical: '历史证据（未接入）', preview: '合成 Preview', simulation: '模拟事件' }
const states: Record<CoreState, string> = { idle: '空闲', listening: '聆听演示', thinking: '思考演示', speaking: '播报演示', stopped: '已停止', error: '错误' }
const focus = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan-300'
const button = `inline-flex items-center justify-center gap-2 rounded-lg border border-cyan-400/25 bg-slate-900 px-3 py-2 text-xs text-slate-100 disabled:opacity-40 ${focus}`
interface Message { id: number; turnId?: string; role: string; text: string; market: Market; mode: DataMode }

export function DamonAIPage() {
  const voice = useMockVoice()
  const { state } = voice
  const [market, setMarket] = useState<Market>('CN')
  const [mode, setMode] = useState<DataMode>('simulation')
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [reduced, setReduced] = useState(false)
  const [tab, setTab] = useState<'chat' | 'research'>('chat')
  const messageCounter = useRef(0)
  useEffect(() => {
    if (!state.assistant || !state.assistantTurnId) return
    const id = ++messageCounter.current
    setMessages(previous => previous.some(message => message.turnId === state.assistantTurnId)
      ? previous.map(message => message.turnId === state.assistantTurnId ? { ...message, text: state.assistant } : message)
      : [...previous, { id, turnId: state.assistantTurnId!, role: 'Damon · 演示回复', text: state.assistant, market, mode }].slice(-100))
  }, [state.assistant, state.assistantTurnId, market, mode])
  const connected = state.connection === 'connected'
  const active = state.agent === 'running' || state.playback === 'mock'
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!connected || active || !draft.trim()) return
    const id = ++messageCounter.current
    setMessages(previous => [...previous, { id, role: '你', text: draft.trim(), market, mode }].slice(-100))
    voice.send(draft.trim()); setDraft('')
  }
  const changeContext = (nextMarket: Market, nextMode: DataMode) => {
    voice.stop(); setMarket(nextMarket); setMode(nextMode)
  }
  return <section className="flex h-full min-h-0 flex-col bg-slate-950 text-slate-100" aria-label="Damon AI 演示工作区">
    <PageHeader title="Damon AI" subtitle="Phase 1 · 离线交互演示 · 未接入真实语音、模型或研究工具" right={<ShieldCheck className="h-5 w-5 shrink-0 text-cyan-300" aria-label="只读边界" />} />
    <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
      <div className="mx-auto max-w-6xl space-y-5">
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-cyan-400/20 bg-slate-900/70 p-3 text-xs">
          <label>模型配置 <select aria-label="模型配置" className={`ml-2 rounded bg-slate-800 p-2 ${focus}`}><option value="damon.mock">Damon Mock · 不调用模型</option></select></label>
          <MarketSwitcher value={market} enabledMarkets={['CN', 'HK', 'US']} onChange={next => changeContext(next, mode)} />
          <label>数据模式 <select aria-label="数据模式" value={mode} onChange={e => changeContext(market, e.target.value as DataMode)} className={`ml-2 max-w-full rounded bg-slate-800 p-2 ${focus}`}>
            {Object.entries(modes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
          <span>语音：chained / Mock</span><span className="text-slate-400">Realtime：尚未实现</span>
        </div>
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="min-w-0 space-y-5">
            <section className="relative overflow-hidden rounded-2xl border border-cyan-400/25 bg-gradient-to-b from-cyan-950/30 to-slate-950 p-5 text-center" aria-label="语音核心">
              <div aria-hidden="true" className={`mx-auto grid h-36 w-36 place-items-center rounded-full border border-cyan-300/50 shadow-[0_0_45px_rgba(34,211,238,0.12)] ${!reduced && state.core === 'thinking' ? 'motion-safe:animate-pulse' : ''}`}>
                <div className="grid h-28 w-28 place-items-center rounded-full border border-dashed border-cyan-400/30"><Bot className="h-12 w-12 text-cyan-200" /></div>
              </div>
              <p role="status" aria-live="polite" className="mt-4 font-medium text-cyan-100">{states[state.core]}</p>
              <p className="mt-2 text-xs text-slate-300">MOCK · 麦克风未开启 · 无真实音频波形或声音</p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                <button className={button} disabled={connected} onClick={voice.start}><Radio size={14} />开始演示会话</button>
                <button className={button} disabled={!connected} onClick={voice.end}>结束会话</button>
                <button className={button} disabled={!connected || active} onClick={voice.listen}><Mic size={14} />模拟聆听</button>
                <button className={button} disabled={!connected} onClick={voice.stopPlayback}>停止播报</button>
                <button className={button} disabled={!connected} onClick={voice.stop}><Square size={14} />停止任务</button>
              </div>
              <label className="mt-4 inline-flex items-center gap-2 text-xs text-slate-300"><input type="checkbox" checked={reduced} onChange={e => setReduced(e.target.checked)} />减少动态效果（同时尊重系统设置）</label>
            </section>
            <div className="flex gap-2 lg:hidden" role="group" aria-label="内容面板">
              <button className={button} aria-pressed={tab === 'chat'} onClick={() => setTab('chat')}>对话</button>
              <button className={button} aria-pressed={tab === 'research'} onClick={() => setTab('research')}>任务与证据</button>
            </div>
            <section className={`${tab === 'chat' ? '' : 'hidden lg:block'} rounded-xl border border-slate-700 bg-slate-900/50 p-4`} aria-label="文字对话">
              <h2 className="text-sm font-medium">对话与转写</h2>
              <p className="mt-1 text-xs text-slate-400">历史仅保留在本页面内存中，离开后清除。</p>
              <div className="my-4 max-h-80 space-y-3 overflow-y-auto break-words" aria-label="消息历史">
                {!messages.length && <p className="text-sm text-slate-400">开始演示会话后输入问题，查看 Mock 交互流程。</p>}
                {messages.map(message => <article key={message.id} className="rounded-lg bg-slate-800/70 p-3 text-sm"><p className="mb-1 text-xs text-cyan-200">{message.role} · {message.market} · {modes[message.mode]} · 演示</p>{message.text}</article>)}
                {state.transcript && <p className="text-xs text-slate-300">演示转写（来自文字输入）：{state.transcript}</p>}
                {state.error && <p role="alert" className="text-sm text-amber-300">{state.error}，{connected ? '可重新发送文字。' : '请重新开始演示会话。'}</p>}
              </div>
              <form onSubmit={submit} className="space-y-2">
                <label htmlFor="damon-input" className="text-xs text-slate-300">文字消息 / 演示转写输入</label>
                <textarea id="damon-input" maxLength={2000} rows={3} value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit() }
                }} className={`w-full resize-y rounded-lg border border-slate-600 bg-slate-950 p-3 text-sm ${focus}`} placeholder="输入文字；Enter 发送，Shift+Enter 换行" />
                <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-slate-400">不发送至模型，不保存到服务器</span><button className={button} disabled={!connected || active || !draft.trim()}>发送演示消息</button></div>
              </form>
            </section>
          </div>
          <aside className={`${tab === 'research' ? '' : 'hidden lg:block'} min-w-0 space-y-4`} aria-label="任务与证据">
            <section className="rounded-xl border border-cyan-400/20 bg-slate-900/60 p-4">
              <h2 className="text-sm font-medium">研究任务 · 流程演示</h2>
              <ol className="mt-4 space-y-4 text-sm"><li>01 接收问题 · {messages.length ? '已演示' : '等待输入'}</li><li>02 工具调用 · 已阻止</li><li>03 证据核验 · 无可用证据</li><li>04 研究报告 · 未生成</li></ol>
              <p className="mt-4 text-xs text-amber-200">缺失原因：生产工具注册表为空，真实研究尚未接入。</p>
            </section>
            <section className="rounded-xl border border-slate-700 bg-slate-900/60 p-4" aria-label="证据摘要">
              <h2 className="text-sm font-medium">证据边界</h2><p className="mt-3 text-sm">{market} · {modes[mode]}</p>
              <p className="mt-3 text-xs leading-6 text-slate-300">当前证据：0 条。所有演示交互均为非生产内容；选择真实缓存或历史模式也不会查询业务服务。</p>
              <p className="mt-2 text-xs text-amber-200">Preview fixture 与模拟事件不能标记为生产证据。</p>
            </section>
            <details className="rounded-xl border border-slate-700 p-4 text-xs"><summary className={`cursor-pointer ${focus}`}>演示诊断</summary>
              <p className="my-3 break-all">连接：{state.connection} · 会话：{state.sessionId ?? '未开始'}</p>
              <button className={button} disabled={!connected} onClick={voice.fail}>模拟连接错误</button>
            </details>
          </aside>
        </div>
      </div>
    </div>
  </section>
}
