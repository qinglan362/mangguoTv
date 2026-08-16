import http from '@/api'
import type { CollectionRun } from '@/types'

export interface SchedulerJob {
  id: string
  name: string
  kind: 'topic' | 'report' | 'reconcile' | 'retry' | 'snapshot' | 'unknown'
  topic_id?: number | null
  topic_name?: string | null
  trigger: string
  interval_minutes?: number | null
  next_run_time: string | null
  last_run_at?: string | null
  last_run_status?: string | null
}

export interface SchedulerFailedRun {
  id: number
  topic_id: number
  platform: string
  error_message: string
}

export interface SchedulerStatus {
  scheduler_running: boolean
  dispatch_running: boolean
  active_jobs: SchedulerJob[]
  pending_queue: number
  running_count: number
  recent_failed: SchedulerFailedRun[]
}

export const taskApi = {
  runs: (params: Record<string, unknown> = {}) => http.get('/tasks/runs/', { params }),
  runDetail: (id: number) => http.get('/tasks/runs/' + id + '/'),
  status: () => http.get<SchedulerStatus>('/tasks/status/'),
}

export type { CollectionRun }
