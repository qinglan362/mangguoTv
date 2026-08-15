import http from '@/api'
import type { Paginated, Post } from '@/types'

export interface PostFilters {
  topic?: number
  platform?: string
  sentiment?: string
  is_related?: boolean
  q?: string
  ordering?: string
  page?: number
  page_size?: number
}

export const postApi = {
  list: (params: PostFilters = {}) => http.get('/posts/', { params }) as Promise<Paginated<Post>>,
  detail: (id: number) => http.get(`/posts/${id}/`),
  history: (id: number) => http.get(`/posts/${id}/history/`),
}

export type { Post }
