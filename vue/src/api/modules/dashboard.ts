import http from '@/api'

export interface DashboardFilters {
  topic?: number
  topics?: string
  platform?: string
  start?: string
  end?: string
  bucket?: 'hour' | 'day'
  limit?: number
  window?: string
}

export const dashboardApi = {
  overview: (params: DashboardFilters = {}) => http.get('/dashboard/overview/', { params }),
  trend: (params: DashboardFilters = {}) => http.get('/dashboard/trend/', { params }),
  platformDistribution: (params: DashboardFilters = {}) => http.get('/dashboard/platform-distribution/', { params }),
  sentimentDistribution: (params: DashboardFilters = {}) => http.get('/dashboard/sentiment-distribution/', { params }),
  interactionTrend: (params: DashboardFilters = {}) => http.get('/dashboard/interaction-trend/', { params }),
  hotPosts: (params: DashboardFilters = {}) => http.get('/dashboard/hot-posts/', { params }),
  negativePosts: (params: DashboardFilters = {}) => http.get('/dashboard/negative-posts/', { params }),
  // 高频关键词走 LLM 精选（推理模型实测约 2 分钟），单独放宽超时，不受全局 30s 限制
  topKeywords: (params: DashboardFilters = {}) =>
    http.get('/dashboard/top-keywords/', { params, timeout: 180000 }),
  heatTrend: (params: DashboardFilters = {}) => http.get('/dashboard/heat-trend/', { params }),
  keyAuthors: (params: DashboardFilters = {}) => http.get('/dashboard/key-authors/', { params }),
  topicCompare: (params: DashboardFilters = {}) => http.get('/dashboard/topic-compare/', { params }),
}
