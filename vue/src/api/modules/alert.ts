import http from '@/api'
import type { AlertEvent, AlertNotification, AlertRule, Paginated } from '@/types'

export const alertApi = {
  events: (params: Record<string, unknown> = {}) => http.get<Paginated<AlertEvent>>('/alerts/events/', { params }),
  eventDetail: (id: number) => http.get<AlertEvent>(`/alerts/events/${id}/`),
  ackEvent: (id: number) => http.post<AlertEvent>(`/alerts/events/${id}/ack/`),
  resolveEvent: (id: number) => http.post<AlertEvent>(`/alerts/events/${id}/resolve/`),
  notifications: (params: Record<string, unknown> = {}) => http.get<Paginated<AlertNotification>>('/alerts/notifications/', { params }),
  rules: (params: Record<string, unknown> = {}) => http.get<Paginated<AlertRule>>('/alerts/rules/', { params }),
  createRule: (data: Partial<AlertRule>) => http.post<AlertRule>('/alerts/rules/', data),
  updateRule: (id: number, data: Partial<AlertRule>) => http.patch<AlertRule>(`/alerts/rules/${id}/`, data),
  deleteRule: (id: number) => http.delete(`/alerts/rules/${id}/`),
}

export type { AlertEvent, AlertRule }
