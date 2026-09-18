import axios from 'axios'
import type { TripFormData, TripPlanResponse, PlanCandidateResponse, PlanConfirmRequest } from '@/types'

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
