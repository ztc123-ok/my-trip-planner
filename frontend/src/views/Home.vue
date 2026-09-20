<template>
  <div class="home-container">
    <!-- 背景装饰 -->
    <div class="bg-decoration">
      <div class="circle circle-1"></div>
      <div class="circle circle-2"></div>
      <div class="circle circle-3"></div>
    </div>

    <!-- 页面标题 -->
    <div class="page-header">
      <div class="icon-wrapper">
        <span class="icon">✈️</span>
      </div>
      <h1 class="page-title">智能旅行助手</h1>
      <p class="page-subtitle">基于AI的个性化旅行规划,让每一次出行都完美无忧</p>
      <div style="margin-top: 14px;">
        <a-button type="primary" shape="round" size="large" @click="goToWorkspace">
          💬 进入全新 AI 对话工作台（推荐）
        </a-button>
      </div>

    </div>


    <a-card class="form-card" :bordered="false">
      <a-form
        :model="formData"
        layout="vertical"
        @finish="handleSubmit"
      >
        <!-- 第一步:目的地和日期 -->
        <div class="form-section">
          <div class="section-header">
            <span class="section-icon">📍</span>
            <span class="section-title">目的地与日期</span>
          </div>

          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="city" :rules="[{ required: true, message: '请输入目的地城市' }]">
                <template #label>
                  <span class="form-label">目的地城市</span>
                </template>
                <a-input
                  v-model:value="formData.city"
                  placeholder="例如: 北京"
                  size="large"
                  class="custom-input"
                >
                  <template #prefix>
                    <span style="color: #1890ff;">🏙️</span>
                  </template>
                </a-input>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item name="start_date" :rules="[{ required: true, message: '请选择开始日期' }]">
                <template #label>
                  <span class="form-label">开始日期</span>
                </template>
                <a-date-picker
                  v-model:value="formData.start_date"
                  style="width: 100%"
                  size="large"
                  class="custom-input"
                  placeholder="选择日期"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item name="end_date" :rules="[{ required: true, message: '请选择结束日期' }]">
                <template #label>
                  <span class="form-label">结束日期</span>
                </template>
                <a-date-picker
                  v-model:value="formData.end_date"
                  style="width: 100%"
                  size="large"
                  class="custom-input"
                  placeholder="选择日期"
                />
              </a-form-item>
            </a-col>
            <a-col :span="4">
              <a-form-item>
                <template #label>
                  <span class="form-label">旅行天数</span>
                </template>
                <div class="days-display-compact">
                  <span class="days-value">{{ formData.travel_days }}</span>
                  <span class="days-unit">天</span>
                </div>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 第二步:偏好设置 -->
        <div class="form-section">
          <div class="section-header">
            <span class="section-icon">⚙️</span>
            <span class="section-title">偏好设置</span>
          </div>

          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="transportation">
                <template #label>
                  <span class="form-label">交通方式</span>
                </template>
                <a-select v-model:value="formData.transportation" size="large" class="custom-select">
                  <a-select-option value="公共交通">🚇 公共交通</a-select-option>
                  <a-select-option value="自驾">🚗 自驾</a-select-option>
                  <a-select-option value="步行">🚶 步行</a-select-option>
                  <a-select-option value="混合">🔀 混合</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item name="accommodation">
                <template #label>
                  <span class="form-label">住宿偏好</span>
                </template>
                <a-select v-model:value="formData.accommodation" size="large" class="custom-select">
                  <a-select-option value="经济型酒店">💰 经济型酒店</a-select-option>
                  <a-select-option value="舒适型酒店">🏨 舒适型酒店</a-select-option>
                  <a-select-option value="豪华酒店">⭐ 豪华酒店</a-select-option>
                  <a-select-option value="民宿">🏡 民宿</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item name="preferences">
                <template #label>
                  <span class="form-label">旅行偏好</span>
                </template>
                <div class="preference-tags">
                  <a-checkbox-group v-model:value="formData.preferences" class="custom-checkbox-group">
                    <a-checkbox value="历史文化" class="preference-tag">🏛️ 历史文化</a-checkbox>
                    <a-checkbox value="自然风光" class="preference-tag">🏞️ 自然风光</a-checkbox>
                    <a-checkbox value="美食" class="preference-tag">🍜 美食</a-checkbox>
                    <a-checkbox value="购物" class="preference-tag">🛍️ 购物</a-checkbox>
                    <a-checkbox value="艺术" class="preference-tag">🎨 艺术</a-checkbox>
                    <a-checkbox value="休闲" class="preference-tag">☕ 休闲</a-checkbox>
                  </a-checkbox-group>
                </div>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 第三步:额外要求 -->
        <div class="form-section">
          <div class="section-header">
            <span class="section-icon">💬</span>
            <span class="section-title">额外要求</span>
          </div>

          <a-form-item name="free_text_input">
            <a-textarea
              v-model:value="formData.free_text_input"
              placeholder="请输入您的额外要求,例如:想去看升旗、需要无障碍设施、对海鲜过敏等..."
              :rows="3"
              size="large"
              class="custom-textarea"
            />
          </a-form-item>
        </div>

        <!-- 人机协同确认模式 (Human-in-the-Loop) -->
        <div class="hitl-switch-card">
          <div class="hitl-switch-info">
            <span class="hitl-switch-icon">🤝</span>
            <div>
              <div class="hitl-switch-title">人机协同确认模式 (Human-in-the-Loop)</div>
              <div class="hitl-switch-desc">并行搜索景点与酒店后暂停，由您挑选心仪候选并提出要求后再生成最终行程</div>
            </div>
          </div>
          <a-switch v-model:checked="enableHitl" checked-children="开启" un-checked-children="关闭" />
        </div>

        <!-- 提交按钮 -->
        <a-form-item>
          <a-button
            type="primary"
            html-type="submit"
            :loading="loading"
            size="large"
            block
            class="submit-button"
          >
            <template v-if="!loading">
              <span class="button-icon">🚀</span>
              <span>{{ enableHitl ? '搜集候选并确认 (人机协同)' : '开始规划我的旅行' }}</span>
            </template>
            <template v-else>
              <span>正在生成中...</span>
            </template>
          </a-button>
        </a-form-item>

        <!-- 加载进度条 -->
        <a-form-item v-if="loading">
          <div class="loading-container">
            <a-progress
              :percent="loadingProgress"
              status="active"
              :stroke-color="{
                '0%': '#667eea',
                '100%': '#764ba2',
              }"
              :stroke-width="10"
            />
            <p class="loading-status">
              {{ loadingStatus }}
            </p>
          </div>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- HITL 候选确认弹窗 -->
    <a-modal
      v-model:open="hitlModalVisible"
      title="🤝 人机协同：确认候选景点与酒店"
      width="900px"
      :confirm-loading="confirming"
      ok-text="确认并生成行程计划"
      cancel-text="放弃本次规划"
      @ok="handleConfirmHitl"
      @cancel="handleCancelHitl"
    >
      <div v-if="candidateData" class="hitl-modal-body">
        <a-alert
          message="已完成并行搜索，已在规划前挂起。请挑选您感兴趣的景点与酒店，也可在下方补充人工调整要求。"
          type="info"
          show-icon
          style="margin-bottom: 16px;"
        />

        <div class="hitl-field-label">📍 候选景点列表 (已为您默认全选，可取消不感兴趣项):</div>
        <div class="hitl-poi-scroll">
          <a-checkbox-group v-model:value="selectedAttractions" style="width: 100%;">
            <a-row :gutter="[12, 12]">
              <a-col :span="12" v-for="poi in candidateData.candidate_attractions" :key="poi.name">
                <div class="poi-select-card" :class="{ 'card-selected': selectedAttractions.includes(poi.name) }">
                  <a-checkbox :value="poi.name" class="poi-checkbox">
                    <div class="poi-info-content">
                      <span class="poi-name" :title="poi.name">{{ poi.name }}</span>
                      <span class="poi-addr" :title="poi.address">{{ poi.address || '地址未知' }}</span>
                    </div>
                  </a-checkbox>
                </div>
              </a-col>
            </a-row>
          </a-checkbox-group>
        </div>

        <div class="hitl-field-label" style="margin-top: 16px;">🏨 候选推荐酒店 (单选心仪酒店，可选):</div>
        <div class="hitl-poi-scroll">
          <a-radio-group v-model:value="selectedHotel" style="width: 100%;">
            <a-row :gutter="[12, 12]">
              <a-col :span="12" v-for="hotel in candidateData.candidate_hotels" :key="hotel.name">
                <div class="poi-select-card hotel-select-card" :class="{ 'card-selected': selectedHotel === hotel.name }">
                  <a-radio :value="hotel.name" class="hotel-radio">
                    <div class="hotel-content">
                      <div class="hotel-card-header">
                        <span class="poi-name hotel-name" :title="hotel.name">{{ hotel.name }}</span>
                        <span v-if="hotel.price_range" class="hotel-price-badge">{{ hotel.price_range }}</span>
                      </div>
                      <div class="hotel-meta-row" v-if="hotel.tag || hotel.rating || hotel.distance">
                        <a-tag v-if="hotel.tag" color="blue" size="small">{{ hotel.tag }}</a-tag>
                        <span v-if="hotel.rating" class="hotel-rating">⭐ {{ hotel.rating }}</span>
                        <span v-if="hotel.distance" class="hotel-distance" :title="hotel.distance">📍 {{ hotel.distance }}</span>
                      </div>
                      <span class="poi-addr" :title="hotel.address">{{ hotel.address || '地址未知' }}</span>
                    </div>
                  </a-radio>
                </div>
              </a-col>
            </a-row>
          </a-radio-group>
        </div>

        <div class="hitl-field-label" style="margin-top: 16px;">✍️ 补充人工调整意见 (可选):</div>
        <a-textarea
          v-model:value="userFeedback"
          placeholder="例如：第一天下午想在王府井逛街，晚餐希望安排北京烤鸭老字号"
          :rows="2"
        />
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { generateTripPlanStream, prepareTripPlan, confirmTripPlan, getTripPlanState } from '@/services/api'
import type { TripFormData, PlanCandidateData, StreamEvent } from '@/types'
import type { Dayjs } from 'dayjs'

