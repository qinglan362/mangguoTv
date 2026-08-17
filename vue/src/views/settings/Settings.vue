<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import dayjs from 'dayjs'
import { taskApi, type SchedulerJob } from '@/api/modules/task'

interface SchedulerStatus {
  scheduler_running: boolean
  dispatch_running: boolean
  active_jobs: SchedulerJob[]
  pending_queue: number
  running_count: number
  recent_failed: { id: number; topic_id: number; platform: string; error_message: string }[]
}

const scheduler = ref<SchedulerStatus | null>(null)
const loading = ref(false)

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    scheduler.value = (await taskApi.status()) as SchedulerStatus
  } finally {
    loading.value = false
  }
}

// 静默轮询刷新调度任务状态（不闪烁 loading）
let pollTimer: number | undefined
function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(() => load(true), 8000)
}
function stopPolling() {
  if (pollTimer) window.clearInterval(pollTimer)
  pollTimer = undefined
}

function fmtTime(t: string | null | undefined) {
  return t ? dayjs(t).format('YYYY-MM-DD HH:mm:ss') : '待调度'
}

function fmtTrigger(job: SchedulerJob) {
  if (job.interval_minutes) return '每 ' + job.interval_minutes + ' 分钟'
  const m = job.trigger?.match(/^cron\[(.*)\]$/)
  if (m && m[1] !== undefined) {
    const fields: Record<string, string> = {}
    for (const part of m[1].split(',')) {
      const eq = part.indexOf('=')
      if (eq > 0) fields[part.slice(0, eq).trim()] = part.slice(eq + 1).trim().replace(/^'|'$/g, '')
    }
    // 存在具体的日期/月份表达式时不臆测，保持原样
    if ((fields.day && fields.day !== '*') || (fields.month && fields.month !== '*')) return job.trigger
    const time = (fields.hour ?? '0').padStart(2, '0') + ':' + (fields.minute ?? '0').padStart(2, '0')
    const DOW: Record<string, string> = { mon: '一', tue: '二', wed: '三', thu: '四', fri: '五', sat: '六', sun: '日' }
    const dow = fields.day_of_week ?? ''
    if (dow && dow !== '*') {
      const days = dow.split(',').map((d) => DOW[d.trim()] || d.trim()).filter(Boolean)
      if (days.length) return '每周' + days.join('、') + ' ' + time
    }
    return '每天 ' + time
  }
  return job.trigger
}

const KIND_TAG: Record<string, string> = { topic: 'primary', report: 'success', reconcile: 'info', retry: 'warning', snapshot: 'success', alert: 'danger' }
const RUN_STATUS_LABEL: Record<string, string> = { pending: '待执行', running: '执行中', success: '成功', failed: '失败', canceled: '已取消' }

function runStatusType(status: string) {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}

onMounted(() => {
  load()
  startPolling()
})
onUnmounted(stopPolling)
</script>

<template>
  <div class="settings" v-loading="loading">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>调度任务（{{ scheduler?.active_jobs?.length || 0 }}）</span>
          <div class="header-right">
            <el-tag :type="scheduler?.scheduler_running ? 'success' : 'danger'" size="small">
              调度器：{{ scheduler?.scheduler_running ? '运行中' : '已停止' }}
            </el-tag>
            <el-tag :type="scheduler?.dispatch_running ? 'success' : 'danger'" size="small">
              派发线程：{{ scheduler?.dispatch_running ? '运行中' : '已停止' }}
            </el-tag>
            <el-button size="small" @click="load()">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="scheduler?.active_jobs || []" size="small">
        <el-table-column label="任务名称" min-width="220">
          <template #default="{ row }">
            <el-tag :type="KIND_TAG[row.kind] || 'info'" size="small" effect="plain">{{ row.name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关联主题" width="150">
          <template #default="{ row }">
            <span v-if="row.topic_name">{{ row.topic_name }}</span>
            <span v-else class="dim">-</span>
          </template>
        </el-table-column>
        <el-table-column label="触发器" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ fmtTrigger(row) }}</template>
        </el-table-column>
        <el-table-column label="上次执行" width="230">
          <template #default="{ row }">
            <span v-if="row.last_run_at" class="time-text">{{ fmtTime(row.last_run_at) }}</span>
            <span v-else class="dim">-</span>
            <el-tag v-if="row.last_run_status" size="small" :type="runStatusType(row.last_run_status)" class="ml-4">
              {{ RUN_STATUS_LABEL[row.last_run_status] || row.last_run_status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="下次执行" width="170">
          <template #default="{ row }">
            <span class="time-text">{{ fmtTime(row.next_run_time) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <el-alert
        v-if="scheduler && !scheduler.scheduler_running"
        type="warning"
        :closable="false"
        show-icon
        title="调度器未运行：定时采集与报告任务不会触发。开发环境默认随 runserver 自动启动；若单独关闭了内联调度器，请运行 python manage.py runscheduler。"
        class="mt-12"
      />
    </el-card>

    <el-card v-if="scheduler?.recent_failed?.length" shadow="never" class="mt-12">
      <template #header>最近失败（{{ scheduler.recent_failed.length }}）</template>
      <el-table :data="scheduler.recent_failed" size="small">
        <el-table-column label="运行 ID" prop="id" width="90" />
        <el-table-column label="主题 ID" prop="topic_id" width="90" />
        <el-table-column label="平台" prop="platform" width="100" />
        <el-table-column label="错误信息" prop="error_message" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.header-right { display: flex; gap: 8px; align-items: center; }
.ml-4 { margin-left: 4px; }
.mt-12 { margin-top: 12px; }
.time-text { font-size: 12px; color: #606266; }
.dim { color: #c0c4cc; }
</style>
