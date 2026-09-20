import axios from 'axios'
import type {
  TripFormData,
  TripPlanResponse,
  PlanCandidateResponse,
  PlanConfirmRequest,
  TripStateResponse,
  StreamEvent,
  ChatModifyRequest,
  ChatModifyResponse,
} from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // 四个 Agent 顺序执行时留出足够时间
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

/**
 * 生成旅行计划 (单阶段一键生成)
 */
export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.post<TripPlanResponse>('/api/trip/plan', formData)
    return response.data
  } catch (error: any) {
    console.error('生成旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '生成旅行计划失败')
  }
}

/**
 * HITL 阶段一：准备旅行计划（搜索候选景点与酒店并在 planner 前挂起）
 */
export async function prepareTripPlan(formData: TripFormData): Promise<PlanCandidateResponse> {
  try {
    const response = await apiClient.post<PlanCandidateResponse>('/api/trip/plan/prepare', formData)
    return response.data
  } catch (error: any) {
    console.error('准备旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '准备旅行计划失败')
  }
}

/**
 * HITL 阶段二：确认候选并恢复执行生成最终旅行计划
 */
export async function confirmTripPlan(confirmData: PlanConfirmRequest): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.post<TripPlanResponse>('/api/trip/plan/confirm', confirmData)
    return response.data
  } catch (error: any) {
    console.error('确认旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '确认旅行计划失败')
  }
}

/**
 * 查询旅行规划会话状态（支持断点检测与恢复）
 */
export async function getTripPlanState(threadId: string): Promise<TripStateResponse> {
  try {
    const response = await apiClient.get<TripStateResponse>(`/api/trip/plan/state/${threadId}`)
    return response.data
  } catch (error: any) {
    console.error('获取规划状态失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '获取规划状态失败')
  }
}

/**
 * 流式生成旅行计划 (SSE Fetch 读取器)
 */
export async function generateTripPlanStream(
  formData: TripFormData,
  onEvent: (event: StreamEvent) => void,
  onError?: (err: any) => void
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/trip/plan/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(formData),
    })

    if (!response.ok || !response.body) {
      throw new Error(`流式连接失败: HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split(/(?:\r?\n){2}/)
      buffer = lines.pop() || ''

      for (const block of lines) {
        if (!block.trim()) continue
        const blockLines = block.split(/\r?\n/)
        let eventName = 'message'
        let dataStr = ''

        for (const rawLine of blockLines) {
          const line = rawLine.trim()
          if (line.startsWith('event:')) {
            eventName = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            dataStr = line.slice(5).trim()
          }
        }

        if (dataStr) {
          try {
            const parsedData = JSON.parse(dataStr)
            onEvent({
              event: eventName,
              ...parsedData,
            })
          } catch (e) {
            console.warn('解析 SSE 数据块异常:', e, dataStr)
          }
        }
      }
    }
  } catch (err) {
    console.error('SSE 流式传输异常:', err)
    if (onError) {
      onError(err)
    } else {
      throw err
    }
  }
}

/**
 * 对话式修改行程计划 (调用后端 LangGraph chat_modify 子图)
 */
export async function chatModifyTripPlan(requestData: ChatModifyRequest): Promise<ChatModifyResponse> {
  try {
    const response = await apiClient.post<ChatModifyResponse>('/api/trip/chat/modify', requestData)
    return response.data
  } catch (error: any) {
    console.error('对话修改行程失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '对话修改行程失败')
  }
}

/**
 * 自然语言旅行意图提取
 */
export async function parseNaturalLanguageTrip(text: string): Promise<TripFormData> {
  try {
    const response = await apiClient.post<{ success: boolean; data: TripFormData }>('/api/trip/chat/parse', { text })
    return response.data.data
  } catch (error: any) {
    console.error('自然语言意图提取失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '意图提取失败')
  }
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

export async function getAttractionPhoto(name: string, city: string): Promise<string | null> {
  const response = await apiClient.get('/api/poi/photo', { params: { name, city } })
  return response.data?.data?.photo_url || null
}

export default apiClient