const router = useRouter()
const goToWorkspace = () => {
  router.push('/')
}

const loading = ref(false)

const loadingProgress = ref(0)
const loadingStatus = ref('')

// Human-in-the-Loop 人机协同状态
const enableHitl = ref(false)
const hitlModalVisible = ref(false)
const confirming = ref(false)
const candidateData = ref<PlanCandidateData | null>(null)
const selectedAttractions = ref<string[]>([])
const selectedHotel = ref<string | undefined>(undefined)
const userFeedback = ref('')

// LocalStorage 状态持久化键名
const STORAGE_KEY_THREAD = 'pending_trip_thread_id'
const STORAGE_KEY_CANDIDATES = 'pending_trip_candidate_data'
const STORAGE_KEY_SELECTED_ATTRS = 'pending_trip_selected_attractions'
const STORAGE_KEY_SELECTED_HOTEL = 'pending_trip_selected_hotel'
const STORAGE_KEY_FEEDBACK = 'pending_trip_user_feedback'

const savePendingStorage = (data: PlanCandidateData) => {
  localStorage.setItem(STORAGE_KEY_THREAD, data.thread_id)
  localStorage.setItem(STORAGE_KEY_CANDIDATES, JSON.stringify(data))
  localStorage.setItem(STORAGE_KEY_SELECTED_ATTRS, JSON.stringify(selectedAttractions.value))
  if (selectedHotel.value) {
    localStorage.setItem(STORAGE_KEY_SELECTED_HOTEL, selectedHotel.value)
  }
  if (userFeedback.value) {
    localStorage.setItem(STORAGE_KEY_FEEDBACK, userFeedback.value)
  }
}

