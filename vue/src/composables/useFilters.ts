import { onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { topicApi } from '@/api/modules/topic'
import type { Topic } from '@/types'

/** 通用筛选：主题 / 平台 / 时间范围。供看板与列表页复用。
 *
 * 时间范围默认最近 7 天：采集回来的历史帖子（如小红书搜索返回的 2022/2023 年老帖）
 * 不会把趋势图的时间轴拉到几年前；需要全量数据时清空日期筛选即可。
 */
export function useFilters() {
  const topics = ref<Topic[]>([])
  const topicId = ref<number | undefined>(undefined)
  const platform = ref<string>('')
  const dateRange = ref<[string, string] | null>([
    dayjs().subtract(7, 'day').format('YYYY-MM-DDTHH:mm:ss'),
    dayjs().format('YYYY-MM-DDTHH:mm:ss'),
  ])

  async function loadTopics() {
    const res = await topicApi.list({ page_size: 100, status: 'active' })
    topics.value = (res as { results: Topic[] }).results
  }

  function queryParams(): Record<string, unknown> {
    const params: Record<string, unknown> = {}
    if (topicId.value) params.topic = topicId.value
    if (platform.value) params.platform = platform.value
    if (dateRange.value?.length === 2) {
      params.start = dateRange.value[0]
      params.end = dateRange.value[1]
    }
    return params
  }

  onMounted(loadTopics)

  return { topics, topicId, platform, dateRange, queryParams, loadTopics }
}
