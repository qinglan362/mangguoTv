import http from '@/api'

export interface CollectorStatus {
  platform: string
  display_name: string
  enabled: boolean
  issues: string[]
}

export const collectorApi = {
  list: () => http.get<CollectorStatus[]>('/collectors/'),
}
