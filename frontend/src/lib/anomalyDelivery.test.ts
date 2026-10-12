import { expect, it, vi } from 'vitest'
import { AnomalyDelivery, type DeliveryState } from './anomalyDelivery'
import type { AnomalyCursor, AnomalyEvent, AnomalyIncrement } from './api'

const event = (id: number, status = 'first_trigger') => ({ store_id: id, event_id: `event-${id}`, severity: 'high', status,
  detected_at: '2026-10-09T14:05:00Z' } as AnomalyEvent)
function transport(events: AnomalyEvent[]) {
  return vi.fn(async (cursor: AnomalyCursor): Promise<AnomalyIncrement> => {
    const rows = events.filter(row => row.store_id > cursor.sequence).slice(0, 100)
    const last = rows.at(-1)
    return { rows, next_cursor: last ? { sequence: last.store_id, event_id: last.event_id } : cursor,
      has_more: events.some(row => row.store_id > (last?.store_id ?? cursor.sequence)),
      latest_sequence: events.at(-1)?.store_id ?? 0, latest_event_detected_at: events.at(-1)?.detected_at ?? null }
  })
}
it('over 100 same-time events catch up without loss; escalation re-alerts, sustained does not', async () => {
  const rows: AnomalyEvent[] = []
  const notices: string[] = []
  let delivered: AnomalyEvent[] = []
  const delivery = new AnomalyDelivery(async () => ({ rows: [], next_before_id: null }), transport(rows), (all, high) => { delivered = all; notices.push(...high.map(row => row.event_id)) })
  await delivery.poll()
  for (let id = 1; id <= 251; id++) rows.push(event(id, id === 250 ? 'sustained' : id === 251 ? 'escalation' : 'first_trigger'))
  await delivery.poll()
  expect(delivered).toHaveLength(251); expect(delivery.state.cursor?.sequence).toBe(251)
  expect(notices).toHaveLength(250); expect(notices).toContain('event-251')
  await delivery.poll(); expect(notices).toHaveLength(250)
})
it('bounded catch-up keeps the committed cursor and resumes next round', async () => {
  const rows: AnomalyEvent[] = []
  const delivery = new AnomalyDelivery(async () => ({ rows: [], next_before_id: null }), transport(rows), () => {}, 2)
  await delivery.poll()
  for (let id = 1; id <= 501; id++) rows.push(event(id))
  await delivery.poll(); expect(delivery.state.cursor?.sequence).toBe(200); expect(delivery.state.behind).toBe(true)
  expect(delivery.state.status).toBe('catching_up')
  await delivery.poll(); expect(delivery.state.cursor?.sequence).toBe(400)
  await delivery.poll(); expect(delivery.state.cursor?.sequence).toBe(501); expect(delivery.state.behind).toBe(false)
})
it('network recovery resumes saved cursor, not recent=100; sleep resume catches backlog', async () => {
  const rows: AnomalyEvent[] = [event(1)]
  const after = transport(rows)
  const readRecent = vi.fn(async () => ({ rows: [...rows], next_before_id: null }))
  const delivery = new AnomalyDelivery(readRecent, after, () => {})
  await delivery.poll()
  after.mockRejectedValueOnce(new Error('offline'))
  await delivery.poll(); expect(delivery.state.api_reachable).toBe(false); expect(delivery.state.cursor?.sequence).toBe(1)
  for (let id = 2; id <= 350; id++) rows.push(event(id))
  await delivery.poll()
  expect(delivery.state.cursor?.sequence).toBe(350); expect(readRecent).toHaveBeenCalledTimes(1)
  expect(delivery.state.last_success_at).not.toBeNull()
})
it('initial refresh restore is silent and increment inserts during pagination are retained', async () => {
  const rows = [event(1)]
  const notices: string[] = []
  const transportAfter = transport(rows)
  const after = vi.fn(async (cursor: AnomalyCursor) => {
    const result = await transportAfter(cursor)
    if (cursor.sequence === 1 && rows.length === 150) rows.push(event(151))
    return result
  })
  const delivery = new AnomalyDelivery(async () => ({ rows: [event(1)], next_before_id: null }), after,
    (_, high) => notices.push(...high.map(row => row.event_id)))
  await delivery.poll(); expect(notices).toEqual([])
  for (let id = 2; id <= 150; id++) rows.push(event(id))
  await delivery.poll(); expect(delivery.state.cursor?.sequence).toBe(151)
  expect(new Set(notices).size).toBe(150)
})
it('concurrent poll shares one request; stopped controller ignores late response', async () => {
  let resolve!: (value: AnomalyIncrement) => void
  const after = vi.fn(() => new Promise<AnomalyIncrement>(done => { resolve = done }))
  const publish = vi.fn()
  const delivery = new AnomalyDelivery(async () => ({ rows: [], next_before_id: null }), after, publish)
  const first = delivery.poll(); const overlap = delivery.poll()
  await Promise.resolve(); expect(after).toHaveBeenCalledTimes(1)
  const published = publish.mock.calls.length
  delivery.stop()
  resolve({ rows: [event(1)], next_cursor: { sequence: 1, event_id: 'event-1' }, has_more: false, latest_sequence: 1, latest_event_detected_at: event(1).detected_at })
  await Promise.all([first, overlap]); expect(publish).toHaveBeenCalledTimes(published)
  expect(delivery.state.cursor?.sequence).toBe(0)
})
it('invalid anchor never resets silently or repeatedly requests', async () => {
  const after = vi.fn(async () => { throw { status: 409 } })
  const delivery = new AnomalyDelivery(async () => ({ rows: [event(1)], next_before_id: null }), after, () => {})
  await delivery.poll(); await delivery.poll()
  expect(after).toHaveBeenCalledTimes(1); expect(delivery.state.status).toBe('cursor_invalid')
  expect(delivery.state.cursor?.sequence).toBe(1)
})
it('a regressive/out-of-order response cannot replace consumed events', async () => {
  const states: DeliveryState[] = []
  const after = vi.fn(async () => ({ rows: [event(1)], next_cursor: { sequence: 1, event_id: 'event-1' }, has_more: false, latest_sequence: 2, latest_event_detected_at: event(1).detected_at }))
  const delivery = new AnomalyDelivery(async () => ({ rows: [event(2)], next_before_id: null }), after, (_, __, ___, state) => states.push(state))
  await delivery.poll()
  expect(delivery.state.cursor?.sequence).toBe(2); expect(states.at(-1)?.status).toBe('unavailable')
})
