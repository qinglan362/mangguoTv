<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { postApi } from '@/api/modules/post'
import { useFilters } from '@/composables/useFilters'
import SentimentTag from '@/components/posts/SentimentTag.vue'
import type { Post } from '@/types'

const router = useRouter()
const { topics, topicId, platform } = useFilters()

const posts = ref<Post[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const sentiment = ref('')
const q = ref('')
const ordering = ref('-published_at')
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = (await postApi.list({
      topic: topicId.value,
      platform: platform.value || undefined,
      sentiment: sentiment.value || undefined,
      q: q.value || undefined,
      ordering: ordering.value,
      page: page.value,
      page_size: pageSize.value,
    })) as { count: number; results: Post[] }
    posts.value = res.results
    total.value = res.count
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function goDetail(id: number) {
  router.push(`/posts/${id}`)
}

function openOriginal(url: string) {
  window.open(url, '_blank')
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <!-- 筛选 -->
    <div class="filter-bar">
      <el-select v-model="topicId" placeholder="全部主题" clearable style="width: 180px" @change="search">
        <el-option v-for="t in topics" :key="t.id" :label="t.name" :value="t.id" />
      </el-select>
      <el-select v-model="platform" placeholder="全部平台" clearable style="width: 130px" @change="search">
        <el-option label="小红书" value="xiaohongshu" />
        <el-option label="微博" value="weibo" />
        <el-option label="模拟" value="mock" />
      </el-select>
      <el-select v-model="sentiment" placeholder="全部情感" clearable style="width: 130px" @change="search">
        <el-option label="正面" value="positive" />
        <el-option label="中性" value="neutral" />
        <el-option label="负面" value="negative" />
      </el-select>
      <el-select v-model="ordering" style="width: 150px" @change="search">
        <el-option label="最新发布" value="-published_at" />
        <el-option label="热度最高" value="-heat_score" />
        <el-option label="点赞最多" value="-like_count" />
      </el-select>
      <el-input v-model="q" placeholder="搜索内容关键词" clearable style="width: 220px" @keyup.enter="search" @clear="search" />
      <el-button type="primary" @click="search">查询</el-button>
    </div>

    <!-- 列表 -->
    <el-table v-loading="loading" :data="posts" size="small" class="post-table">
      <el-table-column label="内容" min-width="300">
        <template #default="{ row }">
          <div class="post-content" @click="goDetail(row.id)">{{ row.content }}</div>
        </template>
      </el-table-column>
      <el-table-column label="作者" prop="author_name" width="110" />
      <el-table-column label="平台" width="80">
        <template #default="{ row }">
          <el-tag v-if="row.platform === 'xiaohongshu'" type="danger" size="small">小红书</el-tag>
          <el-tag v-else-if="row.platform === 'weibo'" type="warning" size="small">微博</el-tag>
          <el-tag v-else size="small" type="info">模拟</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="情感" width="80">
        <template #default="{ row }"><SentimentTag :sentiment="row.sentiment" /></template>
      </el-table-column>
      <el-table-column label="点赞" prop="like_count" width="90" />
      <el-table-column label="评论" prop="comment_count" width="90" />
      <el-table-column label="热度" prop="heat_score" width="80" />
      <el-table-column label="发布时间" width="150">
        <template #default="{ row }">{{ row.published_at ? dayjs(row.published_at).format('YYYY-MM-DD HH:mm') : '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="goDetail(row.id)">详情</el-button>
          <el-button link type="primary" size="small" @click="openOriginal(row.url)">原帖</el-button>
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
.filter-bar { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
.post-content { cursor: pointer; color: #303133; line-height: 1.5; }
.post-content:hover { color: #409eff; }
.pagination-bar { display: flex; justify-content: flex-end; margin-top: 14px; }
</style>
