import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
// @ts-ignore
import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    requiresAdmin?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/Login.vue'),
      meta: { title: '登录' },
    },
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', redirect: '/dashboard' },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('@/views/Dashboard.vue'),
          meta: { title: '分析看板' },
        },
        {
          path: 'topics',
          name: 'topics',
          component: () => import('@/views/topics/TopicList.vue'),
          meta: { title: '主题管理' },
        },
        {
          path: 'topics/create',
          name: 'topic-create',
          component: () => import('@/views/topics/TopicEdit.vue'),
          meta: { title: '新建主题' },
        },
        {
          path: 'topics/:id',
          name: 'topic-detail',
          component: () => import('@/views/topics/TopicDetail.vue'),
          meta: { title: '主题详情' },
        },
        {
          path: 'topics/:id/edit',
          name: 'topic-edit',
          component: () => import('@/views/topics/TopicEdit.vue'),
          meta: { title: '编辑主题' },
        },
        {
          path: 'posts',
          name: 'posts',
          component: () => import('@/views/posts/PostList.vue'),
          meta: { title: '帖子列表' },
        },
        {
          path: 'posts/:id',
          name: 'post-detail',
          component: () => import('@/views/posts/PostDetail.vue'),
          meta: { title: '帖子详情' },
        },
        {
          path: 'alerts',
          name: 'alerts',
          component: () => import('@/views/alerts/AlertCenter.vue'),
          meta: { title: '预警中心' },
        },
        {
          path: 'reports',
          name: 'reports',
          component: () => import('@/views/reports/ReportList.vue'),
          meta: { title: '报告与导出' },
        },
        {
          path: 'users',
          name: 'users',
          component: () => import('@/views/users/UserList.vue'),
          meta: { title: '用户管理', requiresAdmin: true },
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/views/settings/Settings.vue'),
          meta: { title: '系统设置', requiresAdmin: true },
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  // 已登录访问登录页 → 回看板
  if (to.path === '/login') {
    if (auth.isAuthenticated) return '/dashboard'
    return true
  }

  // 未登录 → 登录页（记录来源，登录后跳回）
  if (!auth.isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 有 token 但本地无用户信息（刷新/缓存丢失）→ 拉取一次；
  // 拉取失败说明会话已失效，回登录页而不是中断导航卡死当前页
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }

  // 管理员专属页面
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    ElMessage.warning('无权限访问该页面')
    return '/dashboard'
  }

  return true
})

export default router
