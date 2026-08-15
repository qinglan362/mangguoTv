import http from '@/api'
import type { Paginated } from '@/types'

export interface CrawledComment {
  id: number
  post: number | null
  platform: string
  platform_post_id: string
  comment_id: string
  author_name: string
  content: string
  like_count: number
  published_at: string | null
  collected_at: string
}

export const crawlerApi = {
  comments: (postId: number) =>
    http.get('/crawler/comments/', { params: { post: postId } }) as Promise<Paginated<CrawledComment>>,
}
export interface MediaCrawlerRunInfo {
  id: number
  platform: string
  topic: number | null
  topic_name: string
  keywords: string
  status: 'running' | 'queued' | 'finished' | 'importing' | 'failed' | 'stopped'
  status_label: string
  pid: number | null
  exit_code: number | null
  fetched_count: number
  new_count: number
  duplicate_count: number
  updated_count: number
  comment_count: number
  error_message: string
  started_at: string
  finished_at: string | null
}

export interface MediaCrawlerStatus {
  running: boolean
  run: MediaCrawlerRunInfo | null
  log_tail: string
}

export const mediacrawlerApi = {
  run: (data: { topic_id: number; platform?: string; max_notes?: number }) =>
    http.post<MediaCrawlerRunInfo>('/crawler/mediacrawler/run/', data),
  status: (topicId?: number) =>
    http.get<MediaCrawlerStatus>('/crawler/mediacrawler/status/', { params: topicId ? { topic: topicId } : {} }),
  stop: () => http.post<{ stopped: boolean }>('/crawler/mediacrawler/stop/'),
  importData: (topic_id: number) =>
    http.post<MediaCrawlerRunInfo>('/crawler/mediacrawler/import/', { topic_id }),
}
