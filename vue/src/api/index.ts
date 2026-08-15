import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import { tokenStorage, userStorage } from '@/utils/token'

// 底层 axios 实例：拦截器已返回 response.data
const instance = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截：自动附加 Bearer token
instance.interceptors.request.use((config) => {
  const token = tokenStorage.getAccess()
  if (token) {
    config.headers = config.headers || {}
    ;(config.headers as Record<string, string>).Authorization = `Bearer ${token}`
  }
  return config
})

interface RetryConfig extends AxiosRequestConfig {
  _retried?: boolean
}

let refreshPromise: Promise<string> | null = null

// 用独立 axios 刷新 token（避免走拦截器造成递归）
async function refreshAccess(): Promise<string> {
  const refreshToken = tokenStorage.getRefresh()
  if (!refreshToken) throw new Error('no refresh token')
  const resp = await axios.post('/api/auth/refresh/', { refresh: refreshToken })
  // 后端开启了 ROTATE_REFRESH_TOKENS：响应携带新的 refresh token，必须保存新版，
  // 否则旧 token 已被黑名单，下一次刷新必然 401 导致会话被强制登出。
  const data = resp.data as { access: string; refresh?: string }
  tokenStorage.set(data.access, data.refresh || refreshToken)
  return data.access
}

instance.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const status = error?.response?.status as number | undefined
    const config = error?.config as RetryConfig | undefined
    const url: string | undefined = config?.url

    // 登录接口 401：明确提示用户名或密码错误
    if (status === 401 && /\/auth\/login\/$/.test(url || '')) {
      ElMessage.error('用户名或密码错误')
      return Promise.reject(error)
    }

    // 其余 401：刷新 token 后重试一次
    if (status === 401 && config && !config._retried) {
      config._retried = true
      try {
        refreshPromise = refreshPromise || refreshAccess()
        const newToken = await refreshPromise
        refreshPromise = null
        config.headers = config.headers || {}
        ;(config.headers as Record<string, string>).Authorization = `Bearer ${newToken}`
        return instance(config)
      } catch {
        // 刷新失败：会话彻底失效，清空本地登录态并回登录页（携带回跳地址）
        refreshPromise = null
        tokenStorage.clear()
        userStorage.clear()
        ElMessage.error('登录已过期，请重新登录')
        const current = window.location.pathname + window.location.search
        const target = current.startsWith('/login')
          ? '/login'
          : '/login?redirect=' + encodeURIComponent(current)
        window.location.href = target
        return Promise.reject(error)
      }
    }

    const message = error?.response?.data?.detail || error?.response?.data?.message || error.message || '请求失败'
    ElMessage.error(message)
    return Promise.reject(error)
  },
)

/** 类型化请求包装：get/post 等直接返回响应数据（Promise<T>），而非 AxiosResponse。
 *  axios 1.19 的实例方法返回 AxiosResponseResult，此处强制断言为业务类型。 */
export function get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
  return instance.get(url, config) as Promise<T>
}

export function post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return instance.post(url, data, config) as Promise<T>
}

export function put<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return instance.put(url, data, config) as Promise<T>
}

export function patch<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return instance.patch(url, data, config) as Promise<T>
}

export function del<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
  return instance.delete(url, config) as Promise<T>
}

const http = { get, post, put, patch, delete: del }

export default http
