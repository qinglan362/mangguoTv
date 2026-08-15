<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const currentTitle = computed(() => (route.meta.title as string) || '')
const displayName = computed(() => auth.user?.name || auth.user?.username || '')
const roleLabel = computed(() => (auth.isAdmin ? '管理员' : '运营'))

async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定退出登录吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  await auth.logout()
  router.replace('/login')
}
</script>

<template>
  <el-container class="app-layout">
    <el-aside width="220px" class="app-aside">
      <div class="app-logo">
        <span class="logo-text">舆情收集平台</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        class="app-menu"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>分析看板</span>
        </el-menu-item>
        <el-menu-item index="/topics">
          <el-icon><Collection /></el-icon>
          <span>主题管理</span>
        </el-menu-item>
        <el-menu-item index="/posts">
          <el-icon><Document /></el-icon>
          <span>帖子列表</span>
        </el-menu-item>
        <el-menu-item index="/alerts">
          <el-icon><Warning /></el-icon>
          <span>预警中心</span>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><Tickets /></el-icon>
          <span>报告与导出</span>
        </el-menu-item>
        <el-menu-item v-if="auth.isAdmin" index="/users">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
        <el-menu-item v-if="auth.isAdmin" index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <div class="header-title">{{ currentTitle }}</div>
        <div class="header-right">
          <el-tag type="info" size="small" effect="plain">芒果TV舆情监测</el-tag>
          <el-dropdown trigger="click" @command="handleLogout">
            <span class="user-entry">
              <el-icon class="user-icon"><UserFilled /></el-icon>
              <span class="user-name">{{ displayName }}</span>
              <el-tag :type="auth.isAdmin ? 'danger' : 'success'" size="small" effect="light">{{ roleLabel }}</el-tag>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.app-layout {
  height: 100vh;
}
.app-aside {
  background-color: #001529;
  color: #fff;
}
.app-logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.logo-text {
  color: #fff;
  font-size: 18px;
  font-weight: 600;
}
.app-menu {
  border-right: none;
  background-color: #001529;
  --el-menu-text-color: #b3b8c2;
  --el-menu-hover-bg-color: #1f2d3d;
  --el-menu-active-color: #409eff;
}
.app-header {
  background: #fff;
  border-bottom: 1px solid #e5e6eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header-title {
  font-size: 16px;
  font-weight: 600;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.user-entry {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  outline: none;
}
.user-icon {
  color: #409eff;
}
.user-name {
  font-size: 14px;
  color: #303133;
}
.app-main {
  background: #f5f6f7;
  padding: 16px;
  overflow-y: auto;
}
</style>
