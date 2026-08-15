<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { topicApi } from '@/api/modules/topic'
import { postApi } from '@/api/modules/post'
import { taskApi } from '@/api/modules/task'
import { mediacrawlerApi, type MediaCrawlerStatus } from '@/api/modules/crawler'
import PieDonut from '@/components/charts/PieDonut.vue'
import SentimentTag from '@/components/posts/SentimentTag.vue'
import type { Post } from '@/types'

const route = useRoute()
const router = useRouter()
const topicId = Number(route.params.id)

const topic = ref<any>(null)
const stats = ref<any>({})
const posts = ref<Post[]>([])
const runs = ref<any[]>([])
const activeTab = ref('overview')

const platformLabel: Record<string, string> = { xiaohongshu: '小红书', weibo: '微博', mock: '模拟' }

async function loadTopic() {
  topic.value = await topicApi.detail(topicId)
  if (topic.value) stats.value = await topicApi.stats(topicId)
}

async function loadPosts() {
  const res = (await postApi.list({ topic: topicId, page_size: 10, ordering: '-heat_score' })) as { results: Post[] }
  posts.value = res.results
}

async function loadRuns() {
  const res: any = await taskApi.runs({ topic: topicId, page_size: 10 })
  runs.value = res.results || []
}

async function handleTab(tab: string) {
  if (tab === 'posts') loadPosts()
  if (tab === 'runs') loadRuns()
}

async function collectNow() {
  const platforms = topic.value?.platforms || []
  const real = platforms.some((p: string) => p === 'xiaohongshu' || p === 'weibo')
  const hasMock = platforms.includes('mock')

  if (real) {
    // 真实平台 → MediaCrawler（后台执行，采集过程页面不自动弹出；
    // 主题状态会显示「爬取中」，点击状态可打开过程页面查看；结束后自动导入数据）
    try {
      await mediacrawlerApi.run({ topic_id: topicId })
      ElMessage.success('已启动采集：本机浏览器将弹出二维码，请扫码登录；结束后数据自动导入')
    } catch {
      return // 错误详情由 axios 拦截器提示
    }
  }
  if (hasMock) {
    const res: any = await topicApi.collectNow(topicId)
    const runs = res?.runs || []
    const failed = runs.filter((r: any) => r.status === 'failed')
    if (failed.length) {
      ElMessage.error('模拟采集失败：' + failed.map((r: any) => `${platformLabel[r.platform] || r.platform}(${r.error_message || '未知错误'})`).join('；'))
    } else if (!real) {
      ElMessage.success('采集已执行')
    }
  }
  loadTopic()
  loadRuns()
}

// ---------- MediaCrawler 真实采集（外部爬虫命令，由「立即采集」触发） ----------
const mcDialogVisible = ref(false)
const mcStatus = ref<MediaCrawlerStatus | null>(null)
const mcStarting = ref(false)
const mcImporting = ref(false)
let mcPollTimer: number | undefined

async function pollMcStatus() {
  try {
    mcStatus.value = await mediacrawlerApi.status(topicId)
    if (mcStatus.value?.running && mcDialogVisible.value) {
      mcPollTimer = window.setTimeout(pollMcStatus, 2000)
    }
  } catch {
    /* 接口异常时停止轮询 */
  }
}

function openMediaCrawler() {
  mcDialogVisible.value = true
  mcStatus.value = null
  pollMcStatus()
}

function closeMediaCrawler() {
  mcDialogVisible.value = false
  if (mcPollTimer) window.clearTimeout(mcPollTimer)
}

async function startMediaCrawler() {
  mcStarting.value = true
  try {
    await mediacrawlerApi.run({ topic_id: topicId, platform: 'xhs' })
    pollMcStatus()
  } finally {
    mcStarting.value = false
  }
}

async function stopMediaCrawler() {
  await mediacrawlerApi.stop()
  pollMcStatus()
}

async function importMediaData() {
  mcImporting.value = true
  try {
    await mediacrawlerApi.importData(topicId)
    ElMessage.success('导入完成')
    pollMcStatus()
    loadTopic()
    loadPosts()
  } finally {
    mcImporting.value = false
  }
}

