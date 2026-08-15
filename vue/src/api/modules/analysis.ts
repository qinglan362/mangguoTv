import http from '@/api'

export interface CorrectionPayload {
  field: 'sentiment' | 'related' | 'viewpoint' | 'entities'
  corrected_value: string | string[] | Record<string, unknown>[]
  note?: string
}

// 仅保留帖子详情页「人工修正」接口；分析列表/实体/观点/聚类/摘要页面已从主题详情移除，
// 对应后端接口已同步删除。
export const analysisApi = {
  correct: (id: number, data: CorrectionPayload) => http.post(`/analysis/${id}/correct/`, data),
}
