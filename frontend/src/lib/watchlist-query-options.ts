import { CancelledError, type QueryFunctionContext } from '@tanstack/react-query'
import { api } from './api'
import { QK } from './queryKeys'

function requireActiveObserver(context: QueryFunctionContext, key: readonly [string]) {
  if (context.queryKey.length !== 1 || context.queryKey[0] !== key[0]) {
    throw new Error(`Unexpected query key for ${key[0]}`)
  }
  const query = context.client.getQueryCache().find({ queryKey: key, exact: true })
  if (query?.isActive()) return
  // Only end this unneeded attempt before its HTTP starts. In-flight requests are
  // untouched, and any enabled shared observer authorizes the normal request.
  void query?.cancel({ revert: true })
  throw new CancelledError({ revert: true })
}

// Every observer of these keys must use these entry points: the last observer's
// options may be used by invalidation and retries. Do not read context.signal,
// which would change the existing in-flight completion/cache semantics.
export function watchlistQueryFn(context: QueryFunctionContext) {
  requireActiveObserver(context, QK.watchlist)
  return api.watchlistList()
}

export function watchlistGroupsQueryFn(context: QueryFunctionContext) {
  requireActiveObserver(context, QK.watchlistGroups)
  return api.watchlistGroups()
}
