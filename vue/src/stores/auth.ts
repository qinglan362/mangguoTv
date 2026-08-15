import { defineStore } from 'pinia'
import { authApi } from '@/api/modules/auth'
import { tokenStorage, userStorage } from '@/utils/token'
import type { UserInfo, UserRole } from '@/types'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: userStorage.get() as UserInfo | null,
    // 登录态必须走响应式 state：Pinia getter 会缓存计算结果，
    // 若 getter 直接读 localStorage（非响应式来源），登录后写入的 token
    // 不会触发重新计算，isAuthenticated 始终停留在初始的 false，
    // 导致登录成功却无法跳转主页面。
    token: tokenStorage.getAccess() as string,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
    isAdmin: (state) => state.user?.role === 'admin',
    role: (state) => (state.user?.role || 'operator') as UserRole,
  },
  actions: {
    async login(username: string, password: string) {
      const data = await authApi.login(username, password)
      tokenStorage.set(data.access, data.refresh)
      this.token = data.access
      this.user = data.user
      userStorage.set(data.user)
    },
    async fetchMe() {
      const user = await authApi.me()
      this.user = user
      userStorage.set(user)
      return user
    },
    async logout() {
      // 先吊销后端 refresh token，再清本地；吊销失败不影响本地退出
      const refresh = tokenStorage.getRefresh()
      if (refresh) {
        try {
          await authApi.logout(refresh)
        } catch {
          // 忽略：网络/服务异常时仍允许退出
        }
      }
      tokenStorage.clear()
      userStorage.clear()
      this.token = ''
      this.user = null
    },
  },
})
