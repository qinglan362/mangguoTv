<script setup lang="ts">
import { computed } from 'vue'
import type { Sentiment } from '@/types'

const props = defineProps<{ sentiment: Sentiment | null | undefined }>()

type TagType = 'success' | 'info' | 'danger'

const current = computed<{ label: string; type: TagType }>(() => {
  switch (props.sentiment) {
    case 'positive':
      return { label: '正面', type: 'success' }
    case 'neutral':
      return { label: '中性', type: 'info' }
    case 'negative':
      return { label: '负面', type: 'danger' }
    default:
      return { label: '未知', type: 'info' }
  }
})
</script>

<template>
  <el-tag :type="current.type" size="small" effect="light">{{ current.label }}</el-tag>
</template>
