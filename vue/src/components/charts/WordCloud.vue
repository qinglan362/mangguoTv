<script setup lang="ts">
import { computed } from 'vue'
import 'echarts-wordcloud'
import BaseChart from './BaseChart.vue'

const props = defineProps<{
  data: { keyword: string; count: number }[]
  height?: string
}>()

const option = computed(() => ({
  tooltip: { show: true },
  series: [{
    type: 'wordCloud',
    gridSize: 12,
    sizeRange: [12, 42],
    rotationRange: [-45, 45],
    textStyle: { fontFamily: 'sans-serif' },
    data: props.data.map((d) => ({ name: d.keyword, value: d.count })),
  }],
}))
</script>

<template>
  <BaseChart :option="option" :height="height || '320px'" />
</template>
