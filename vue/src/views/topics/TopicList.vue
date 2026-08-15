<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { topicApi } from '@/api/modules/topic'
import { mediacrawlerApi } from '@/api/modules/crawler'
import type { Topic } from '@/types'

const router = useRouter()
const topics = ref<Topic[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const nameFilter = ref('')
const statusFilter = ref('')
const loading = ref(false)

const STATUS_LABEL: Record<string, { label: string; type: 'success' | 'info' | 'warning' }> = {
  active: { label: '监测中', type: 'success' },
  paused: { label: '已暂停', type: 'warning' },
  archived: { label: '已归档', type: 'info' },
}

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const res = (await topicApi.list({
      page: page.value,
      page_size: pageSize.value,
      name: nameFilter.value || undefined,
      status: statusFilter.value || undefined,
    })) as { count: number; results: Topic[] }
    topics.value = res.results
    total.value = res.count
  } finally {
    loading.value = false
  }
}

// 静默轮询刷新「爬取中」状态（不显示 loading，避免闪烁）
let pollTimer: number | undefined
function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(() => load(true), 8000)
}
function stopPolling() {
  if (pollTimer) window.clearInterval(pollTimer)
  pollTimer = undefined
}

// 点击「爬取中」状态 → 打开主题详情的采集过程页面
function openCollectPage(topic: Topic) {
  router.push({ path: `/topics/${topic.id}`, query: { mc: '1' } })
}

function search() {
  page.value = 1
  load()
}

function goCreate() {
  router.push('/topics/create')
}
function goDetail(id: number) {
  router.push(`/topics/${id}`)
}
function goEdit(id: number) {
  router.push(`/topics/${id}/edit`)
}

async function toggleStatus(topic: Topic) {
  if (topic.status === 'active') {
    await topicApi.pause(topic.id)
    ElMessage.success('已暂停监测')
  } else {
    await topicApi.resume(topic.id)
    ElMessage.success('已恢复监测')
  }
  load()
}

function hasRealPlatform(topic: Topic) {
  return (topic.platforms || []).some((p) => p === 'xiaohongshu' || p === 'weibo')
}

async function collectNow(topic: Topic) {
  const real = hasRealPlatform(topic)
  const hasMock = (topic.platforms || []).includes('mock')

  // 真实平台（小红书/微博）→ MediaCrawler 命令采集
  if (real) {
    try {
      await mediacrawlerApi.run({ topic_id: topic.id })
      ElMessage.success('已启动 MediaCrawler 采集：本机浏览器将弹出二维码，请扫码登录；完成后数据自动导入')
    } catch {
      return // 错误详情由 axios 拦截器提示（如：已有任务在运行/没有关键词）
    }
  }

  // 模拟数据 → 内置采集器同步执行
  if (hasMock) {
    const res: any = await topicApi.collectNow(topic.id)
    const runs = res?.runs || []
    const failed = runs.filter((r: any) => r.status === 'failed')
    if (failed.length) {
      ElMessage.error('模拟采集失败：' + failed.map((r: any) => `${platformLabel[r.platform] || r.platform}（${r.error_message || '未知错误'}）`).join('；'))
    } else if (!real) {
      ElMessage.success('采集任务已执行')
    }
  }

  // 采集过程页面不再自动弹出：主题状态列会显示「爬取中」，点击该状态可查看过程
}

async function removeTopic(topic: Topic) {
  await ElMessageBox.confirm(`确定删除主题「${topic.name}」吗？该主题采集的帖子将一并删除（其他主题共享的帖子仅解除关联），此操作不可恢复。`, '提示', { type: 'warning' })
  await topicApi.remove(topic.id)
  ElMessage.success('已删除')
  load()
}

const platformLabel: Record<string, string> = { xiaohongshu: '小红书', weibo: '微博', mock: '模拟' }

onMounted(() => {
  load()
  startPolling()
})
onUnmounted(stopPolling)
</script>

<template>
  <el-card shadow="never">
    <div class="toolbar">
      <el-input v-model="nameFilter" placeholder="搜索主题名称" clearable style="width: 220px" @keyup.enter="search" @clear="search" />
      <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 140px" @change="search">
        <el-option label="监测中" value="active" />
        <el-option label="已暂停" value="paused" />
        <el-option label="已归档" value="archived" />
      </el-select>
      <el-button type="primary" @click="search">查询</el-button>
      <div class="spacer" />
      <el-button type="primary" @click="goCreate">新建主题</el-button>
    </div>

    <el-table v-loading="loading" :data="topics" size="small">
      <el-table-column label="ID" prop="id" width="60" />
      <el-table-column label="主题名称" prop="name" min-width="160">
        <template #default="{ row }">
          <span class="link" @click="goDetail(row.id)">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="平台" width="140">
        <template #default="{ row }">
          <el-tag v-for="p in row.platforms" :key="p" size="small" effect="plain" class="mr-4">
            {{ platformLabel[p] || p }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="频率" width="90">
        <template #default="{ row }">{{ row.collection_interval }} 分钟</template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tooltip v-if="row.collecting" content="正在采集，点击查看采集过程" placement="top">
            <el-tag type="danger" size="small" class="link" @click="openCollectPage(row)">爬取中</el-tag>
          </el-tooltip>
          <el-tag v-else :type="STATUS_LABEL[row.status]?.type || 'info'" size="small">
            {{ STATUS_LABEL[row.status]?.label || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="goDetail(row.id)">详情</el-button>
          <el-button link type="primary" size="small" @click="goEdit(row.id)">编辑</el-button>
          <el-button link type="warning" size="small" @click="toggleStatus(row)">
            {{ row.status === 'active' ? '暂停' : '恢复' }}
          </el-button>
          <el-button link type="primary" size="small" @click="collectNow(row)">立即采集</el-button>
          <el-button link type="danger" size="small" @click="removeTopic(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-bar">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @change="load"
      />
    </div>
  </el-card>
</template>

<style scoped>
.toolbar { display: flex; gap: 10px; margin-bottom: 14px; }
.spacer { flex: 1; }
.link { color: #409eff; cursor: pointer; }
.mr-4 { margin-right: 4px; }
.pagination-bar { display: flex; justify-content: flex-end; margin-top: 14px; }
</style>
