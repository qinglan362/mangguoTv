<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { postApi } from '@/api/modules/post'
import { analysisApi } from '@/api/modules/analysis'
import { crawlerApi, type CrawledComment } from '@/api/modules/crawler'
import SentimentTag from '@/components/posts/SentimentTag.vue'
import BaseChart from '@/components/charts/BaseChart.vue'

const route = useRoute()
const postId = Number(route.params.id)

const post = ref<any>(null)
const snapshots = ref<any[]>([])
const correctionField = ref('sentiment')
const correctionValue = ref('')
const correctionNote = ref('')

const snapshotOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 50, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: snapshots.value.map((s) => dayjs(s.collected_at).format('YYYY-MM-DD HH:mm')) },
  yAxis: { type: 'value' },
  series: [{ name: '点赞', type: 'line', smooth: true, data: snapshots.value.map((s) => s.like_count), itemStyle: { color: '#409eff' } }],
}))

const comments = ref<CrawledComment[]>([])
const commentsTotal = ref(0)

async function load() {
  post.value = await postApi.detail(postId)
  snapshots.value = (await postApi.history(postId)) as any[]
  loadComments()
}

async function loadComments() {
  try {
    const res = await crawlerApi.comments(postId)
    comments.value = res.results || []
    commentsTotal.value = res.count || 0
  } catch {
    // 插件未安装/接口不可用时静默，不影响帖子详情其余功能
    comments.value = []
    commentsTotal.value = 0
  }
}

function openOriginal(url: string) {
  if (url) window.open(url, '_blank', 'noopener')
}

async function submitCorrection() {
  // M22：未分析的帖子无 post.analysis，直接访问 .id 会崩溃，需空值守卫
  const analysisId = post.value?.analysis?.id
  if (!analysisId) {
    ElMessage.warning('该帖暂未分析，无法人工修正')
    return
  }
  if (!correctionValue.value) {
    ElMessage.warning('请填写修正值')
    return
  }
  await analysisApi.correct(analysisId, {
    field: correctionField.value as any,
    corrected_value: correctionValue.value,
    note: correctionNote.value,
  })
  ElMessage.success('修正已保存')
  correctionValue.value = ''
  correctionNote.value = ''
  await load()
}

onMounted(load)
</script>

