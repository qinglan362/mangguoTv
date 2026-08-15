import http from '@/api'
import type { CollectionRun } from '@/types'

export const taskApi = {
  runs: (params: Record<string, unknown> = {}) => http.get('/tasks/runs/', { params }),
  runDetail: (id: number) => http.get(`/tasks/runs/${id}/`),
  status: () => http.get('/tasks/status/'),
}

export type { CollectionRun }
