<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { dashboardApi } from '@/api/modules/dashboard'
import { useFilters } from '@/composables/useFilters'
import AreaTrend from '@/components/charts/AreaTrend.vue'
import WordCloud from '@/components/charts/WordCloud.vue'
import BaseChart from '@/components/charts/BaseChart.vue'
import SentimentTag from '@/components/posts/SentimentTag.vue'

const router = useRouter()
const { topics, topicId, platform, dateRange, queryParams } = useFilters()
// 看板不再支持按时间筛选：清空时间范围，统计接口按全量数据查询
dateRange.value = null

const overview = ref<Record<string, unknown>>({})
const interaction = ref<any[]>([])
const hotPosts = ref<any[]>([])
const negativePosts = ref<any[]>([])
const keywords = ref<{ keyword: string; count: number }[]>([])
const keywordsLoading = ref(false)
const heatTrend = ref<{ time: string; heat: number }[]>([])
const loading = ref(false)

async function loadAll() {
  loading.value = true
  try {
    const p = queryParams()
    const [o, it, hp, np, ht] = await Promise.all([
      dashboardApi.overview(p),
      dashboardApi.interactionTrend({ ...p, bucket: 'hour' }),
      dashboardApi.hotPosts({ ...p, limit: 8 }),
      dashboardApi.negativePosts({ ...p, limit: 8 }),
      dashboardApi.heatTrend(p),
    ])
    overview.value = o as Record<string, unknown>
    interaction.value = it as any[]
    hotPosts.value = hp as any[]
    negativePosts.value = np as any[]
    heatTrend.value = ht as { time: string; heat: number }[]
  } finally {
    loading.value = false
  }
}

// 高频关键词由 LLM 精选，耗时可达数十秒：单独请求、单独 loading，
// 不阻塞其他板块渲染；请求序号防止快速切换筛选时旧响应覆盖新响应
let keywordsReqId = 0
async function loadKeywords() {
  const id = ++keywordsReqId
  keywordsLoading.value = true
  try {
    // 关键词固定用最近 7 天窗口：后端直接读预计算快照，秒回
    const kw = await dashboardApi.topKeywords({ ...queryParams(), window: '7d' })
    if (id === keywordsReqId) keywords.value = kw as { keyword: string; count: number }[]
  } catch {
    if (id === keywordsReqId) keywords.value = []
  } finally {
    if (id === keywordsReqId) keywordsLoading.value = false
  }
}

function loadPage() {
  loadAll()
  loadKeywords()
}

watch([topicId, platform], loadPage)
onMounted(loadPage)

function goPost(id: number) {
  router.push(`/posts/${id}`)
}

const heatTrendOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 50, right: 20, top: 30, bottom: 30 },
  xAxis: { type: 'category', data: heatTrend.value.map((d) => dayjs(d.time).format('YYYY-MM-DD HH:mm')) },
  yAxis: { type: 'value' },
  series: [
    {
      name: '舆情热度',
      type: 'line',
      smooth: true,
      data: heatTrend.value.map((d) => d.heat),
      areaStyle: { opacity: 0.2 },
    },
  ],
  dataZoom: [{ type: 'inside' }],
}))
</script>

<template>
  <div v-loading="loading">
    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-bar">
        <el-select v-model="topicId" placeholder="全部主题" clearable style="width: 200px">
          <el-option v-for="t in topics" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
        <el-select v-model="platform" placeholder="全部平台" clearable style="width: 140px">
          <el-option label="小红书" value="xiaohongshu" />
          <el-option label="微博" value="weibo" />
          <el-option label="模拟" value="mock" />
        </el-select>
        <el-button type="primary" @click="loadPage">刷新</el-button>
      </div>
    </el-card>

    <!-- 概览卡片 -->
    <el-row :gutter="12" class="cards-row">
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-card">
            <div class="stat-label">帖子数量</div>
            <div class="stat-value">{{ overview.post_count ?? '-' }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-card">
            <div class="stat-label">今日新增</div>
            <div class="stat-value">{{ overview.new_today ?? '-' }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-card">
            <div class="stat-label">负面帖数</div>
            <div class="stat-value negative">{{ overview.negative_count ?? '-' }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-card">
            <div class="stat-label">待处理预警</div>
            <div class="stat-value warning">{{ overview.alert_count ?? '-' }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 互动量趋势 -->
    <el-card shadow="never" header="互动量趋势" class="block-card">
      <AreaTrend :data="interaction" />
    </el-card>

    <!-- 舆情热度变化趋势 -->
    <el-card shadow="never" header="舆情热度变化趋势" class="block-card">
      <BaseChart :option="heatTrendOption" height="300px" />
    </el-card>

    <!-- 高频关键词（LLM 精选较慢，独立加载，算好后再渲染词云） -->
    <el-card shadow="never" header="高频关键词" class="block-card" v-loading="keywordsLoading">
      <div class="kw-wrap">
        <WordCloud v-if="keywords.length" :data="keywords" />
        <div v-else-if="!keywordsLoading" class="empty-hint">暂无关键词数据</div>
      </div>
    </el-card>

    <!-- 排行 -->
    <el-row :gutter="12">
      <el-col :span="12">
        <el-card shadow="never" header="热门帖子" class="block-card">
          <el-table :data="hotPosts" size="small" class="clickable" @row-click="(r: any) => goPost(r.post_id)">
            <el-table-column label="内容" prop="content" show-overflow-tooltip />
            <el-table-column label="作者" prop="author" width="90" />
            <el-table-column label="点赞" prop="like_count" width="80" />
            <el-table-column label="热度" prop="heat_score" width="70" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never" header="负面帖子" class="block-card">
          <el-table :data="negativePosts" size="small" class="clickable" @row-click="(r: any) => goPost(r.post_id)">
            <el-table-column label="内容" prop="content" show-overflow-tooltip />
            <el-table-column label="情感" width="70">
              <template #default="{ row }"><SentimentTag :sentiment="row.sentiment" /></template>
            </el-table-column>
            <el-table-column label="热度" prop="heat_score" width="70" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.filter-card { margin-bottom: 12px; }
.filter-bar { display: flex; gap: 12px; flex-wrap: wrap; }
.cards-row { margin-bottom: 12px; }
.stat-card { text-align: center; padding: 8px 0; }
.stat-label { color: #909399; font-size: 13px; }
.stat-value { font-size: 26px; font-weight: 700; margin-top: 4px; }
.stat-value.negative { color: #f56c6c; }
.stat-value.warning { color: #e6a23c; }
.block-card { margin-top: 12px; }
.kw-wrap { min-height: 320px; }
.clickable :deep(.el-table__row) { cursor: pointer; }
.empty-hint { color: #909399; text-align: center; padding: 20px; }
</style>