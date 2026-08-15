<script setup lang="ts">
import { computed } from 'vue'
import BaseChart from './BaseChart.vue'

const props = defineProps<{
  data: { name: string; value: number }[]
  /** 可选第二系列（如负面占比%），与 data 按顺序对齐 */
  compare?: { name: string; value: number }[]
  title?: string
  color?: string
  compareColor?: string
  height?: string
}>()

const option = computed(() => {
  const series: Record<string, unknown>[] = [{
    name: '数量',
    type: 'bar',
    data: props.data.map((d) => d.value),
    itemStyle: { color: props.color || '#409eff', borderRadius: [0, 4, 4, 0] },
    barMaxWidth: 22,
  }]
  let legend: { bottom: number; data: string[] } | undefined
  if (props.compare?.length) {
    series.push({
      name: '负面占比(%)',
      type: 'bar',
      data: props.compare.map((d) => d.value),
      itemStyle: { color: props.compareColor || '#f56c6c', borderRadius: [0, 4, 4, 0] },
      barMaxWidth: 22,
    })
    legend = { bottom: 0, data: ['数量', '负面占比(%)'] }
  }
  return {
    title: { text: props.title, left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend,
    grid: { left: 90, right: 20, top: 40, bottom: legend ? 50 : 30 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: props.data.map((d) => d.name), inverse: true },
    series,
  }
})
</script>

<template>
  <BaseChart :option="option" :height="height || '320px'" />
</template>
