<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { reportApi, type DataExportRecord, type ReportRecord } from '@/api/modules/report'
import { topicApi } from '@/api/modules/topic'
import { tokenStorage } from '@/utils/token'
import type { Topic } from '@/types'

const activeTab = ref<'reports' | 'exports'>('reports')

// ---------- 报告 ----------
const topics = ref<Topic[]>([])
const reports = ref<ReportRecord[]>([])
const reportsTotal = ref(0)
const reportFilter = reactive({
  topic: undefined as number | undefined,
  period_type: '' as string,
  page: 1,
  pageSize: 15,
})
const reportDetail = ref<ReportRecord | null>(null)
const detailVisible = ref(false)
const generating = ref(false)

async function loadReports() {
  const params: Record<string, unknown> = { page: reportFilter.page, page_size: reportFilter.pageSize }
  if (reportFilter.topic) params.topic = reportFilter.topic
  if (reportFilter.period_type) params.period_type = reportFilter.period_type
  const data = await reportApi.reports(params)
  reports.value = data.results
  reportsTotal.value = data.count
}

async function generateReport(periodType: 'daily' | 'weekly') {
  if (!reportFilter.topic) {
    ElMessage.warning('请先选择一个主题')
    return
  }
  generating.value = true
  try {
    await reportApi.generate({ topic: reportFilter.topic, period_type: periodType })
    ElMessage.success(periodType === 'daily' ? '日报已生成' : '周报已生成')
    loadReports()
  } finally {
    generating.value = false
  }
}

function showDetail(row: ReportRecord) {
  reportDetail.value = row
  detailVisible.value = true
}

// ---------- 导出任务 ----------
const exportsList = ref<DataExportRecord[]>([])
const exportsTotal = ref(0)
const exportFilter = reactive({
  topic: undefined as number | undefined,
  sentiment: '' as string,
  exportType: 'post' as 'post' | 'full',
  page: 1,
  pageSize: 15,
})
const exporting = ref(false)

async function loadExports() {
  const data = await reportApi.exports({ page: exportFilter.page, page_size: exportFilter.pageSize })
  exportsList.value = data.results
  exportsTotal.value = data.count
}

async function createExport() {
  exporting.value = true
  try {
    const filters: Record<string, unknown> = {}
    if (exportFilter.topic) {
      const t = topics.value.find((x) => x.id === exportFilter.topic)
      filters.topic_ids = [exportFilter.topic]
      filters.topic_names = t?.name || ''
    }
    if (exportFilter.sentiment) filters.sentiment = exportFilter.sentiment
    await reportApi.createExport({ export_type: exportFilter.exportType, filters })
    ElMessage.success('导出完成，可在下方任务中下载')
    loadExports()
  } finally {
    exporting.value = false
  }
}

const exportingRow = ref<number | null>(null)

async function exportReport(row: ReportRecord) {
  exportingRow.value = row.id
  try {
    const base = dayjs(row.report_date)
    const start = row.period_type === 'weekly' ? base.subtract(6, 'day') : base
    const filters: Record<string, unknown> = {
      topic_ids: [row.topic],
      topic_names: row.topic_name || '',
      start: start.format('YYYY-MM-DDT00:00:00'),
      end: base.add(1, 'day').format('YYYY-MM-DDT00:00:00'),
      period_type: row.period_type,
      report_date: row.report_date,
    }
    const record = await reportApi.createExport({ export_type: 'full', filters })
    if (record.status === 'done') {
      downloadExport(record)
    } else {
      ElMessage.warning('导出任务已创建，可在「数据导出」页下载')
    }
    loadExports()
  } finally {
    exportingRow.value = null
  }
}

