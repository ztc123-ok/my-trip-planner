// 类型定义

export interface Location {
  longitude: number
  latitude: number
}

export interface Attraction {
  name: string
  address: string
  location: Location
  visit_duration: number
  description: string
  category?: string
  rating?: number
  image_url?: string
  ticket_price?: number
  booking_tips?: string
  tips?: string
}

export interface Meal {
  type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  name: string
  address?: string
  location?: Location
  description?: string
  estimated_cost?: number
}

export interface Hotel {
  name: string
  address: string
  location?: Location
  price_range: string
  rating: string
  distance: string
  type: string
  estimated_cost?: number
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_meals: number
  total_transportation: number
  total: number
}

export interface DayPlan {
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel
  attractions: Attraction[]
  meals: Meal[]
}

export interface WeatherInfo {
  date: string
  source?: string
  day_weather: string
  night_weather: string
  day_temp: number
  night_temp: number
  wind_direction: string
  wind_power: string
}

export interface TripPlan {
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info: WeatherInfo[]
  overall_suggestions: string
  budget?: Budget
  knowledge_highlights?: string[]
}

export interface TripFormData {
  city: string
  start_date: string
  end_date: string
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input: string
  has_explicit_dates?: boolean
  has_explicit_start_date?: boolean
  has_explicit_duration?: boolean
  has_explicit_city?: boolean
  clarification_prompt?: string
}

export interface TripPlanResponse {
  success: boolean
  message: string
  data?: TripPlan
  thread_id?: string
  evaluation?: EvaluationReport
}

export interface POIInfo {
  id: string
  name: string
  type: string
  address: string
  location?: Location
  tel?: string
  price_range?: string
  rating?: string
  tag?: string
  distance?: string
}

export interface PlanCandidateData {
  thread_id: string
  city: string
  travel_days: number
  start_date?: string
  end_date?: string
  candidate_attractions: POIInfo[]
  candidate_hotels: POIInfo[]
  weather_info: WeatherInfo[]
  knowledge_highlights?: string[]
}

export interface PlanCandidateResponse {
  success: boolean
  message: string
  data?: PlanCandidateData
}

export interface PlanConfirmRequest {
  thread_id: string
  selected_attractions?: string[]
  selected_hotel?: string
  user_feedback?: string
  start_date?: string
  end_date?: string
}

export interface TripStateData {
  thread_id: string
  next_nodes: string[]
  is_interrupted: boolean
  is_completed: boolean
  city?: string
  travel_days?: number
  has_plan: boolean
  candidate_attractions_count: number
  candidate_hotels_count: number
  retry_count: number
}

export interface TripStateResponse {
  success: boolean
  message: string
  data?: TripStateData
}

// Phase 2: 对话式交互与流式推送类型定义

export interface ThoughtStep {
  id: string
  title: string
  detail: string
  status: 'running' | 'completed' | 'failed'
  stage?: string
  node?: string
  elapsedSeconds?: number
  timestamp?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  planData?: TripPlan
  streamEvents?: StreamEvent[]
  thoughtSteps?: ThoughtStep[]
  thoughtElapsed?: number
  isThoughtExpanded?: boolean
  loading?: boolean
  changesSummary?: string
  evaluation?: EvaluationReport
  // 前置轻量行程参数确认状态 (Pre-Search Parameter Confirmation)
  isParamConfirmPending?: boolean
  pendingParams?: TripFormData
  // HITL 人机协同卡片相关状态
  hitlCandidateData?: PlanCandidateData
  hitlStartDate?: string
  hitlEndDate?: string
  hitlTravelDays?: number
  initialTravelDays?: number
  initialStartDate?: string
  hitlRefreshing?: boolean
  hitlSelectedAttractions?: string[]
  hitlSelectedHotel?: string
  hitlUserFeedback?: string
  hitlConfirmed?: boolean
  hitlSubmitting?: boolean
}

export interface ChatModifyRequest {
  thread_id?: string
  message: string
  trip_plan: TripPlan
  chat_history?: { role: string; content: string }[]
}

export interface ChatModifyData {
  reply: string
  updated_plan?: TripPlan
  modified: boolean
  thread_id: string
  changes_summary?: string
  evaluation?: EvaluationReport
}

export interface ChatModifyResponse {
  success: boolean
  message: string
  data?: ChatModifyData
}

export interface StreamEvent {
  event: 'start' | 'node_start' | 'node_progress' | 'node_finish' | 'retry' | 'plan_complete' | 'error' | string
  node?: string
  name?: string
  status?: 'running' | 'completed' | 'failed'
  stage?: string
  progress?: number
  message?: string
  elapsed_seconds?: number
  data?: any
  thread_id?: string
  evaluation?: EvaluationReport
}

export interface AgentNodeStatus {
  key: string
  name: string
  icon: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  detail?: string
  progress?: number
}

export interface ChatSession {
  id: string
  title: string
  city: string
  updatedAt: string
  tripPlan?: TripPlan
  messages: ChatMessage[]
}

// ============ Phase 6: 评估与可观测性类型 ============

export interface EvaluationIssue {
  dimension: 'completeness' | 'geography' | 'budget' | 'overall' | string
  severity: 'error' | 'warning' | 'info'
  message: string
  day_index?: number
  suggestion?: string
}

export interface DimensionScore {
  dimension: string
  dimension_name: string
  score: number
  weight: number
  passed: boolean
  details: Record<string, any>
}

export interface EvaluationReport {
  overall_score: number
  grade: string
  passed: boolean
  dimensions: {
    completeness: DimensionScore
    geography: DimensionScore
    budget: DimensionScore
    [key: string]: DimensionScore
  }
  metrics: {
    total_days?: number
    expected_days?: number
    total_attractions?: number
    avg_attractions_per_day?: number
    total_route_distance_km?: number
    max_single_leg_km?: number
    budget_total?: number
    budget_arithmetic_valid?: boolean
    critical_errors_count?: number
    [key: string]: any
  }
  issues: EvaluationIssue[]
  suggestions: string[]
  created_at?: string
}

export interface PlanEvaluationResponse {
  success: boolean
  message: string
  data?: EvaluationReport
}

export interface ObservabilityStatus {
  tracing_enabled: boolean
  has_api_key: boolean
  project: string
  endpoint: string
  client_ready: boolean
}




