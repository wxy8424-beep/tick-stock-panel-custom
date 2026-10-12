import type { AnomalyCursor, AnomalyEvent, AnomalyIncrement, AnomalyPage } from './api'
import { AttentionLedger } from './anomalyPresentation'

export interface DeliveryState {
  cursor: AnomalyCursor | null; last_success_at: string | null; latest_event_detected_at: string | null
  latest_sequence: number | null; api_reachable: boolean | null; behind: boolean | null
  status: 'initializing' | 'caught_up' | 'catching_up' | 'unavailable' | 'cursor_invalid' | 'stopped'
  error: string | null
}
export class AnomalyDelivery {
  private busy: Promise<void> | null = null
  private stopped = false
  private initialized = false
  private ledger = new AttentionLedger()
  private events = new Map<string, AnomalyEvent>()
  private pendingHigh: AnomalyEvent[] = []
  private pendingFresh: AnomalyEvent[] = []
  state: DeliveryState = { cursor: null, last_success_at: null, latest_event_detected_at: null,
    latest_sequence: null, api_reachable: null, behind: null, status: 'initializing', error: null }
  constructor(private recent: () => Promise<AnomalyPage>, private after: (cursor: AnomalyCursor) => Promise<AnomalyIncrement>,
    private publish: (rows: AnomalyEvent[], high: AnomalyEvent[], fresh: AnomalyEvent[], state: DeliveryState) => void,
    private maxPages = 10) {}
  private emit(rows: AnomalyEvent[]) {
    const attention = this.ledger.accept(rows)
    for (const row of rows) this.events.set(row.event_id, row)
    this.pendingHigh.push(...attention.high)
    this.pendingFresh.push(...attention.fresh)
  }
  private flush() {
    this.publish([...this.events.values()], this.pendingHigh, this.pendingFresh, { ...this.state })
    this.pendingHigh = []; this.pendingFresh = []
  }
  poll(): Promise<void> {
    if (this.stopped || this.state.status === 'cursor_invalid') return Promise.resolve()
    if (this.busy) return this.busy // One shared in-flight operation; late responses cannot overwrite it.
    this.busy = this.run().finally(() => { this.busy = null })
    return this.busy
  }
  stop() { this.stopped = true }
  private async run() {
    try {
      if (!this.initialized) {
        const page = await this.recent()
        if (this.stopped) return
        const latest = [...page.rows].sort((a, b) => b.store_id - a.store_id)[0]
        this.state.cursor = page.resume_cursor ?? { sequence: latest?.store_id ?? 0, event_id: latest?.event_id ?? null }
        this.initialized = true
        this.state.last_success_at = new Date().toISOString()
        this.state.api_reachable = true
        this.emit(page.rows) // Bootstrap history is deliberately silent.
        this.flush()
      }
      for (let count = 0; count < this.maxPages; count++) {
        const cursor = { ...this.state.cursor! }
        const page = await this.after(cursor)
        if (this.stopped) return
        const ordered = [...page.rows].sort((a, b) => a.store_id - b.store_id)
        // Reject response regression instead of silently skipping a cursor gap.
        if (page.next_cursor.sequence < cursor.sequence || page.latest_sequence < page.next_cursor.sequence
            || ordered.some(row => row.store_id <= cursor.sequence || row.store_id > page.next_cursor.sequence)
            || (ordered.length === 0 && (page.next_cursor.sequence !== cursor.sequence || page.next_cursor.event_id !== cursor.event_id))
            || (page.has_more && page.next_cursor.sequence <= cursor.sequence)
            || (ordered.length > 0 && (ordered[ordered.length - 1].store_id !== page.next_cursor.sequence
              || ordered[ordered.length - 1].event_id !== page.next_cursor.event_id))) throw new Error('delivery_contract_mismatch')
        this.state = { ...this.state, cursor: page.next_cursor, latest_sequence: page.latest_sequence,
          latest_event_detected_at: page.latest_event_detected_at, last_success_at: new Date().toISOString(),
          api_reachable: true, behind: page.has_more || page.next_cursor.sequence < page.latest_sequence,
          status: page.has_more ? 'catching_up' : 'caught_up', error: null }
        this.emit(ordered)
        this.flush() // Publish HIGH promptly, not after the entire backlog round.
        if (!page.has_more) break
      }
    } catch (error) {
      if (this.stopped) return
      const stale = typeof error === 'object' && error !== null && 'status' in error && error.status === 409
      this.state = { ...this.state, api_reachable: false, behind: null, status: stale ? 'cursor_invalid' : 'unavailable',
        error: stale ? '交付游标失效，请刷新重新恢复历史' : '增量交付失败，保留游标等待恢复' }
      this.emit([])
      this.flush()
    }
  }
}
