<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { taskApi } from '@/api/modules/task'
import http from '@/api'
import dayjs from 'dayjs'

interface CollectorStatus {
  platform: string
  display_name: string
  enabled: boolean
  issues: string[]
}

interface ActiveJob {
  id: string
  trigger: string
  next_run_time: string | null
}

interface SchedulerStatus {
  scheduler_running: boolean
  dispatch_running: boolean
  active_jobs: ActiveJob[]
}

interface HealthInfo {
  status: string
  version: string
  env: string
  timezone: string
  scheduler_running: boolean
}

const scheduler = ref<SchedulerStatus | null>(null)
const collectors = ref<CollectorStatus[]>([])
const health = ref<HealthInfo | null>(null)
const loading = ref(false)

async function loadAll() {
  loading.value = true
  try {
    const [s, c, h] = await Promise.all([
      taskApi.status(),
      http.get<CollectorStatus[]>('/collectors/'),
      http.get<HealthInfo>('/health/'),
    ])
    scheduler.value = s as SchedulerStatus
    collectors.value = c
    health.value = h
  } finally {
    loading.value = false
  }
}

function fmtNext(t: string | null) {
  return t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '待调度'
}

onMounted(loadAll)
</script>

<template>
  <div class="settings" v-loading="loading">
    <el-row :gutter="16">
      <!-- 系统信息 -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>系统信息</template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="状态">{{ health?.status === 'ok' ? '正常' : health?.status }}</el-descriptions-item>
            <el-descriptions-item label="版本">{{ health?.version }}</el-descriptions-item>
            <el-descriptions-item label="环境">{{ health?.env }}</el-descriptions-item>
            <el-descriptions-item label="时区">{{ health?.timezone }}</el-descriptions-item>
            <el-descriptions-item label="调度器">{{ health?.scheduler_running ? '运行中' : '已停止' }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <!-- 采集器状态 -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>采集器状态</template>
          <el-table :data="collectors" size="small">
            <el-table-column prop="display_name" label="采集器" width="120" />
            <el-table-column prop="platform" label="平台标识" width="120" />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? 'success' : 'info'" size="small">{{ row.enabled ? '已启用' : '未启用' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="配置问题" min-width="120">
              <template #default="{ row }">
                <span v-if="row.issues?.length" class="issue-text">{{ row.issues.join('；') }}</span>
                <span v-else class="ok-text">无</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- 调度任务 -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>调度任务（{{ scheduler?.active_jobs?.length || 0 }}）</template>
          <el-table :data="scheduler?.active_jobs || []" size="small" max-height="320">
            <el-table-column prop="id" label="任务 ID" width="150" />
            <el-table-column prop="trigger" label="触发器" min-width="130" show-overflow-tooltip />
            <el-table-column label="下次执行" min-width="140">
              <template #default="{ row }">{{ fmtNext(row.next_run_time) }}</template>
            </el-table-column>
          </el-table>
          <el-button style="margin-top: 12px" size="small" @click="loadAll">刷新</el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.ok-text {
  color: #67c23a;
  font-size: 12px;
}
.issue-text {
  color: #f56c6c;
  font-size: 12px;
}
</style>
