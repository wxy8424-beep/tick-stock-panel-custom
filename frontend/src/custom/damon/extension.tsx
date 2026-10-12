import { lazy, Suspense } from 'react'
import { Activity } from 'lucide-react'
import type { FrontendExtension } from '@/extensions/types'

const Page = lazy(() => import('@/pages/AnomalyMonitoring').then(module => ({ default: module.AnomalyMonitoring })))
const extension: FrontendExtension = {
  id: 'damon.anomaly-monitoring', apiVersion: 1,
  routes: [{ id: 'damon-anomalies', path: '/anomalies', component: () => <Suspense fallback={<p>加载异动监控…</p>}><Page /></Suspense> }],
  navigation: [{ id: 'damon-anomalies', routeId: 'damon-anomalies', label: '实时异动流', icon: Activity, order: 13 }],
}
export default extension
