// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AnomalyMonitoring } from './AnomalyMonitoring'
import { AnomaliesPreview } from '@/custom/damon/anomalies-preview/Presentation'
import { selectAnomaliesMode, validateAnomaliesPreview, type AnomaliesPreviewData, type AnomaliesPreviewState } from '@/custom/damon/anomalies-preview/contract'
import { loadAnomaliesPreview } from '../../tests/fixtures/anomalies_preview'
import { QK } from '@/lib/queryKeys'

const calls = vi.hoisted(() => ({ api: vi.fn(), delivery: vi.fn(), stock: vi.fn(), intelligence: vi.fn() }))
vi.mock('@/lib/useAnomalyDelivery', () => ({ useAnomalyDelivery: (...args: unknown[]) => calls.delivery(...args) }))
vi.mock('@/lib/api', () => ({ api: new Proxy({}, { get: (_t, name) => (...args: unknown[]) => calls.api(name, ...args) }) }))
vi.mock('@/components/StockPreviewDialog', () => ({ StockPreviewDialog: () => { calls.stock(); return null } }))
vi.mock('@/components/anomalies/IntelligenceContext', () => ({ IntelligenceContext: () => { calls.intelligence(); return <div data-real-intelligence /> } }))

let host: HTMLDivElement, root: Root, client: QueryClient
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); vi.clearAllMocks(); localStorage.clear(); sessionStorage.clear()
  calls.delivery.mockReturnValue({ rows: [], state: { status: 'caught_up', cursor: { sequence: 0 } } })
  calls.api.mockImplementation((name: string) => Promise.resolve(name === 'anomalyHealth' ? { state: 'not_started', diagnostics: [] } : name === 'anomalyRecent' ? { rows: [], next_before_id: null } : { contexts: {}, rows: [] }))
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
})
afterEach(async () => { await act(async () => root.unmount()); client.clear(); host.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })
async function render(query = '', element = <AnomalyMonitoring />, provider = false) {
  function Nav() { const nav = useNavigate(), loc = useLocation(); return <><output data-url>{loc.search}</output><button data-back onClick={() => nav(-1)}>返回</button><button data-forward onClick={() => nav(1)}>前进</button></> }
  await act(async () => root.render(<MemoryRouter initialEntries={['/anomalies' + query]}>{provider ? <QueryClientProvider client={client}>{element}</QueryClientProvider> : element}<Nav /></MemoryRouter>))
}
async function click(selector: string) { await act(async () => host.querySelector<HTMLButtonElement>(selector)!.click()) }
async function search(value: string) { await act(async () => {
  const el = host.querySelector<HTMLInputElement>('[aria-label="搜索异动样稿"]')!
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, value); el.dispatchEvent(new Event('input', { bubbles: true }))
}) }
async function select(label: string, value: string) { await act(async () => { const el=host.querySelector<HTMLSelectElement>(`[aria-label="${label}"]`)!; el.value=value; el.dispatchEvent(new Event('change', { bubbles:true })) }) }
it.each(['', '?market=HK', '?market=US&market=CN', '?run=real&event_id=real'])('absent data_mode keeps original ALL/CN/HK/US business entry %s', async query => {
  await render(query, <AnomalyMonitoring />, true)
  expect(calls.delivery).toHaveBeenCalled(); expect(calls.api).toHaveBeenCalledWith('anomalyHealth', expect.objectContaining({ client, queryKey: QK.anomalyHealth })); expect(calls.stock).toHaveBeenCalled()
  expect(host.querySelector('[data-anomalies-preview]')).toBeNull(); expect(host.querySelectorAll('[aria-label="市场筛选"] button')).toHaveLength(4)
  expect(host.querySelector('[aria-label="市场筛选"] button[aria-pressed="true"]')!.textContent).toBe('全部')
})
it('original earlier-event pagination still uses its cursor and original query, without Preview', async () => {
  client.setQueryData(QK.anomalyRecent(), { rows: [], next_before_id: 12 })
  await render('', <AnomalyMonitoring />, true)
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '加载更早事件')!.click())
  expect(calls.api).toHaveBeenCalledWith('anomalyRecent', 12); expect(host.textContent).not.toContain('加载更早事件')
})
const badQueries = ['?data_mode=preview', '?data_mode=preview&market=CN', '?data_mode=preview&market=hk', '?data_mode=preview&market=', '?data_mode=live&market=HK', '?data_mode=&market=HK', '?data_mode=preview&data_mode=preview&market=HK', '?data_mode=preview&data_mode=live&market=HK', '?data_mode=preview&market=HK&market=US', '?data_mode=preview&market=HK&market=HK']
it.each(badQueries)('explicit invalid parameters fail closed %s', async query => {
  await render(query)
  expect(host.querySelector('[data-anomalies-mode="error"]')).not.toBeNull(); expect(host.textContent).toContain('不回退真实业务')
  expect(calls.delivery).not.toHaveBeenCalled(); expect(calls.api).not.toHaveBeenCalled(); expect(calls.stock).not.toHaveBeenCalled()
})
it.each(['HK', 'US'] as const)('%s Preview has no real hooks, business requests, storage or notifications even with real IDs', async market => {
  const set=vi.spyOn(Storage.prototype,'setItem'), get=vi.spyOn(Storage.prototype,'getItem'), remove=vi.spyOn(Storage.prototype,'removeItem'), clear=vi.spyOn(Storage.prototype,'clear')
  const fetch=vi.fn(), notification=vi.fn(), eventSource=vi.fn(); vi.stubGlobal('fetch',fetch); vi.stubGlobal('Notification',notification); vi.stubGlobal('EventSource',eventSource)
  await render(`?data_mode=preview&market=${market}&event_id=real&episode_id=real&run=real`)
  expect(host.textContent).toContain(`${market} 合成证券 A`); expect(host.textContent).not.toContain(`${market==='HK'?'US':'HK'} 合成证券`)
  expect(host.textContent).toContain('演示数据｜非生产行情｜不构成真实异动事件或投资信号'); expect(host.textContent).toContain('is_production: false')
  expect(host.textContent).toContain(`fixture:anomalies:${market}:A:v1`); expect(host.textContent).toContain('2026-09-16')
  const disabled=host.querySelector<HTMLButtonElement>('button[title^="Preview 模式不可执行"]')!; expect(disabled.disabled).toBe(true); disabled.click()
  await click(`[data-anomaly-sample="fixture-anomaly-${market}-B"]`)
  expect(host.querySelector('[aria-label="合成异动详情"]')!.textContent).toContain('不填零')
  expect(host.querySelector('[data-anomaly-missing="health_state"]')!.textContent).toContain('未请求真实 Worker')
  expect(host.querySelector('[data-anomaly-missing="delivery_sequence"]')!.textContent).toContain('没有连接真实交付')
  for(const spy of [set,get,remove,clear,fetch,notification,eventSource,calls.delivery,calls.api,calls.stock,calls.intelligence])expect(spy).not.toHaveBeenCalled()
})
it('HK/US switch, back, forward and refresh preserve explicit mode and reset local states', async () => {
  await render('?data_mode=preview&market=HK&keep=qa'); await search('not found'); await click('[aria-label="市场选择"] button:nth-child(3)')
  expect(host.querySelector<HTMLInputElement>('input')!.value).toBe(''); expect(host.querySelector('[data-anomalies-preview="US"]')).not.toBeNull()
  expect(host.querySelector('[data-url]')!.textContent).toContain('data_mode=preview'); expect(host.querySelector('[data-url]')!.textContent).toContain('keep=qa')
  await select('样稿严重程度','low'); await click('[data-anomaly-sample="fixture-anomaly-US-B"]'); await click('[data-back]')
  expect(host.querySelector('[data-anomalies-preview="HK"]')).not.toBeNull(); expect(host.querySelector<HTMLInputElement>('input')!.value).toBe('')
  await click('[data-forward]'); expect(host.querySelector<HTMLSelectElement>('[aria-label="样稿严重程度"]')!.value).toBe('ALL')
  expect(host.querySelector('[aria-label="合成异动详情"]')!.textContent).toContain('fixture-anomaly-US-A')
  await act(async()=>root.unmount()); root=createRoot(host); await render('?data_mode=preview&market=US'); expect(host.querySelector('[data-anomalies-preview="US"]')).not.toBeNull()
  expect(calls.delivery).not.toHaveBeenCalled(); expect(calls.api).not.toHaveBeenCalled()
})
it('search/type/severity filtering, null-last sorting, details and focus work without timers', async () => {
  await render('?data_mode=preview&market=HK'); await select('样稿异动类型','intraday_breakout'); expect(host.querySelectorAll('[data-anomaly-sample]')).toHaveLength(1)
  await select('样稿严重程度','high'); expect(host.textContent).toContain('暂无匹配'); await select('样稿严重程度','ALL'); await select('样稿异动类型','ALL')
  await click('[aria-label="按演示涨跌幅排序"]'); expect(host.querySelectorAll('[data-anomaly-sample]')[0].getAttribute('data-anomaly-sample')).toBe('fixture-anomaly-HK-A')
  await click('[aria-label="按演示涨跌幅排序"]'); expect(host.querySelectorAll('[data-anomaly-sample]')[0].getAttribute('data-anomaly-sample')).toBe('fixture-anomaly-HK-A')
  await click('[aria-label="按演示涨跌幅排序"]'); expect(host.querySelectorAll('th')[2].getAttribute('aria-sort')).toBe('none')
  const sort=host.querySelector<HTMLButtonElement>('[aria-label="按合成证券 / 身份排序"]')!;sort.focus();expect(document.activeElement).toBe(sort);expect(sort.type).toBe('button')
  await search('SYNTH-B.HK');expect(host.querySelectorAll('[data-anomaly-sample]')).toHaveLength(1)
})
it('error, loading, empty and mixed-market envelopes retain declaration without fallback', async () => {
  const states: AnomaliesPreviewState[]=[{kind:'error'},{kind:'loading'},{kind:'ready',data:{...loadAnomaliesPreview('HK'),rows:[]}},{kind:'ready',data:loadAnomaliesPreview('US')}]
  for(const state of states){await render('',<AnomaliesPreview market="HK" state={state}/>);expect(host.querySelector('[role="note"]')!.textContent).toContain('不构成真实异动事件');expect(host.querySelector('[data-anomaly-sample]')).toBeNull()}
  expect(host.textContent).toContain('异动样稿加载失败');expect(calls.api).not.toHaveBeenCalled()
})
it('direct non-router legacy mount is retained and malformed explicit URL also fails closed', async () => {
  await act(async()=>root.render(<QueryClientProvider client={client}><AnomalyMonitoring/></QueryClientProvider>));expect(calls.delivery).toHaveBeenCalled()
  await act(async()=>root.unmount());root=createRoot(host);vi.clearAllMocks();history.replaceState(null,'','/?data_mode=preview')
  try{await act(async()=>root.render(<AnomalyMonitoring/>));expect(host.querySelector('[data-anomalies-mode="error"]')).not.toBeNull();expect(calls.delivery).not.toHaveBeenCalled()}finally{history.replaceState(null,'','/')}
})
it('fixed fixtures remain independent of current date, returned references and source event IDs', () => {
  const hk=loadAnomaliesPreview('HK'),us=loadAnomaliesPreview('US');vi.useFakeTimers();vi.setSystemTime(new Date('2040-01-01T00:00:00Z'))
  expect(loadAnomaliesPreview('HK')).toEqual(hk);expect(loadAnomaliesPreview('US')).toEqual(us);expect(hk.rows).not.toBe(loadAnomaliesPreview('HK').rows)
  expect(hk.rows[0].event_time).not.toBe(us.rows[0].event_time)
})
it.each(['HK','US'] as const)('%s fixture validates and unknown production fields remain null',market=>{
  const d=loadAnomaliesPreview(market);expect(validateAnomaliesPreview(d)).toBe(d);expect(d.rows.every(r=>Object.values(r.unknown).every(v=>v===null))).toBe(true)
})
const invalid: [string,(d:AnomaliesPreviewData)=>void][]=[
  ['mixed market',d=>{Object.assign(d.rows[0],{market:'US'})}], ['production ID',d=>{d.rows[0].sample_id='a'.repeat(64)}],
  ['real symbol',d=>{d.rows[0].symbol='00700.HK'}], ['duplicate ID',d=>{Object.assign(d.rows[1],d.rows[0])}],
  ['provenance',d=>{Object.assign(d.rows[0],{source:'longbridge_snapshot_archive'})}], ['false synthetic',d=>{Object.assign(d.rows[0],{synthetic:false})}],
  ['production ready',d=>{Object.assign(d.rows[0],{execution_status:'READY'})}], ['real health',d=>{Object.assign(d.rows[0].unknown,{health_state:'observing'})}],
  ['fake cursor zero',d=>{Object.assign(d.rows[0].unknown,{delivery_sequence:0})}], ['null reason absent',d=>{delete d.rows[0].missing_reasons.production_event_id}],
  ['null change reason absent',d=>{delete d.rows[1].missing_reasons.change_pct}], ['NaN',d=>{d.rows[0].change_pct=NaN}],
  ['Infinity',d=>{d.rows[0].condition.window_minutes=Infinity}], ['numeric string',d=>{Object.assign(d.rows[0],{change_pct:'0.02'})}],
  ['missing window reason',d=>{delete d.rows[1].missing_reasons.window_minutes}], ['timestamp naive',d=>{d.rows[0].event_time='2026-09-16T06:00:00'}],
  ['invalid date',d=>{d.trading_date='2026-02-31'}], ['wrong evidence',d=>{d.rows[0].evidence='production:event'}],
  ['additional action',d=>{Object.assign(d.rows[0],{acknowledge:true})}],
]
it.each(invalid)('contract rejects %s',(_label,mutate)=>{const d=loadAnomaliesPreview('HK');mutate(d);expect(()=>validateAnomaliesPreview(d)).toThrow()})
it('mode selector rejects duplicate parameters rather than selecting the first value',()=>{
  expect(selectAnomaliesMode(new URLSearchParams('data_mode=preview&market=HK&market=US'))).toEqual({kind:'error'})
})