const clearPendingStorage = () => {
  localStorage.removeItem(STORAGE_KEY_THREAD)
  localStorage.removeItem(STORAGE_KEY_CANDIDATES)
  localStorage.removeItem(STORAGE_KEY_SELECTED_ATTRS)
  localStorage.removeItem(STORAGE_KEY_SELECTED_HOTEL)
  localStorage.removeItem(STORAGE_KEY_FEEDBACK)
}

// 页面加载时检测未完成的挂起规划
onMounted(async () => {
  const savedThreadId = localStorage.getItem(STORAGE_KEY_THREAD)
  const savedCandidatesStr = localStorage.getItem(STORAGE_KEY_CANDIDATES)

  if (savedThreadId && savedCandidatesStr) {
    try {
      const stateRes = await getTripPlanState(savedThreadId)
      if (stateRes.success && stateRes.data && stateRes.data.is_interrupted && !stateRes.data.is_completed) {
        const parsedCandidates: PlanCandidateData = JSON.parse(savedCandidatesStr)
        const city = stateRes.data.city || parsedCandidates.city || '目的地'
        const days = stateRes.data.travel_days || parsedCandidates.travel_days || 1

        Modal.confirm({
          title: '发现未完成的旅行规划',
          content: `检测到您之前有正在规划中的【${city}】${days}天行程，是否恢复断点继续挑选？`,
          okText: '恢复规划',
          cancelText: '放弃并新建',
          onOk() {
            candidateData.value = parsedCandidates
            enableHitl.value = true
            const savedAttrs = localStorage.getItem(STORAGE_KEY_SELECTED_ATTRS)
            if (savedAttrs) {
              try {
                selectedAttractions.value = JSON.parse(savedAttrs)
              } catch {
                selectedAttractions.value = parsedCandidates.candidate_attractions.map(a => a.name)
              }
            } else {
              selectedAttractions.value = parsedCandidates.candidate_attractions.map(a => a.name)
            }
            selectedHotel.value = localStorage.getItem(STORAGE_KEY_SELECTED_HOTEL) || (parsedCandidates.candidate_hotels.length > 0 ? parsedCandidates.candidate_hotels[0].name : undefined)
            userFeedback.value = localStorage.getItem(STORAGE_KEY_FEEDBACK) || ''
            hitlModalVisible.value = true
            message.success('已恢复上次未完成的规划现场！')
          },
          onCancel() {
            clearPendingStorage()
          }
        })
      } else {
        clearPendingStorage()
      }
    } catch (e) {
      console.warn('检查未完成规划失败，清理失效缓存', e)
      clearPendingStorage()
    }
  }
})

