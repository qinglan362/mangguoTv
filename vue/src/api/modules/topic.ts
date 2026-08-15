import http from '@/api'
import type { Paginated, Topic, TopicKeyword } from '@/types'

export interface TopicPayload {
  name: string
  description?: string
  platforms: string[]
  collection_interval: number
  monitor_start?: string | null
  monitor_end?: string | null
  keywords_inline?: { word: string; kind: string }[]
  keywords?: { word: string; kind: string }[]
  excluded_users_inline?: { platform: string; author_name: string }[]
  excluded_users?: { platform: string; author_name: string }[]
}

export const topicApi = {
  list: (params?: Record<string, unknown>) => http.get('/topics/', { params }) as Promise<Paginated<Topic>>,
  detail: (id: number) => http.get(`/topics/${id}/`) as Promise<Topic>,
  create: (data: TopicPayload) => http.post('/topics/', data) as Promise<Topic>,
  update: (id: number, data: Partial<TopicPayload>) => http.patch(`/topics/${id}/`, data) as Promise<Topic>,
  remove: (id: number) => http.delete(`/topics/${id}/`),
  pause: (id: number) => http.post(`/topics/${id}/pause/`),
  resume: (id: number) => http.post(`/topics/${id}/resume/`),
  collectNow: (id: number) => http.post(`/topics/${id}/collect_now/`),
  stats: (id: number) => http.get(`/topics/${id}/stats/`),
}

export type { Topic, TopicKeyword }
