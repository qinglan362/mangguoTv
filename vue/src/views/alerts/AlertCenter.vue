<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import dayjs from 'dayjs'
import { alertApi } from '@/api/modules/alert'
import { topicApi } from '@/api/modules/topic'
import type { AlertEvent, AlertLevel, AlertNotification, AlertRule, Topic } from '@/types'

// ---------- 类型与常量 ----------
type TabName = 'events' | 'rules' | 'notifications'
const activeTab = ref<TabName>('events')

const LEVEL_MAP: Record<string, { label: string; type: 'info' | 'warning' | 'danger' | 'primary' }> = {
  low: { label: '低', type: 'info' },
  medium: { label: '中', type: 'warning' },
  high: { label: '高', type: 'danger' },
  critical: { label: '严重', type: 'danger' },
}

const RULE_TYPES: { value: string; label: string }[] = [
  { value: 'negative_keyword', label: '负面关键词出现' },
  { value: 'like_threshold', label: '负面帖点赞超阈值' },
  { value: 'negative_spike', label: '负面帖数量激增' },
  { value: 'coordinated_posting', label: '同观点多账号集中发布' },
  { value: 'interaction_spike', label: '互动量异常增长' },
  { value: 'key_author_negative', label: '重点账号发布负面' },
]

const CHANNELS = [
  { label: '站内消息', value: 'platform' },
  { label: '邮件', value: 'email' },
]

const EVENT_STATUS_MAP: Record<string, { label: string; type: 'info' | 'success' | 'warning' | 'danger' }> = {
  new: { label: '待处理', type: 'danger' },
  acknowledged: { label: '已确认', type: 'warning' },
  resolved: { label: '已解决', type: 'success' },
}

// ---------- 事件列表 ----------
const topics = ref<Topic[]>([])
const events = ref<AlertEvent[]>([])
const eventsTotal = ref(0)
const eventsLoading = ref(false)
const eventFilter = reactive({
  topic: undefined as number | undefined,
  status: '' as string,
  level: '' as string,
  page: 1,
  pageSize: 20,
})

async function loadEvents() {
  eventsLoading.value = true
  try {
    const params: Record<string, unknown> = {
      page: eventFilter.page,
      page_size: eventFilter.pageSize,
    }
    if (eventFilter.topic) params.topic = eventFilter.topic
    if (eventFilter.status) params.status = eventFilter.status
    if (eventFilter.level) params.level = eventFilter.level
    const data = await alertApi.events(params)
    events.value = data.results
    eventsTotal.value = data.count
  } finally {
    eventsLoading.value = false
  }
}

async function ackEvent(row: AlertEvent) {
  await alertApi.ackEvent(row.id)
  ElMessage.success('已确认')
  loadEvents()
}

async function resolveEvent(row: AlertEvent) {
  await alertApi.resolveEvent(row.id)
  ElMessage.success('已标记解决')
  loadEvents()
}

// ---------- 规则管理 ----------
const rules = ref<AlertRule[]>([])
const ruleDialogVisible = ref(false)
const editingRule = ref<AlertRule | null>(null)
const ruleFormRef = ref<FormInstance>()
const ruleForm = reactive({
  topic: undefined as number | undefined,
  name: '',
  rule_type: 'negative_keyword' as string,
  level: 'medium' as AlertLevel,
  enabled: true,
  cooldown_minutes: 60,
  notify_channels: ['platform'] as string[],
  notify_recipients: [] as string[],
  config: {} as Record<string, unknown>,
})
const ruleRules: FormRules = {
  topic: [{ required: true, message: '请选择主题', trigger: 'change' }],
  name: [{ required: true, message: '请输入规则名称', trigger: 'blur' }],
  rule_type: [{ required: true, message: '请选择规则类型', trigger: 'change' }],
}

// M20：notify_recipients 为数组，el-input 直接 v-model 数组会在输入时变成字符串，
// 保存时 .filter 崩溃。用 computed 字符串字段做「逗号分隔 ⇄ 数组」双向转换。
const notifyRecipientsText = computed({
  get: () => ruleForm.notify_recipients.join(', '),
  set: (v: string) => {
    ruleForm.notify_recipients = v
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean)
  },
})

