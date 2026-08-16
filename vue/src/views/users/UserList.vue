<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import { authApi } from '@/api/modules/auth'
import { useAuthStore } from '@/stores/auth'
import type { UserInfo, UserRole } from '@/types'

const auth = useAuthStore()
const users = ref<UserInfo[]>([])
const total = ref(0)
const loading = ref(false)
const page = reactive({ current: 1, size: 20 })

async function loadUsers() {
  loading.value = true
  try {
    const data = await authApi.users({ page: page.current, page_size: page.size })
    users.value = data.results
    total.value = data.count
  } finally {
    loading.value = false
  }
}

// ---------- 新建用户 ----------
const createVisible = ref(false)
const createForm = reactive({ username: '', name: '', password: '', role: 'operator' as UserRole })
const creating = ref(false)

function openCreate() {
  createForm.username = ''
  createForm.name = ''
  createForm.password = ''
  createForm.role = 'operator'
  createVisible.value = true
}

async function submitCreate() {
  if (!createForm.username || !createForm.password) {
    ElMessage.warning('用户名和密码必填')
    return
  }
  creating.value = true
  try {
    await authApi.createUser(createForm)
    ElMessage.success('用户已创建')
    createVisible.value = false
    loadUsers()
  } finally {
    creating.value = false
  }
}

// ---------- 编辑用户 ----------
const editVisible = ref(false)
const editForm = reactive({ id: 0, name: '', role: 'operator' as UserRole, is_active: true })

function openEdit(row: UserInfo) {
  editForm.id = row.id
  editForm.name = row.name || ''
  editForm.role = row.role
  editForm.is_active = row.is_active
  editVisible.value = true
}

async function submitEdit() {
  await authApi.updateUser(editForm.id, { name: editForm.name, role: editForm.role, is_active: editForm.is_active })
  ElMessage.success('已更新')
  editVisible.value = false
  loadUsers()
}

// ---------- 重置密码 ----------
const pwdVisible = ref(false)
const pwdForm = reactive({ id: 0, username: '', password: '' })

function openReset(row: UserInfo) {
  pwdForm.id = row.id
  pwdForm.username = row.username
  pwdForm.password = ''
  pwdVisible.value = true
}

async function submitReset() {
  if (pwdForm.password.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  await authApi.resetPassword(pwdForm.id, pwdForm.password)
  ElMessage.success('密码已重置')
  pwdVisible.value = false
}

// ---------- 停用 ----------
async function deactivate(row: UserInfo) {
  if (row.id === auth.user?.id) {
    ElMessage.warning('不能停用当前登录账号')
    return
  }
  try {
    await ElMessageBox.confirm(`确定停用用户「${row.username}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  await authApi.deactivateUser(row.id)
  ElMessage.success('已停用')
  loadUsers()
}

function fmtTime(s: string) {
  return dayjs(s).format('YYYY-MM-DD HH:mm')
}

onMounted(loadUsers)
</script>

<template>
  <div class="user-list">
    <el-card shadow="never">
      <div class="toolbar">
        <el-button type="primary" @click="openCreate">新建用户</el-button>
        <el-button @click="loadUsers">刷新</el-button>
      </div>

      <el-table :data="users" v-loading="loading" style="width: 100%">
        <el-table-column prop="username" label="用户名" min-width="180" />
        <el-table-column label="姓名" min-width="160">
          <template #default="{ row }">{{ row.name || '-' }}</template>
        </el-table-column>
        <el-table-column label="角色" min-width="110">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'success'" size="small">
              {{ row.role === 'admin' ? '管理员' : '运营' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="160">
          <template #default="{ row }">{{ fmtTime(row.date_joined) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="warning" size="small" @click="openReset(row)">重置密码</el-button>
            <el-button link type="danger" size="small" :disabled="row.id === auth.user?.id" @click="deactivate(row)">停用</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page.current"
        :page-size="page.size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadUsers"
      />
    </el-card>

    <!-- 新建用户 -->
    <el-dialog v-model="createVisible" title="新建用户" width="460px">
      <el-form :model="createForm" label-width="70px">
        <el-form-item label="用户名" required>
          <el-input v-model="createForm.username" placeholder="登录账号" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="createForm.name" placeholder="显示名称" />
        </el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="createForm.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="createForm.role">
            <el-radio value="operator">运营</el-radio>
            <el-radio value="admin">管理员</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑用户 -->
    <el-dialog v-model="editVisible" title="编辑用户" width="460px">
      <el-form :model="editForm" label-width="70px">
        <el-form-item label="姓名">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="editForm.role">
            <el-radio value="operator">运营</el-radio>
            <el-radio value="admin">管理员</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="editForm.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码 -->
    <el-dialog v-model="pwdVisible" :title="`重置密码 - ${pwdForm.username}`" width="460px">
      <el-form label-width="70px">
        <el-form-item label="新密码" required>
          <el-input v-model="pwdForm.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" @click="submitReset">重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
</style>
