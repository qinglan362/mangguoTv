<script setup lang="ts">
import { computed } from 'vue'
import BaseChart from './BaseChart.vue'

const props = defineProps<{
  data: Record<string, number>
  title?: string
  height?: string
}>()

const LABELS: Record<string, string> = {
  positive: '正面',
  neutral: '中性',
  negative: '负面',
  unknown: '未知',
  xiaohongshu: '小红书',
  weibo: '微博',
  mock: '模拟',
}

const COLOR: Record<string, string> = {
  positive: '#67c23a',
  neutral: '#909399',
  negative: '#f56c6c',
  unknown: '#b1b3b8',
  xiaohongshu: '#ff4d6a',
  weibo: '#e6162d',
  mock: '#409eff',
}

const option = computed(() => ({
  title: { text: props.title, left: 'center', textStyle: { fontSize: 14 } },
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { bottom: 0 },
  series: [{
    type: 'pie',
    radius: ['42%', '70%'],
    center: ['50%', '46%'],
    avoidLabelOverlap: true,
    itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
    label: { show: true, formatter: '{b}\n{c}' },
    data: Object.entries(props.data).map(([k, v]) => ({
      name: LABELS[k] || k,
      value: v,
      itemStyle: { color: COLOR[k] },
    })),
  }],
}))
</script>

<template>
  <BaseChart :option="option" :height="height || '320px'" />
</template>