const RULE_CONFIG_FIELDS: Record<string, { key: string; label: string; type: 'number' | 'text'; default: unknown; placeholder?: string }[]> = {
  negative_keyword: [
    { key: 'keywords', label: '负面关键词（逗号分隔）', type: 'text', default: '', placeholder: '例如：无法播放,会员还要看广告,自动续费' },
    { key: 'min_count', label: '最少命中条数', type: 'number', default: 1 },
  ],
  like_threshold: [
    { key: 'threshold', label: '点赞阈值', type: 'number', default: 1000 },
  ],
  negative_spike: [
    { key: 'window_minutes', label: '统计窗口(分钟)', type: 'number', default: 60 },
    { key: 'growth_ratio', label: '增长倍数', type: 'number', default: 2 },
    { key: 'min_count', label: '窗口内最少负面条数', type: 'number', default: 5 },
  ],
  coordinated_posting: [
    { key: 'window_minutes', label: '统计窗口(分钟)', type: 'number', default: 60 },
    { key: 'min_posts', label: '同词最少帖数', type: 'number', default: 5 },
    { key: 'min_accounts', label: '最少账号数', type: 'number', default: 3 },
  ],
  interaction_spike: [
    { key: 'growth_ratio', label: '增长倍数', type: 'number', default: 2 },
    { key: 'min_abs', label: '最少增量(互动数)', type: 'number', default: 500 },
  ],
  key_author_negative: [],
}

async function loadRules() {
  const data = await alertApi.rules({ page_size: 100 })
  rules.value = data.results
}

function openCreateRule() {
  editingRule.value = null
  Object.assign(ruleForm, {
    topic: undefined,
    name: '',
    rule_type: 'negative_keyword',
    level: 'medium',
    enabled: true,
    cooldown_minutes: 60,
    notify_channels: ['platform'],
    notify_recipients: [],
    config: {},
  })
  ruleDialogVisible.value = true
}

function openEditRule(row: AlertRule) {
  editingRule.value = row
  Object.assign(ruleForm, {
    topic: row.topic,
    name: row.name,
    rule_type: row.rule_type,
    level: row.level,
    enabled: row.enabled,
    cooldown_minutes: row.cooldown_minutes,
    notify_channels: row.notify_channels || ['platform'],
    notify_recipients: row.notify_recipients || [],
    config: { ...(row.config || {}) },
  })
  ruleDialogVisible.value = true
}

async function saveRule() {
  await ruleFormRef.value?.validate()
  const cfg: Record<string, unknown> = {}
  const keywordsRaw = ruleForm.config['keywords']
  if (typeof keywordsRaw === 'string' && keywordsRaw.trim()) {
    cfg['keywords'] = keywordsRaw.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean)
  }
  for (const field of RULE_CONFIG_FIELDS[ruleForm.rule_type] || []) {
    if (field.key === 'keywords') continue
    const v = ruleForm.config[field.key]
    if (v !== undefined && v !== '') cfg[field.key] = Number(v)
  }
  const payload = {
    topic: ruleForm.topic,
    name: ruleForm.name,
    rule_type: ruleForm.rule_type,
    level: ruleForm.level,
    enabled: ruleForm.enabled,
    cooldown_minutes: Number(ruleForm.cooldown_minutes),
    notify_channels: ruleForm.notify_channels,
    notify_recipients: ruleForm.notify_recipients.filter((r) => r.trim()),
    config: cfg,
  }
  if (editingRule.value) {
    await alertApi.updateRule(editingRule.value.id, payload)
    ElMessage.success('规则已更新')
  } else {
    await alertApi.createRule(payload)
    ElMessage.success('规则已创建')
  }
  ruleDialogVisible.value = false
  loadRules()
}

async function removeRule(row: AlertRule) {
  await ElMessageBox.confirm(`确认删除规则「${row.name}」？`, '提示', { type: 'warning' })
  await alertApi.deleteRule(row.id)
  ElMessage.success('已删除')
  loadRules()
}

async function toggleRule(row: AlertRule) {
  await alertApi.updateRule(row.id, { enabled: !row.enabled })
  ElMessage.success(row.enabled ? '已启用' : '已停用')
  loadRules()
}

// ---------- 通知记录 ----------
const notifications = ref<AlertNotification[]>([])
const notifyTotal = ref(0)
const notifyFilter = reactive({ page: 1, pageSize: 20 })

async function loadNotifications() {
  const data = await alertApi.notifications({
    page: notifyFilter.page,
    page_size: notifyFilter.pageSize,
  })
  notifications.value = data.results
  notifyTotal.value = data.count
}

