// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryObserver, type QueryFunctionContext } from '@tanstack/react-query'
import { api } from './api'
import { QK } from './queryKeys'
import { watchlistGroupsQueryFn, watchlistQueryFn } from './watchlist-query-options'

let client: QueryClient
let stops: (() => void)[]
beforeEach(() => { vi.useFakeTimers(); client = new QueryClient(); stops = [] })
afterEach(() => { stops.forEach(stop => stop()); client.clear(); vi.restoreAllMocks(); vi.useRealTimers() })
const tick = async (ms = 10) => { await vi.advanceTimersByTimeAsync(ms) }

describe.each([
  { key: QK.watchlist, fn: watchlistQueryFn, method: 'watchlistList' as const, data: { symbols: [] } },
  { key: QK.watchlistGroups, fn: watchlistGroupsQueryFn, method: 'watchlistGroups' as const, data: { groups: [] } },
])('$method shared attempt boundary', ({ key, fn, method, data }) => {
  function observe(enabled: boolean) {
    const observer = new QueryObserver<unknown>(client, { queryKey: key, queryFn: fn, enabled })
    const stop = observer.subscribe(() => {})
    stops.push(stop)
    return { observer, stop }
  }
  const query = () => client.getQueryCache().find({ queryKey: key, exact: true })!

  it('blocks a queued retry with a disabled host even after host options replace page options', async () => {
    const request = vi.spyOn(api, method).mockRejectedValue(new Error('synthetic failure'))
    const host = observe(false), page = observe(true)
    await tick(); expect(request).toHaveBeenCalledTimes(1)
    page.stop()
    host.observer.setOptions({ queryKey: key, queryFn: context => fn(context), enabled: false })
    await tick(8000)
    expect(request).toHaveBeenCalledTimes(1)
    expect(query().getObserversCount()).toBe(1)
    expect(query().state.fetchStatus).toBe('idle')
    expect(query().state.error).toBeNull()
  })
  it('retains the original three retries when a genuine shared consumer stays active', async () => {
    const request = vi.spyOn(api, method).mockRejectedValue(new Error('synthetic failure'))
    const host = observe(false), page = observe(true)
    await tick(); page.stop()
    host.observer.setOptions({ queryKey: key, queryFn: fn, enabled: true })
    await tick(3100); expect(request).toHaveBeenCalledTimes(3)
    request.mockResolvedValue(data as never)
    await tick(4100)
    expect(request).toHaveBeenCalledTimes(4)
    expect(query().state.status).toBe('success')
    expect(client.getQueryData(key)).toEqual(data)
  })
  it('guards cached invalidation and restores cached data before normal reactivation', async () => {
    const request = vi.spyOn(api, method).mockResolvedValue(data as never)
    const host = observe(false), page = observe(true)
    await tick(); const cached = client.getQueryData(key)
    request.mockRejectedValue(new Error('synthetic refetch failure'))
    host.observer.setOptions({ queryKey: key, queryFn: fn, enabled: false })
    void client.invalidateQueries({ queryKey: key, exact: true }); await tick()
    expect(request).toHaveBeenCalledTimes(2)
    page.stop(); await tick(8000)
    expect(request).toHaveBeenCalledTimes(2)
    expect(client.getQueryData(key)).toBe(cached)
    expect(query().state.status).toBe('success')
    expect(query().state.fetchStatus).toBe('idle')
    request.mockResolvedValue(data as never)
    page.observer.setOptions({ queryKey: key, queryFn: fn, enabled: true })
    const stop = page.observer.subscribe(() => {}); stops.push(stop)
    await tick(); expect(request).toHaveBeenCalledTimes(3)
  })
  it.each(['resolve', 'reject'] as const)('does not cancel an in-flight retry that later %ss', async outcome => {
    let resolve!: (value: unknown) => void, reject!: (error: Error) => void
    const pending = new Promise((yes, no) => { resolve = yes; reject = no })
    const request = vi.spyOn(api, method).mockRejectedValueOnce(new Error('synthetic first failure')).mockImplementation(() => pending as never)
    observe(false); const page = observe(true)
    await tick(1100); expect(request).toHaveBeenCalledTimes(2)
    page.stop(); expect(query().state.fetchStatus).toBe('fetching')
    if (outcome === 'resolve') resolve(data)
    else reject(new Error('synthetic late failure'))
    await tick(8000)
    expect(request).toHaveBeenCalledTimes(2)
    expect(query().state.fetchStatus).toBe('idle')
    if (outcome === 'resolve') expect(client.getQueryData(key)).toEqual(data)
  })
  it('allows a queued attempt when a consumer reactivates before its deadline', async () => {
    const request = vi.spyOn(api, method).mockRejectedValueOnce(new Error('synthetic first failure')).mockResolvedValue(data as never)
    const host = observe(false), page = observe(true)
    await tick(); page.stop(); await tick(100)
    host.observer.setOptions({ queryKey: key, queryFn: fn, enabled: true })
    await tick(1100)
    expect(request).toHaveBeenCalledTimes(2)
    expect(client.getQueryData(key)).toEqual(data)
  })
  it('rejects an incorrect key without invoking the API', () => {
    const request = vi.spyOn(api, method)
    const context: QueryFunctionContext = { client, queryKey: ['unrelated'], signal: new AbortController().signal, meta: undefined }
    expect(() => fn(context)).toThrow('Unexpected query key')
    expect(request).not.toHaveBeenCalled()
  })
})