const mcStatusType: Record<string, string> = { running: 'warning', queued: 'info', finished: 'success', importing: 'warning', failed: 'danger', stopped: 'info' }
const mcStatusTagType = computed(() => (mcStatus.value?.run ? mcStatusType[mcStatus.value.run.status] || 'info' : 'info'))

const runStatusLabel: Record<string, string> = { pending: '待执行', running: '执行中', success: '成功', failed: '失败', canceled: '已取消' }

onMounted(() => {
  loadTopic()
  loadRuns()
  handleTab('posts')
  // 从列表页「立即采集」跳转过来时自动打开采集对话框
  if (route.query.mc === '1') openMediaCrawler()
})
</script>

<template>
  <div v-if="topic">
    <el-card shadow="never">
      <div class="topic-header">
        <div>
          <h2>{{ topic.name }}</h2>
          <div class="topic-meta">
            <el-tag v-for="p in topic.platforms" :key="p" size="small" effect="plain">{{ platformLabel[p] }}</el-tag>
            <span>频率：{{ topic.collection_interval }} 分钟</span>
            <el-tag v-if="topic.collecting" type="danger" size="small" class="link" @click="openMediaCrawler">爬取中（点击查看过程）</el-tag>
            <el-tag :type="topic.status === 'active' ? 'success' : 'warning'" size="small">
              {{ topic.status === 'active' ? '监测中' : '已暂停' }}
            </el-tag>
          </div>
        </div>
        <div>
          <el-button type="primary" @click="collectNow">立即采集</el-button>
          <el-button @click="router.push(`/topics/${topicId}/edit`)">编辑</el-button>
        </div>
      </div>
      <p v-if="topic.description" class="topic-desc">{{ topic.description }}</p>
    </el-card>

    <el-tabs v-model="activeTab" class="topic-tabs" @tab-change="handleTab">
      <el-tab-pane label="概览" name="overview">
        <el-row :gutter="12">
          <el-col :span="6">
            <el-card shadow="never" class="stat-box">
              <div class="stat-num">{{ stats.post_count ?? 0 }}</div>
              <div class="stat-label">帖子总量</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never" class="stat-box">
              <div class="stat-num">{{ stats.new_today ?? 0 }}</div>
              <div class="stat-label">今日新增</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never" class="stat-box">
              <div class="stat-num negative">{{ stats.negative_count ?? 0 }}</div>
              <div class="stat-label">负面帖数</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="never" class="stat-box">
              <div class="stat-num">{{ stats.alert_count ?? 0 }}</div>
              <div class="stat-label">待处理预警</div>
            </el-card>
          </el-col>
        </el-row>
        <el-row :gutter="12" style="margin-top: 12px">
          <el-col :span="8">
            <el-card shadow="never" header="情感占比">
              <PieDonut :data="stats.sentiment_distribution || {}" />
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never" header="平台分布">
              <PieDonut :data="stats.platform_distribution || {}" />
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="never" header="最近运行">
              <el-table :data="runs" size="small" max-height="260">
                <el-table-column label="平台" prop="platform" width="70" />
                <el-table-column label="状态" width="70">
                  <template #default="{ row }">{{ runStatusLabel[row.status] }}</template>
                </el-table-column>
                <el-table-column label="新增" prop="new_count" width="60" />
                <el-table-column label="时间" width="120">
                  <template #default="{ row }">{{ row.created_at ? dayjs(row.created_at).format('YYYY-MM-DD HH:mm') : '-' }}</template>
                </el-table-column>
              </el-table>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <el-tab-pane label="帖子" name="posts">
        <el-table :data="posts" size="small" @row-click="(r: any) => router.push(`/posts/${r.id}`)">
          <el-table-column label="内容" prop="content" show-overflow-tooltip />
          <el-table-column label="作者" prop="author_name" width="100" />
          <el-table-column label="情感" width="80">
            <template #default="{ row }"><SentimentTag :sentiment="row.sentiment" /></template>
          </el-table-column>
          <el-table-column label="点赞" prop="like_count" width="80" />
          <el-table-column label="热度" prop="heat_score" width="80" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="运行记录" name="runs">
        <el-table :data="runs" size="small">
          <el-table-column label="ID" prop="id" width="60" />
          <el-table-column label="平台" prop="platform" width="90" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'info'" size="small">
                {{ runStatusLabel[row.status] }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="触发" prop="trigger_type" width="80" />
          <el-table-column label="采集/新增/重复" width="140">
            <template #default="{ row }">{{ row.fetched_count }}/{{ row.new_count }}/{{ row.duplicate_count }}</template>
          </el-table-column>
          <el-table-column label="重试" prop="retry_count" width="60" />
          <el-table-column label="错误" prop="error_message" show-overflow-tooltip />
          <el-table-column label="时间" width="150">
            <template #default="{ row }">{{ row.created_at ? dayjs(row.created_at).format('YYYY-MM-DD HH:mm:ss') : '-' }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      
    </el-tabs>

    <!-- MediaCrawler 采集对话框 -->
    <el-dialog v-model="mcDialogVisible" title="MediaCrawler 采集（小红书/微博）" width="760px" @close="closeMediaCrawler">
      <div class="mc-panel">
        <el-alert type="info" :closable="false" title="点击「开始采集」后，本机将弹出浏览器窗口并显示小红书登录二维码，请用小红书 App 扫码；扫码后自动按本主题关键词搜索并抓取帖子和评论。" class="mc-tip" />
        <div class="mc-actions">
          <el-button type="primary" :loading="mcStarting" :disabled="mcStatus?.running" @click="startMediaCrawler">开始采集（uv run main.py）</el-button>
          <el-button :disabled="!mcStatus?.running" @click="stopMediaCrawler">停止</el-button>
          <el-button :loading="mcImporting" @click="importMediaData">仅导入已有数据</el-button>
        </div>
        <div v-if="mcStatus?.run" class="mc-status">
          <el-tag :type="mcStatusTagType" size="small">{{ mcStatus.run.status_label }}</el-tag>
          <span class="mc-kw">关键词：{{ mcStatus.run.keywords }}</span>
          <span v-if="mcStatus.run.fetched_count || mcStatus.run.new_count || mcStatus.run.comment_count" class="mc-counts">抓取 {{ mcStatus.run.fetched_count }} / 新增 {{ mcStatus.run.new_count }} / 重复 {{ mcStatus.run.duplicate_count }} / 评论 {{ mcStatus.run.comment_count }}</span>
          <span v-if="mcStatus.run.error_message" class="mc-error">{{ mcStatus.run.error_message }}</span>
        </div>
        <div class="mc-log-title">运行日志（含扫码提示）：</div>
        <pre class="mc-log">{{ mcStatus?.log_tail || '（暂无日志，点击开始采集后这里会显示 MediaCrawler 输出）' }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.topic-header { display: flex; justify-content: space-between; align-items: flex-start; }
.topic-header h2 { margin: 0 0 8px; }
.topic-meta { display: flex; gap: 10px; align-items: center; color: #909399; font-size: 13px; }
.topic-desc { color: #606266; margin-top: 10px; }
.topic-tabs { margin-top: 12px; }
.link { cursor: pointer; }
.stat-box { text-align: center; padding: 10px 0; }
.stat-num { font-size: 28px; font-weight: 700; }
.stat-num.negative { color: #f56c6c; }
.stat-label { color: #909399; font-size: 13px; }
.mc-tip { margin-bottom: 12px; }
.mc-actions { display: flex; gap: 10px; margin-bottom: 12px; }
.mc-status { display: flex; gap: 12px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.mc-kw { color: #606266; font-size: 12px; }
.mc-counts { color: #67c23a; font-size: 12px; }
.mc-error { color: #f56c6c; font-size: 12px; }
.mc-log-title { color: #909399; font-size: 12px; margin-bottom: 4px; }
.mc-log { background: #1f2d3d; color: #b3b8c2; padding: 10px; border-radius: 6px; max-height: 320px; overflow-y: auto; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; margin: 0; }
</style>
