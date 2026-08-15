// 与后端模型对齐的共享类型定义

export type UserRole = 'admin' | 'operator'

export interface UserInfo {
  id: number
  username: string
  name: string
  role: UserRole
  is_active: boolean
  is_staff: boolean
  date_joined: string
}

export type Platform = 'xiaohongshu' | 'weibo' | 'mock'
export type TopicStatus = 'active' | 'paused' | 'archived' | 'deleted'
export type KeywordKind = 'core' | 'related' | 'exclude'
export type Sentiment = 'positive' | 'neutral' | 'negative' | 'unknown'
export type SentimentSource = 'rule' | 'llm' | 'manual'
export type RunStatus = 'pending' | 'running' | 'success' | 'failed' | 'canceled'
export type AlertLevel = 'low' | 'medium' | 'high' | 'critical'
export type AlertEventStatus = 'new' | 'acknowledged' | 'resolved'

export interface Topic {
  id: number
  name: string
  description: string
  platforms: Platform[]
  collection_interval: number
  monitor_start: string | null
  monitor_end: string | null
  status: TopicStatus
  collecting?: boolean
  owner: number | null
  created_at: string
  updated_at: string
  keywords: TopicKeyword[]
  excluded_users: TopicExclusionUser[]
}

export interface TopicKeyword {
  id: number
  topic: number
  word: string
  kind: KeywordKind
}

export interface TopicExclusionUser {
  id: number
  topic: number
  platform: Platform
  author_name: string
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface Post {
  id: number
  post_id: string
  platform: Platform
  url: string
  title: string
  content: string
  author: number | null
  author_name?: string
  published_at: string | null
  collected_at: string
  like_count: number
  comment_count: number
  share_count: number
  favorite_count: number
  hashtags: string[]
  cover_url: string | null
  images: string[]
  heat_score?: number
  sentiment?: Sentiment
}

export interface AlertRule {
  id: number
  topic: number
  name: string
  rule_type: string
  config: Record<string, unknown>
  level: AlertLevel
  enabled: boolean
  notify_channels: string[]
  notify_recipients: string[]
  cooldown_minutes: number
}

export interface AlertEvent {
  id: number
  rule: number
  rule_name?: string
  rule_type?: string
  topic: number
  topic_name?: string
  triggered_at: string
  level: AlertLevel
  level_label?: string
  reason: string
  matched_posts: Record<string, unknown>[]
  matched_keywords: string[]
  metrics: Record<string, unknown>
  status: AlertEventStatus
  status_label?: string
  handled_by: number | null
  handled_at: string | null
}

export interface AlertNotification {
  id: number
  event: number
  channel: 'platform' | 'email'
  channel_label?: string
  recipient: string
  status: 'pending' | 'sent' | 'failed'
  status_label?: string
  sent_at: string | null
  error_message: string | null
  created_at: string
}

export interface CollectionRun {
  id: number
  topic: number
  platform: Platform
  status: RunStatus
  trigger_type: 'schedule' | 'manual'
  started_at: string | null
  finished_at: string | null
  fetched_count: number
  new_count: number
  updated_count: number
  duplicate_count: number
  retry_count: number
  error_message: string | null
}