async function downloadExport(row: DataExportRecord) {
  if (!row.download_url) {
    ElMessage.warning('文件未生成')
    return
  }
  // window.open 新标签页不会带 Authorization 头，JWT 鉴权下必然 401（H14）：
  // 改用 fetch + blob 携带 token 下载。
  try {
    const token = tokenStorage.getAccess()
    const resp = await fetch(reportApi.downloadUrl(row.id), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!resp.ok) {
      ElMessage.error('下载失败，请重新登录后重试')
      return
    }
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    // 用服务端生成的真实文件名（报告导出为「主题+日报/周报+日期」）
    const baseName = (row.file_path || '').split(/[\\/]/).pop()
    a.download = baseName || `export_${row.id}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('下载失败')
  }
}

// ---------- 工具 ----------
function fmtTime(s: string | null) {
  return s ? dayjs(s).format('YYYY-MM-DD HH:mm') : '-'
}

const STATUS_MAP: Record<string, { label: string; type: 'success' | 'info' | 'danger' | 'warning' }> = {
  done: { label: '完成', type: 'success' },
  generating: { label: '生成中', type: 'warning' },
  failed: { label: '失败', type: 'danger' },
  pending: { label: '待处理', type: 'info' },
  running: { label: '处理中', type: 'warning' },
}

onMounted(async () => {
  const topicData = await topicApi.list({ page_size: 100 })
  topics.value = topicData.results
  loadReports()
  loadExports()
})
</script>

<template>
  <div class="report-list">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="舆情报告" name="reports">
        <el-card shadow="never">
          <div class="filter-bar">
            <el-select v-model="reportFilter.topic" placeholder="选择主题" clearable style="width: 200px" @change="reportFilter.page = 1; loadReports()">
              <el-option v-for="t in topics" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
            <el-select v-model="reportFilter.period_type" placeholder="报告类型" clearable style="width: 120px" @change="reportFilter.page = 1; loadReports()">
              <el-option label="日报" value="daily" />
              <el-option label="周报" value="weekly" />
            </el-select>
            <el-button type="primary" :loading="generating" :disabled="!reportFilter.topic" @click="generateReport('daily')">生成日报</el-button>
            <el-button type="success" :loading="generating" :disabled="!reportFilter.topic" @click="generateReport('weekly')">生成周报</el-button>
            <el-button @click="reportFilter.page = 1; loadReports()">刷新</el-button>
          </div>

          <el-table :data="reports" style="width: 100%">
            <el-table-column prop="title" label="报告标题" min-width="200" />
            <el-table-column prop="topic_name" label="主题" min-width="120" />
            <el-table-column label="类型" min-width="70">
              <template #default="{ row }">{{ row.period_type === 'daily' ? '日报' : '周报' }}</template>
            </el-table-column>
            <el-table-column prop="report_date" label="报告日期" min-width="110" />
            <el-table-column label="状态" min-width="80">
              <template #default="{ row }">
                <el-tag :type="STATUS_MAP[row.status]?.type || 'info'" size="small">{{ STATUS_MAP[row.status]?.label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="生成时间" min-width="140">
              <template #default="{ row }">{{ fmtTime(row.generated_at || row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="导出报告" min-width="90">
              <template #default="{ row }">
                <el-button v-if="row.status === 'done'" link type="success" size="small" :loading="exportingRow === row.id" @click="exportReport(row)">导出</el-button>
              </template>
            </el-table-column>
            <el-table-column label="操作" min-width="80" fixed="right">
              <template #default="{ row }">
                <el-button v-if="row.status === 'done'" link type="primary" size="small" @click="showDetail(row)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="reportFilter.page"
            :page-size="reportFilter.pageSize"
            :total="reportsTotal"
            layout="total, prev, pager, next"
            @current-change="loadReports"
          />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="数据导出" name="exports">
        <el-card shadow="never">
          <div class="filter-bar">
            <el-select v-model="exportFilter.topic" placeholder="全部主题" clearable style="width: 200px">
              <el-option v-for="t in topics" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
            <el-select v-model="exportFilter.sentiment" placeholder="情感" clearable style="width: 120px">
              <el-option label="全部" value="" />
              <el-option label="正面" value="positive" />
              <el-option label="中性" value="neutral" />
              <el-option label="负面" value="negative" />
            </el-select>
            <el-radio-group v-model="exportFilter.exportType">
              <el-radio value="post">帖子数据</el-radio>
              <el-radio value="full">全量数据</el-radio>
            </el-radio-group>
            <el-button type="primary" :loading="exporting" @click="createExport">导出</el-button>
          </div>

          <el-table :data="exportsList" style="width: 100%">
            <el-table-column label="类型" width="100">
              <template #default="{ row }">{{ row.export_type === 'full' ? '全量数据' : '帖子数据' }}</template>
            </el-table-column>
            <el-table-column label="筛选" min-width="180">
              <template #default="{ row }">
                {{ JSON.stringify(row.filters || {}) }}
              </template>
            </el-table-column>
            <el-table-column prop="row_count" label="行数" width="90" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="STATUS_MAP[row.status]?.type || 'info'" size="small">{{ STATUS_MAP[row.status]?.label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" width="130">
              <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90" fixed="right">
              <template #default="{ row }">
                <el-button v-if="row.status === 'done'" link type="primary" size="small" @click="downloadExport(row)">下载</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="exportFilter.page"
            :page-size="exportFilter.pageSize"
            :total="exportsTotal"
            layout="total, prev, pager, next"
            @current-change="loadExports"
          />
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 报告摘要 -->
    <el-dialog v-model="detailVisible" :title="reportDetail?.title" width="620px">
      <template v-if="reportDetail">
        <pre class="report-summary">{{ reportDetail.summary }}</pre>
        <el-divider />
        <div class="stat-grid">
          <div class="stat-item" v-for="(v, k) in reportDetail.statistics" :key="k">
            <span class="stat-key">{{ k }}</span>
            <span class="stat-val">{{ typeof v === 'object' ? JSON.stringify(v) : v }}</span>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
  align-items: center;
}
.report-summary {
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.7;
  color: #303133;
  margin: 0;
}
.stat-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
  max-height: 300px;
  overflow-y: auto;
}
.stat-item {
  display: flex;
  gap: 8px;
  font-size: 12px;
}
.stat-key {
  color: #909399;
  flex-shrink: 0;
}
.stat-val {
  color: #303133;
  word-break: break-all;
}
</style>