// 监听用户弹窗中的挑选，实时同步到 LocalStorage
watch(selectedAttractions, (val) => {
  if (hitlModalVisible.value && candidateData.value) {
    localStorage.setItem(STORAGE_KEY_SELECTED_ATTRS, JSON.stringify(val))
  }
}, { deep: true })

watch(selectedHotel, (val) => {
  if (hitlModalVisible.value && candidateData.value && val) {
    localStorage.setItem(STORAGE_KEY_SELECTED_HOTEL, val)
  }
})

watch(userFeedback, (val) => {
  if (hitlModalVisible.value && candidateData.value) {
    localStorage.setItem(STORAGE_KEY_FEEDBACK, val)
  }
})

type TripFormState = Omit<TripFormData, 'start_date' | 'end_date'> & {
  start_date: Dayjs | null
  end_date: Dayjs | null
}

const formData = reactive<TripFormState>({
  city: '',
  start_date: null,
  end_date: null,
  travel_days: 1,
  transportation: '公共交通',
  accommodation: '经济型酒店',
  preferences: [],
  free_text_input: ''
})

// 监听日期变化,自动计算旅行天数
watch([() => formData.start_date, () => formData.end_date], ([start, end]) => {
  if (start && end) {
    const days = end.diff(start, 'day') + 1
    if (days > 0 && days <= 30) {
      formData.travel_days = days
    } else if (days > 30) {
      message.warning('旅行天数不能超过30天')
      formData.end_date = null
    } else {
      message.warning('结束日期不能早于开始日期')
      formData.end_date = null
    }
  }
})

