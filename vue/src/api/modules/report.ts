import http from '@/api'
import type { Paginated } from '@/types'

export interface DataExportRecord {
  id: number
  requester_name: string
  export_type: 'post' | 'full'
  filters: Record<string, unknown>
  file_path: string | null
  status: 'pending' | 'running' | 'done' | 'failed'
  row_count: number
  download_url: string | null
  created_at: string
  finished_at: string | null
}

export interface ReportRecord {
  id: number
  topic: number
  topic_name: string
  period_type: 'daily' | 'weekly'
  period_type_label: string
  report_date: string
  title: string
  summary: string
  statistics: Record<string, unknown>
  status: 'generating' | 'done' | 'failed'
  status_label: string
  generated_at: string | null
  created_at: string
}

export const reportApi = {
  exports: (params: Record<string, unknown> = {}) => http.get<Paginated<DataExportRecord>>('/reports/exports/', { params }),
  createExport: (data: { export_type: string; filters: Record<string, unknown> }) => http.post<DataExportRecord>('/reports/exports/', data),
  downloadUrl: (id: number) => `/api/reports/exports/${id}/download/`,
  reports: (params: Record<string, unknown> = {}) => http.get<Paginated<ReportRecord>>('/reports/reports/', { params }),
  generate: (data: { topic: number; period_type: 'daily' | 'weekly' }) => http.post<ReportRecord>('/reports/reports/generate/', data),
}

export type { Paginated }
