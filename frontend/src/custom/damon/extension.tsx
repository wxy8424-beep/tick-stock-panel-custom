import { lazy, Suspense } from 'react'
import { Activity, Bot } from 'lucide-react'
import type { FrontendExtension } from '@/extensions/types'

const Page = lazy(() => import('@/pages/AnomalyMonitoring').then(module => ({ default: module.AnomalyMonitoring })))
const DamonAI = lazy(() => import('./ai/DamonAIPage').then(module => ({ default: module.DamonAIPage })))
const extension: FrontendExtension = {
  id: 'damon.anomaly-monitoring', apiVersion: 1,
  routes: [
    { id: 'damon-anomalies', path: '/anomalies', component: () => <Suspense fallback={<p>加载异动监控…</p>}><Page /></Suspense> },
    { id: 'damon-ai', path: '/damon/ai', component: () => <Suspense fallback={<p>加载 Damon AI…</p>}><DamonAI /></Suspense> },
  ],
  navigation: [
    { id: 'damon-anomalies', routeId: 'damon-anomalies', label: '实时异动流', icon: Activity, order: 13 },
    { id: 'damon-ai', routeId: 'damon-ai', label: 'Damon AI', icon: Bot, order: 14 },
  ],
}
export default extension