const handleSubmit = async () => {
  if (!formData.start_date || !formData.end_date) {
    message.error('请选择日期')
    return
  }

  loading.value = true
  loadingProgress.value = 5
  loadingStatus.value = '正在启动 LangGraph 多智能体协作...'

  try {
    const requestData: TripFormData = {
      city: formData.city,
      start_date: formData.start_date.format('YYYY-MM-DD'),
      end_date: formData.end_date.format('YYYY-MM-DD'),
      travel_days: formData.travel_days,
      transportation: formData.transportation,
      accommodation: formData.accommodation,
      preferences: formData.preferences,
      free_text_input: formData.free_text_input
    }

    if (enableHitl.value) {
      // 人机协同模式：第一阶段获取候选并挂起
      loadingStatus.value = '正在并行检索景点与酒店候选...'
      loadingProgress.value = 40
      const response = await prepareTripPlan(requestData)
      loading.value = false
      loadingProgress.value = 0
      loadingStatus.value = ''

      if (response.success && response.data) {
        candidateData.value = response.data
        selectedAttractions.value = response.data.candidate_attractions.map(a => a.name)
        selectedHotel.value = response.data.candidate_hotels.length > 0 ? response.data.candidate_hotels[0].name : undefined
        userFeedback.value = ''
        savePendingStorage(response.data)
        hitlModalVisible.value = true
        message.info('候选景点与酒店已检索完成，请在弹窗中挑选确认！')
      } else {
        message.error(response.message || '获取候选数据失败')
      }
      return
    }

    // 全自动模式：使用真实 LangGraph SSE 流式推送
    await generateTripPlanStream(
      requestData,
      (evt: StreamEvent) => {
        const timeSuffix = evt.elapsed_seconds ? ` (${Math.round(evt.elapsed_seconds)}s)` : ''
        if (evt.event === 'node_finish') {
          loadingProgress.value = evt.progress || Math.min(95, loadingProgress.value + 15)
          loadingStatus.value = (evt.message || '多智能体协作中...') + timeSuffix
        } else if (evt.event === 'node_start' || evt.event === 'node_progress') {
          loadingProgress.value = evt.progress || Math.min(92, loadingProgress.value + 3)
          const stagePrefix = evt.stage ? `【${evt.stage}】` : ''
          loadingStatus.value = `${stagePrefix}${evt.message || '多智能体深度推演中...'}${timeSuffix}`
        } else if (evt.event === 'retry') {
          loadingStatus.value = (evt.message || '正在自动重试修复行程...') + timeSuffix
          loadingProgress.value = evt.progress || 75
        } else if (evt.event === 'plan_complete' && evt.data) {
          loadingProgress.value = 100
          loadingStatus.value = '✅ 旅行计划生成成功!' + timeSuffix
          sessionStorage.setItem('tripPlan', JSON.stringify(evt.data))
          message.success('旅行计划生成成功!')
          setTimeout(() => {
            router.push('/result')
          }, 400)
        } else if (evt.event === 'error') {
          message.error(evt.message || '生成旅行计划出现异常')
          loading.value = false
        }
      },
      (err: any) => {
        message.error(err.message || '流式连接发生错误')
        loading.value = false
      }
    )
  } catch (error: any) {
    message.error(error.message || '生成旅行计划失败,请稍后重试')
    loading.value = false
  }
}


const handleConfirmHitl = async () => {
  if (!candidateData.value) return
  confirming.value = true
  try {
    const response = await confirmTripPlan({
      thread_id: candidateData.value.thread_id,
      selected_attractions: selectedAttractions.value,
      selected_hotel: selectedHotel.value,
      user_feedback: userFeedback.value
    })
    if (response.success && response.data) {
      clearPendingStorage()
      sessionStorage.setItem('tripPlan', JSON.stringify(response.data))
      message.success('人机协同行程规划完成!')
      hitlModalVisible.value = false
      setTimeout(() => {
        router.push('/result')
      }, 500)
    } else {
      message.error(response.message || '生成旅行计划失败')
    }
  } catch (error: any) {
    message.error(error.message || '确认生成失败')
  } finally {
    confirming.value = false
  }
}

const handleCancelHitl = () => {
  hitlModalVisible.value = false
  candidateData.value = null
  clearPendingStorage()
  message.info('已取消本次人机协同规划')
}
</script>

