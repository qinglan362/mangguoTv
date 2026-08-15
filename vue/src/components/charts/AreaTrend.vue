<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'
import BaseChart from './BaseChart.vue'

const props = defineProps<{
  data: { time: string; likes: number; comments: number; shares: number; favorites: number }[]
  title?: string
  height?: string
}>()

const option = computed(() => ({
  title: { text: props.title, left: 'center', textStyle: { fontSize: 14 } },
  tooltip: { trigger: 'axis' },
  legend: { bottom: 0, data: ['点赞', '评论', '转发', '收藏'] },
  grid: { left: 50, right: 20, top: 40, bottom: 50 },
  xAxis: { type: 'category', data: props.data.map((d) => dayjs(d.time).format('YYYY-MM-DD HH:mm')) },
  yAxis: { type: 'value' },
  series: [
    { name: '点赞', type: 'line', smooth: true, stack: 'total', data: props.data.map((d) => d.likes), areaStyle: { opacity: 0.2 } },
    { name: '评论', type: 'line', smooth: true, stack: 'total', data: props.data.map((d) => d.comments), areaStyle: { opacity: 0.2 } },
    { name: '转发', type: 'line', smooth: true, stack: 'total', data: props.data.map((d) => d.shares), areaStyle: { opacity: 0.2 } },
    { name: '收藏', type: 'line', smooth: true, stack: 'total', data: props.data.map((d) => d.favorites), areaStyle: { opacity: 0.2 } },
  ],
  dataZoom: [{ type: 'inside' }],
}))
</script>

<template>
  <BaseChart :option="option" :height="height || '320px'" />
</template>