<template>
  <div v-if="post" class="post-detail">
    <el-card shadow="never">
      <div class="post-header">
        <h3>{{ post.title || '无标题' }}</h3>
        <div class="post-actions">
          <el-button type="primary" link @click="openOriginal(post.url)">查看原帖</el-button>
        </div>
      </div>
      <p class="post-content">{{ post.content }}</p>
      <div v-if="post.hashtags?.length" class="hashtags">
        <el-tag v-for="h in post.hashtags" :key="h" size="small" effect="plain">{{ h }}</el-tag>
      </div>
    </el-card>

    <el-row :gutter="12" class="block-row">
      <el-col :span="8">
        <el-card shadow="never" header="作者信息">
          <div class="author-info">
            <div class="author-name">{{ post.author?.name || post.author_name }}</div>
            <div>粉丝：{{ post.author?.follower_count || 0 }}</div>
            <el-tag v-if="post.author?.is_key_author" type="danger" size="small">重点账号</el-tag>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" header="互动数据">
          <div class="stats-grid">
            <div class="stat-item"><div class="num">{{ post.like_count }}</div><div class="label">点赞</div></div>
            <div class="stat-item"><div class="num">{{ post.comment_count }}</div><div class="label">评论</div></div>
            <div class="stat-item"><div class="num">{{ post.share_count }}</div><div class="label">转发</div></div>
            <div class="stat-item"><div class="num">{{ post.favorite_count }}</div><div class="label">收藏</div></div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" header="关联主题">
          <div v-for="hit in post.topic_hits" :key="hit.id" class="topic-hit">
            <div class="hit-topic">{{ hit.topic_name }}</div>
            <div class="hit-words">
              <el-tag v-for="kw in hit.matched_keywords" :key="kw.word" size="small" type="info" effect="plain">
                {{ kw.word }}
              </el-tag>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" header="舆情分析结果" class="block-row">
      <div v-if="post.analysis" class="analysis-block">
        <div class="analysis-row">
          <span class="label">情感倾向：</span><SentimentTag :sentiment="post.analysis.sentiment" />
          <el-tag size="small" effect="plain" type="info">来源：{{ post.analysis.sentiment_source }}</el-tag>
          <el-tag size="small" effect="plain">相关度：{{ post.analysis.related_score }}</el-tag>
          <el-tag size="small" effect="plain">热度：{{ post.analysis.heat_score }}</el-tag>
        </div>
        <div v-if="post.analysis.key_entities?.length" class="analysis-row">
          <span class="label">识别实体：</span>
          <el-tag v-for="e in post.analysis.key_entities" :key="e.name" size="small" type="success" effect="plain">
            {{ e.name }}({{ e.type }})
          </el-tag>
        </div>
        <div v-if="post.analysis.key_viewpoints?.length" class="analysis-row">
          <span class="label">核心观点：</span>
          <ul class="vp-list">
            <li v-for="v in post.analysis.key_viewpoints" :key="v">{{ v }}</li>
          </ul>
        </div>
      </div>
      <el-empty v-else description="该帖暂未分析" />
    </el-card>

    <el-row :gutter="12" class="block-row">
      <el-col :span="14">
        <el-card shadow="never" header="互动历史">
          <BaseChart :option="snapshotOption" :height="'240px'" />
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never" header="人工修正">
          <div class="correction-form">
            <el-select v-model="correctionField" style="width: 100%">
              <el-option label="情感倾向" value="sentiment" />
              <el-option label="相关性" value="related" />
              <el-option label="核心观点" value="viewpoint" />
              <el-option label="关键实体" value="entities" />
            </el-select>
            <el-select v-if="correctionField === 'sentiment'" v-model="correctionValue" placeholder="选择情感倾向">
              <el-option label="正面" value="positive" />
              <el-option label="中性" value="neutral" />
              <el-option label="负面" value="negative" />
            </el-select>
            <el-select v-else-if="correctionField === 'related'" v-model="correctionValue" placeholder="选择相关性">
              <el-option label="相关" value="true" />
              <el-option label="不相关" value="false" />
            </el-select>
            <el-input
              v-else
              v-model="correctionValue"
              :placeholder="correctionField === 'viewpoint' ? '观点文本，多条用逗号分隔' : '实体：逗号分隔名称，或 JSON 数组如 [{type: brand, name: 芒果TV}]'"
            />
            <el-input v-model="correctionNote" placeholder="修正说明（可选）" />
            <el-button type="primary" @click="submitCorrection">提交修正</el-button>
            <div class="tip">修正结果会回写分析结果，并用于后续规则与模型优化。</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 平台评论（小红书/微博采集器插件抓取） -->
    <el-card v-if="commentsTotal" shadow="never" header="平台评论" class="block-row">
      <div class="comment-total">共 {{ commentsTotal }} 条评论（插件采集，按点赞排序）</div>
      <div v-for="c in comments" :key="c.id" class="comment-item">
        <div class="comment-head">
          <span class="comment-author">{{ c.author_name || '匿名网友' }}</span>
          <span class="comment-like">赞 {{ c.like_count }}</span>
        </div>
        <div class="comment-content">{{ c.content }}</div>
      </div>
    </el-card>
  </div>
</template>


<style scoped>
.post-header { display: flex; justify-content: space-between; align-items: center; }
.post-content { line-height: 1.7; color: #303133; }
.hashtags { display: flex; gap: 6px; margin-top: 10px; }
.block-row { margin-top: 12px; }
.author-info { line-height: 2; }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); text-align: center; }
.stat-item .num { font-size: 22px; font-weight: 700; }
.stat-item .label { color: #909399; font-size: 12px; }
.topic-hit { margin-bottom: 10px; }
.hit-topic { font-weight: 600; margin-bottom: 4px; }
.hit-words { display: flex; gap: 4px; flex-wrap: wrap; }
.analysis-block .analysis-row { margin-bottom: 10px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.analysis-block .label { color: #909399; }
.vp-list { margin: 0; padding-left: 18px; }
.comment-total { color: #909399; font-size: 12px; margin-bottom: 8px; }
.comment-item { padding: 8px 0; border-bottom: 1px dashed #ebeef5; }
.comment-item:last-child { border-bottom: none; }
.comment-head { display: flex; justify-content: space-between; font-size: 12px; color: #909399; margin-bottom: 4px; }
.comment-author { font-weight: 600; color: #606266; }
.comment-content { font-size: 13px; line-height: 1.6; color: #303133; }
.correction-form { display: flex; flex-direction: column; gap: 10px; }
.tip { color: #909399; font-size: 12px; }
</style>