<style scoped>
.home-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 60px 20px;
  position: relative;
  overflow: hidden;
}

/* 背景装饰 */
.bg-decoration {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: hidden;
}

.circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  animation: float 20s infinite ease-in-out;
}

.circle-1 {
  width: 300px;
  height: 300px;
  top: -100px;
  left: -100px;
  animation-delay: 0s;
}

.circle-2 {
  width: 200px;
  height: 200px;
  top: 50%;
  right: -50px;
  animation-delay: 5s;
}

.circle-3 {
  width: 150px;
  height: 150px;
  bottom: -50px;
  left: 30%;
  animation-delay: 10s;
}

@keyframes float {
  0%, 100% {
    transform: translateY(0) rotate(0deg);
  }
  50% {
    transform: translateY(-30px) rotate(180deg);
  }
}

/* 页面标题 */
.page-header {
  text-align: center;
  margin-bottom: 50px;
  animation: fadeInDown 0.8s ease-out;
  position: relative;
  z-index: 1;
}

.icon-wrapper {
  margin-bottom: 20px;
}

.icon {
  font-size: 80px;
  display: inline-block;
  animation: bounce 2s infinite;
}

@keyframes bounce {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-20px);
  }
}

.page-title {
  font-size: 56px;
  font-weight: 800;
  color: #ffffff;
  margin-bottom: 16px;
  text-shadow: 3px 3px 6px rgba(0, 0, 0, 0.3);
  letter-spacing: 2px;
}

.page-subtitle {
  font-size: 20px;
  color: rgba(255, 255, 255, 0.95);
  margin: 0;
  font-weight: 300;
}

/* 表单卡片 */
.form-card {
  max-width: 1400px;
  margin: 0 auto;
  border-radius: 24px;
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.4);
  animation: fadeInUp 0.8s ease-out;
  position: relative;
  z-index: 1;
  backdrop-filter: blur(10px);
  background: rgba(255, 255, 255, 0.98) !important;
}

/* 表单分区 */
.form-section {
  margin-bottom: 32px;
  padding: 24px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 16px;
  border: 1px solid #e8e8e8;
  transition: all 0.3s ease;
}

.form-section:hover {
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.15);
  transform: translateY(-2px);
}

.section-header {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 2px solid #667eea;
}

.section-icon {
  font-size: 24px;
  margin-right: 12px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

/* 表单标签 */
.form-label {
  font-size: 15px;
  font-weight: 500;
  color: #555;
}

/* 自定义输入框 */
.custom-input :deep(.ant-input),
.custom-input :deep(.ant-picker) {
  border-radius: 12px;
  border: 2px solid #e8e8e8;
  transition: all 0.3s ease;
}

.custom-input :deep(.ant-input:hover),
.custom-input :deep(.ant-picker:hover) {
  border-color: #667eea;
}

.custom-input :deep(.ant-input:focus),
.custom-input :deep(.ant-picker-focused) {
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

/* 自定义选择框 */
.custom-select :deep(.ant-select-selector) {
  border-radius: 12px !important;
  border: 2px solid #e8e8e8 !important;
  transition: all 0.3s ease;
}

.custom-select:hover :deep(.ant-select-selector) {
  border-color: #667eea !important;
}

.custom-select :deep(.ant-select-focused .ant-select-selector) {
  border-color: #667eea !important;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1) !important;
}

/* 天数显示 - 紧凑版 */
.days-display-compact {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  color: white;
}

.days-display-compact .days-value {
  font-size: 24px;
  font-weight: 700;
  margin-right: 4px;
}

.days-display-compact .days-unit {
  font-size: 14px;
}

/* 偏好标签 */
.preference-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.custom-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
}

.preference-tag :deep(.ant-checkbox-wrapper) {
  margin: 0 !important;
  padding: 8px 16px;
  border: 2px solid #e8e8e8;
  border-radius: 20px;
  transition: all 0.3s ease;
  background: white;
  font-size: 14px;
}

.preference-tag :deep(.ant-checkbox-wrapper:hover) {
  border-color: #667eea;
  background: #f5f7ff;
}

.preference-tag :deep(.ant-checkbox-wrapper-checked) {
  border-color: #667eea;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

/* 自定义文本域 */
.custom-textarea :deep(.ant-input) {
  border-radius: 12px;
  border: 2px solid #e8e8e8;
  transition: all 0.3s ease;
}

.custom-textarea :deep(.ant-input:hover) {
  border-color: #667eea;
}

.custom-textarea :deep(.ant-input:focus) {
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

/* 提交按钮 */
.submit-button {
  height: 56px;
  border-radius: 28px;
  font-size: 18px;
  font-weight: 600;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  box-shadow: 0 8px 24px rgba(102, 126, 234, 0.4);
  transition: all 0.3s ease;
}

.submit-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(102, 126, 234, 0.5);
}

.submit-button:active {
  transform: translateY(0);
}

.button-icon {
  margin-right: 8px;
  font-size: 20px;
}

/* 加载容器 */
.loading-container {
  text-align: center;
  padding: 24px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 16px;
  border: 2px dashed #667eea;
}

.loading-status {
  margin-top: 16px;
  color: #667eea;
  font-size: 18px;
  font-weight: 500;
}

/* 动画 */
@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
/* Human-in-the-Loop 交互样式 */
.hitl-switch-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  margin-bottom: 24px;
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.08) 0%, rgba(118, 75, 162, 0.08) 100%);
  border: 1.5px solid rgba(102, 126, 234, 0.25);
  border-radius: 12px;
  transition: all 0.3s;
}

