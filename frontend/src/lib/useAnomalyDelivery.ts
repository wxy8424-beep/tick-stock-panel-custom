import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api, type AnomalyEvent } from './api'
import { QK } from './queryKeys'
import { AnomalyDelivery, type DeliveryState } from './anomalyDelivery'

export function useAnomalyDelivery(onAttention?: (high: AnomalyEvent[], fresh: AnomalyEvent[]) => void) {
  const client = useQueryClient()
  const [snapshot, setSnapshot] = useState<{ rows: AnomalyEvent[]; high: AnomalyEvent[]; fresh: AnomalyEvent[]; state: DeliveryState | null }>({ rows: [], high: [], fresh: [], state: null })
  useEffect(() => {
    const delivery = new AnomalyDelivery(
      () => client.fetchQuery({ queryKey: QK.anomalyRecent(), queryFn: () => api.anomalyRecent(), staleTime: 0, retry: false }),
      cursor => client.fetchQuery({ queryKey: QK.anomalyIncremental(cursor.sequence, cursor.event_id), queryFn: () => api.anomalyIncremental(cursor), staleTime: 0, retry: false }),
      (rows, high, fresh, state) => { setSnapshot({ rows, high, fresh, state }); onAttention?.(high, fresh) },
    )
    const poll = () => { if (document.visibilityState !== 'hidden') void delivery.poll() }
    poll()
    const timer = setInterval(poll, 3000)
    window.addEventListener('focus', poll)
    document.addEventListener('visibilitychange', poll)
    return () => { clearInterval(timer); delivery.stop(); window.removeEventListener('focus', poll); document.removeEventListener('visibilitychange', poll) }
  }, [client, onAttention])
  return snapshot
}