const configFields = (t: string) => RULE_CONFIG_FIELDS[t] || []

// ---------- 工具 ----------
function fmtTime(s: string | null) {
  return s ? dayjs(s).format('YYYY-MM-DD HH:mm') : '-'
}

function snippet(p: Record<string, unknown>) {
  return String(p['snippet'] || p['title'] || '')
}

// ---------- 初始化 ----------
// tab 切换时重新拉取：通知/事件多由后台产生，仅挂载时拉一次会长期停留在旧数据
function onTabChange(name: TabName | string) {
  if (name === 'events') loadEvents()
  else if (name === 'rules') loadRules()
  else if (name === 'notifications') loadNotifications()
}

onMounted(async () => {
  const topicData = await topicApi.list({ page_size: 100 })
  topics.value = topicData.results
  loadEvents()
  loadRules()
  loadNotifications()
})
</script>

<template>
  <div class="alert-center">
    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="预警事件" name="events">
        <el-card shadow="never">
          <el-alert
            v-if="!rules.length"
            type="info"
            :closable="false"
            show-icon
            title="当前没有配置任何预警规则，不会产生预警事件；请先在「预警规则」页签新建规则。"
            style="margin-bottom: 12px"
          />
          <div class="filter-bar">
            <el-select v-model="eventFilter.topic" placeholder="全部主题" clearable style="width: 200px" @change="eventFilter.page = 1; loadEvents()">
              <el-option v-for="t in topics" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
            <el-select v-model="eventFilter.status" placeholder="状态" clearable style="width: 140px" @change="eventFilter.page = 1; loadEvents()">
              <el-option label="待处理" value="new" />
              <el-option label="已确认" value="acknowledged" />
              <el-option label="已解决" value="resolved" />
            </el-select>
            <el-select v-model="eventFilter.level" placeholder="等级" clearable style="width: 120px" @change="eventFilter.page = 1; loadEvents()">
              <el-option v-for="(v, k) in LEVEL_MAP" :key="k" :label="v.label" :value="k" />
            </el-select>
            <el-button type="primary" @click="eventFilter.page = 1; loadEvents()">查询</el-button>
          </div>

          <el-table v-loading="eventsLoading" :data="events" style="width: 100%" @expand-change="() => undefined">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="event-detail">
                  <p class="reason">{{ row.reason }}</p>
                  <template v-if="row.matched_posts?.length">
                    <p class="sub-title">相关帖子（{{ row.matched_posts.length }} 条）</p>
                    <ul>
                      <li v-for="(p, i) in row.matched_posts.slice(0, 10)" :key="i">
                        <a :href="String(p.url || '')" target="_blank" rel="noopener">{{ p.post_id }}</a>
                        {{ snippet(p) }}
                      </li>
                    </ul>
                  </template>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="等级" width="80">
              <template #default="{ row }">
                <el-tag :type="LEVEL_MAP[row.level]?.type || 'info'" size="small">{{ LEVEL_MAP[row.level]?.label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="topic_name" label="主题" width="150" />
            <el-table-column prop="rule_name" label="规则" width="150" />
            <el-table-column prop="reason" label="触发原因" min-width="240" show-overflow-tooltip />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="EVENT_STATUS_MAP[row.status]?.type" size="small">{{ EVENT_STATUS_MAP[row.status]?.label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="触发时间" width="120">
              <template #default="{ row }">{{ fmtTime(row.triggered_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button v-if="row.status === 'new'" link type="primary" size="small" @click="ackEvent(row)">确认</el-button>
                <el-button v-if="row.status !== 'resolved'" link type="success" size="small" @click="resolveEvent(row)">解决</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="eventFilter.page"
            :page-size="eventFilter.pageSize"
            :total="eventsTotal"
            layout="total, prev, pager, next"
            @current-change="loadEvents"
          />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="预警规则" name="rules">
        <el-card shadow="never">
          <div class="filter-bar">
            <el-button type="primary" @click="openCreateRule">新建规则</el-button>
          </div>
          <el-table :data="rules" style="width: 100%">
            <el-table-column prop="name" label="规则名称" min-width="140" />
            <el-table-column prop="topic_name" label="主题" width="150" />
            <el-table-column label="类型" width="160">
              <template #default="{ row }">{{ row.rule_type_label || row.rule_type }}</template>
            </el-table-column>
            <el-table-column label="等级" width="80">
              <template #default="{ row }">
                <el-tag :type="LEVEL_MAP[row.level]?.type || 'info'" size="small">{{ LEVEL_MAP[row.level]?.label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="启用" width="80">
              <template #default="{ row }">
                <el-switch :model-value="row.enabled" @change="toggleRule(row)" />
              </template>
            </el-table-column>
            <el-table-column label="通知渠道" width="130">
              <template #default="{ row }">
                {{ (row.notify_channels || []).map((c: string) => c === 'email' ? '邮件' : '站内').join(' / ') || '站内' }}
              </template>
            </el-table-column>
            <el-table-column prop="cooldown_minutes" label="冷却(分)" width="90" />
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openEditRule(row)">编辑</el-button>
                <el-button link type="danger" size="small" @click="removeRule(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="通知记录" name="notifications">
        <el-card shadow="never">
          <el-table :data="notifications" style="width: 100%">
            <el-table-column label="渠道" width="90">
              <template #default="{ row }">
                {{ row.channel === 'email' ? '邮件' : '站内' }}
              </template>
            </el-table-column>
            <el-table-column prop="recipient" label="接收方" width="180" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="row.status === 'sent' ? 'success' : row.status === 'failed' ? 'danger' : 'info'" size="small">
                  {{ row.status === 'sent' ? '已发送' : row.status === 'failed' ? '失败' : '待发送' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="发送时间" width="150">
              <template #default="{ row }">{{ fmtTime(row.sent_at) }}</template>
            </el-table-column>
            <el-table-column prop="error_message" label="错误信息" min-width="180" show-overflow-tooltip />
          </el-table>
          <el-pagination
            v-model:current-page="notifyFilter.page"
            :page-size="notifyFilter.pageSize"
            :total="notifyTotal"
            layout="total, prev, pager, next"
            @current-change="loadNotifications"
          />
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 规则编辑对话框 -->
    <el-dialog v-model="ruleDialogVisible" :title="editingRule ? '编辑规则' : '新建规则'" width="560px">
      <el-form ref="ruleFormRef" :model="ruleForm" :rules="ruleRules" label-width="120px">
        <el-form-item label="主题" prop="topic">
          <el-select v-model="ruleForm.topic" placeholder="选择主题" style="width: 100%" :disabled="!!editingRule">
            <el-option v-for="t in topics" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="规则名称" prop="name">
          <el-input v-model="ruleForm.name" placeholder="例如：负面关键词预警" />
        </el-form-item>
        <el-form-item label="规则类型" prop="rule_type">
          <el-select v-model="ruleForm.rule_type" style="width: 100%" :disabled="!!editingRule">
            <el-option v-for="rt in RULE_TYPES" :key="rt.value" :label="rt.label" :value="rt.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-for="field in configFields(ruleForm.rule_type)" :key="field.key" :label="field.label">
          <el-input
            v-if="field.type === 'text'"
            v-model="ruleForm.config[field.key]"
            :placeholder="field.placeholder"
          />
          <el-input-number v-else v-model="ruleForm.config[field.key]" :min="0" :step="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="关注等级">
          <el-select v-model="ruleForm.level" style="width: 100%">
            <el-option v-for="(v, k) in LEVEL_MAP" :key="k" :label="v.label" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item label="冷却时间(分)">
          <el-input-number v-model="ruleForm.cooldown_minutes" :min="0" :step="5" style="width: 100%" />
        </el-form-item>
        <el-form-item label="通知渠道">
          <el-checkbox-group v-model="ruleForm.notify_channels">
            <el-checkbox v-for="c in CHANNELS" :key="c.value" :value="c.value">{{ c.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item v-if="ruleForm.notify_channels.includes('email')" label="邮件接收人">
          <el-input v-model="notifyRecipientsText" placeholder="多个邮箱用逗号分隔" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="ruleForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ruleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRule">保存</el-button>
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
}
.event-detail {
  padding: 8px 16px;
}
.reason {
  font-weight: 600;
  margin-bottom: 8px;
}
.sub-title {
  color: #909399;
  font-size: 12px;
  margin: 8px 0 4px;
}
.event-detail ul {
  margin: 0;
  padding-left: 20px;
  max-height: 240px;
  overflow-y: auto;
}
.event-detail li {
  font-size: 12px;
  color: #606266;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