.hitl-switch-card:hover {
  border-color: #667eea;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
}

.hitl-switch-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.hitl-switch-icon {
  font-size: 24px;
}

.hitl-switch-title {
  font-weight: 600;
  font-size: 15px;
  color: #2d3748;
}

.hitl-switch-desc {
  font-size: 13px;
  color: #718096;
}

.hitl-modal-body {
  max-height: 60vh;
  overflow-y: auto;
  padding-right: 4px;
}

.hitl-field-label {
  font-weight: 600;
  font-size: 14px;
  color: #2d3748;
  margin-bottom: 8px;
}

.hitl-poi-scroll {
  max-height: 220px;
  overflow-y: auto;
  padding: 8px;
  border: 1px solid #edf2f7;
  border-radius: 8px;
  background: #fafafa;
}

.poi-select-card {
  background: #ffffff;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  height: 100%;
  transition: all 0.2s ease;
  cursor: pointer;
}

.poi-select-card:hover {
  border-color: #cbd5e1;
}

.poi-select-card.card-selected {
  border-color: #667eea;
  background: #f7f9fe;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.08);
}

/* 保证 Ant Design 的 checkbox 和 radio 居顶对齐且内容铺满 */
:deep(.poi-checkbox.ant-checkbox-wrapper),
:deep(.hotel-radio.ant-radio-wrapper) {
  display: flex;
  align-items: flex-start;
  width: 100%;
  margin-right: 0;
}

:deep(.poi-checkbox .ant-checkbox),
:deep(.hotel-radio .ant-radio) {
  margin-top: 3px;
  flex-shrink: 0;
}

:deep(.poi-checkbox > span:last-child),
:deep(.hotel-radio > span:last-child) {
  flex: 1;
  min-width: 0;
  padding-left: 8px;
}

.poi-info-content,
.hotel-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
  width: 100%;
}

.poi-name {
  display: block;
  font-weight: 600;
  font-size: 13px;
  color: #2d3748;
  line-height: 1.4;
}

.hotel-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.poi-addr {
  display: block;
  font-size: 12px;
  color: #a0aec0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}

.hotel-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.hotel-price-badge {
  font-size: 11px;
  font-weight: 600;
  color: #e53e3e;
  background: #fff5f5;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid #fed7d7;
  white-space: nowrap;
  flex-shrink: 0;
}

.hotel-meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 4px 0 2px 0;
  flex-wrap: nowrap;
  overflow: hidden;
}

.hotel-rating {
  font-size: 11px;
  color: #d69e2e;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.hotel-distance {
  font-size: 11px;
  color: #4a5568;
  background: #edf2f7;
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
  flex-shrink: 1;
}
</style>

