<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { topicApi } from '@/api/modules/topic'
import { collectorApi } from '@/api/modules/collector'
import type { Topic, TopicKeyword } from '@/types'

const route = useRoute()
const router = useRouter()
const editId = route.params.id ? Number(route.params.id) : null

const PLATFORM_LABELS: Record<string, string> = {
  xiaohongshu: '小红书',
  weibo: '微博',
  mock: '模拟数据',
}

const saving = ref(false)

// 精简表单：只保留 主题名称 / 关键词 / 采集平台 / 采集频率 / 监控周期
const form = reactive({
  name: '',
  platforms: [] as string[],
  collection_interval: 30,
  monitor_start: null as string | null,
  monitor_end: null as string | null,
  keywords_inline: [] as { word: string; kind: string }[],
})

const keywordInput = ref('')

function addKeyword() {
  const word = keywordInput.value.trim()
  if (!word) return
  if (form.keywords_inline.some((k) => k.word === word)) {
    keywordInput.value = ''
    return
  }
  form.keywords_inline.push({ word, kind: 'core' })
  keywordInput.value = ''
}
function removeKeyword(item: { word: string; kind: string }) {
  const idx = form.keywords_inline.findIndex((k) => k === item)
  if (idx >= 0) form.keywords_inline.splice(idx, 1)
}

// 已注册采集器的启用状态（用于平台提示）
const enabledCollectors = ref<string[]>([])
const disabledPlatforms = computed(() =>
  form.platforms.filter((p) => p !== 'mock' && !enabledCollectors.value.includes(p)),
)
const platformWarning = computed(() => {
  const parts: string[] = []
  if (disabledPlatforms.value.includes('xiaohongshu')) parts.push('「小红书」将通过 MediaCrawler 真实采集（点击立即采集时自动执行，浏览器弹出二维码扫码登录）')
  if (disabledPlatforms.value.includes('weibo')) parts.push('「微博」将通过 MediaCrawler 真实采集（点击立即采集时自动执行，浏览器弹出二维码扫码登录）')
  return parts.join('；')
})

async function loadCollectors() {
  try {
    const list = await collectorApi.list()
    enabledCollectors.value = list.filter((c) => c.enabled).map((c) => c.platform)
  } catch {
    /* 无权限时忽略，仅作提示用 */
  }
}

async function loadTopic() {
  if (!editId) return
  const topic = await topicApi.detail(editId)
  if (topic) {
    form.name = topic.name
    form.platforms = topic.platforms
    form.collection_interval = topic.collection_interval
    form.monitor_start = topic.monitor_start
    form.monitor_end = topic.monitor_end
    // 历史主题的关联词也并入关键词列表（保存后统一为核心词）
    form.keywords_inline = (topic.keywords || []).map((k: TopicKeyword) => ({ word: k.word, kind: 'core' }))
  }
}

async function submit() {
  // 输入框里未回车的内容自动提交，避免「输了词直接点保存却没生效」
  if (keywordInput.value.trim()) {
    const word = keywordInput.value.trim()
    if (!form.keywords_inline.some((k) => k.word === word)) {
      form.keywords_inline.push({ word, kind: 'core' })
    }
    keywordInput.value = ''
  }
  if (!form.name.trim()) {
    ElMessage.warning('请填写主题名称')
    return
  }
  if (!form.platforms.length) {
    ElMessage.warning('请至少选择一个采集平台')
    return
  }
  if (!form.keywords_inline.length) {
    ElMessage.warning('请至少添加一个关键词（输入后按回车或点「添加」按钮）')
    return
  }
  const payload = { ...form, monitor_start: form.monitor_start || null, monitor_end: form.monitor_end || null }
  saving.value = true
  try {
    if (editId) {
      await topicApi.update(editId, { ...payload, keywords: form.keywords_inline })
    } else {
      await topicApi.create(payload)
    }
    ElMessage.success('保存成功')
    router.push('/topics')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadTopic()
  loadCollectors()
})
</script>

<template>
  <el-card shadow="never" v-loading="saving">
    <el-form :model="form" label-width="110px">
      <el-divider content-position="left">基本信息</el-divider>
      <el-form-item label="主题名称" required>
        <el-input v-model="form.name" placeholder="例如：芒果TV、乘风2026、咸鱼飞升" />
      </el-form-item>
      <el-form-item label="采集平台" required>
        <div>
          <el-checkbox-group v-model="form.platforms">
            <el-checkbox value="xiaohongshu">小红书</el-checkbox>
            <el-checkbox value="weibo">微博</el-checkbox>
            <el-checkbox value="mock">模拟数据</el-checkbox>
          </el-checkbox-group>
          <el-alert
            v-if="disabledPlatforms.length"
            type="warning"
            :closable="false"
            show-icon
            class="platform-tip"
            :title="platformWarning"
          />
        </div>
      </el-form-item>
      <el-form-item label="采集频率">
        <div>
          <el-input-number
            v-model="form.collection_interval"
            :min="5"
            :max="1440"
            :step="5"
            controls-position="right"
            style="width: 200px"
          />
          <span class="interval-unit">分钟（可自定义 5 ~ 1440，定时采集按此间隔自动执行）</span>
        </div>
      </el-form-item>

      <el-divider content-position="left">监控周期</el-divider>
      <el-form-item label="监测起止">
        <el-date-picker
          v-model="form.monitor_start"
          type="datetime"
          placeholder="开始时间"
        />
        <span style="margin: 0 8px">至</span>
        <el-date-picker v-model="form.monitor_end" type="datetime" placeholder="结束时间" />
      </el-form-item>

      <el-divider content-position="left">关键词</el-divider>
      <el-form-item label="关键词" required>
        <div class="kw-editor">
          <el-tag v-for="(k, i) in form.keywords_inline" :key="i" closable type="primary" @close="removeKeyword(k)">
            {{ k.word }}
          </el-tag>
          <el-input v-model="keywordInput" placeholder="输入关键词，回车或点添加（可多个）" style="width: 280px" @keyup.enter="addKeyword" />
          <el-button size="small" @click="addKeyword">添加</el-button>
        </div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="saving" @click="submit">保存主题</el-button>
        <el-button @click="router.push('/topics')">取消</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<style scoped>
.kw-editor { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; width: 100%; }
.platform-tip { margin-top: 8px; width: 100%; }
.interval-unit { margin-left: 10px; color: #909399; font-size: 12px; }
</style>