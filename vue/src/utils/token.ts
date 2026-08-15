// 登录态本地持久化：token 与用户信息缓存，
// 供 axios 拦截器与 auth store 共用，避免循环依赖。
import type { UserInfo } from '@/types'

const ACCESS_KEY = 'yq_access_token'
const REFRESH_KEY = 'yq_refresh_token'
const USER_KEY = 'yq_user'

export const tokenStorage = {
  getAccess: () => localStorage.getItem(ACCESS_KEY) || '',
  getRefresh: () => localStorage.getItem(REFRESH_KEY) || '',
  set(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

export const userStorage = {
  get(): UserInfo | null {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || 'null') as UserInfo | null
    } catch {
      return null
    }
  },
  set(user: UserInfo) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  },
  clear() {
    localStorage.removeItem(USER_KEY)
  },
}
