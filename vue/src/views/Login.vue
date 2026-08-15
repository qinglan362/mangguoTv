<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const errorMsg = ref('')

function clearError() {
  errorMsg.value = ''
}

async function onSubmit() {
  errorMsg.value = ''
  if (!form.username || !form.password) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  try {
    await auth.login(form.username, form.password)
  } catch {
    // 错误提示由 axios 拦截器统一处理；此处再显示内联提示，避免遗漏
    errorMsg.value = '用户名或密码错误，请重试'
    loading.value = false
    return
  }
  loading.value = false
  // 登录成功：跳回来源页。仅接受站内路径，防止开放重定向；默认回分析看板
  const q = route.query.redirect
  const redirect = typeof q === 'string' && q.startsWith('/') && !q.startsWith('//') ? q : '/dashboard'
  await router.replace(redirect)
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <div class="login-title">
        <h2>舆情收集平台</h2>
        <p>芒果TV舆情监测 · 内部系统</p>
      </div>
      <el-form :model="form" label-position="top" @submit.prevent="onSubmit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" autocomplete="username" size="large" @input="clearError" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            autocomplete="current-password"
            size="large"
            show-password
            @input="clearError"
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <el-alert v-if="errorMsg" :title="errorMsg" type="error" :closable="false" show-icon class="login-error" />
        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="onSubmit">登 录</el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #001529 0%, #1f2d3d 100%);
}
.login-card {
  width: 380px;
  padding: 8px 8px 16px;
}
.login-title {
  text-align: center;
  margin-bottom: 24px;
}
.login-title h2 {
  margin: 0 0 8px;
  font-size: 22px;
}
.login-title p {
  margin: 0;
  color: #909399;
  font-size: 13px;
}
.login-btn {
  width: 100%;
  margin-top: 8px;
}
.login-error {
  margin-bottom: 12px;
}
</style>
