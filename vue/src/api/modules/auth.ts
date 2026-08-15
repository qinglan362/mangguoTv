import http from '@/api'
import type { Paginated, UserInfo } from '@/types'

export interface LoginResult {
  access: string
  refresh: string
  user: UserInfo
}

export interface UserCreatePayload {
  username: string
  name?: string
  password: string
  role: 'admin' | 'operator'
}

export interface UserUpdatePayload {
  name?: string
  role?: 'admin' | 'operator'
  is_active?: boolean
}

export const authApi = {
  login: (username: string, password: string) => http.post<LoginResult>('/auth/login/', { username, password }),
  me: () => http.get<UserInfo>('/auth/me/'),
  logout: (refresh?: string) => http.post<{ detail: string }>('/auth/logout/', refresh ? { refresh } : undefined),
  users: (params: Record<string, unknown> = {}) => http.get<Paginated<UserInfo>>('/users/', { params }),
  createUser: (data: UserCreatePayload) => http.post<UserInfo>('/users/', data),
  updateUser: (id: number, data: UserUpdatePayload) => http.patch<UserInfo>(`/users/${id}/`, data),
  resetPassword: (id: number, password: string) => http.post<{ detail: string }>(`/users/${id}/reset_password/`, { password }),
  deactivateUser: (id: number) => http.delete(`/users/${id}/`),
}
