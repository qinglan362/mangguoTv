<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'
import BaseChart from './BaseChart.vue'

const props = defineProps<{
  data: { time: string; count: number }[]
  title?: string
  color?: string
  height?: string
}>()

const option = computed(() => ({
  title: { text: props.title, left: 'center', textStyle: { fontSize: 14 } },
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 40, bottom: 30 },
  xAxis: { type: 'category', data: props.data.map((d) => dayjs(d.time).format('YYYY-MM-DD HH:mm')) },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{
    name: '数量',
    type: 'line',
    smooth: true,
    data: props.data.map((d) => d.count),
    areaStyle: { opacity: 0.15 },
    itemStyle: { color: props.color || '#409eff' },
  }],
  dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16 }],
}))
</script>

<template>
  <BaseChart :option="option" :height="height || '320px'" />
</template>
