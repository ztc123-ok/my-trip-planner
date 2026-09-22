<template>
  <div class="result-container">
    <!-- 页面头部 -->
    <div class="page-header">
      <a-button class="back-button" size="large" @click="goBack">
        ← 返回首页
      </a-button>
      <a-space size="middle">
        <a-button type="primary" @click="chatDrawerVisible = true">
          💬 AI 对话调整行程
        </a-button>


        <a-button v-if="!editMode" @click="toggleEditMode" type="default">
          ✏️ 编辑行程
        </a-button>
        <a-button v-else @click="saveChanges" type="primary">
          💾 保存修改
        </a-button>
        <a-button v-if="editMode" @click="cancelEdit" type="default">
          ❌ 取消编辑
        </a-button>

        <!-- 导出按钮 -->
        <a-dropdown v-if="!editMode">
          <template #overlay>
            <a-menu>
              <a-menu-item key="image" @click="exportAsImage">
                📷 导出为图片
              </a-menu-item>
              <a-menu-item key="pdf" @click="exportAsPDF">
                📄 导出为PDF
              </a-menu-item>
            </a-menu>
          </template>
          <a-button type="default">
            📥 导出行程 <DownOutlined />
          </a-button>
        </a-dropdown>

      </a-space>
    </div>

    <div v-if="tripPlan" class="content-wrapper">
      <!-- 侧边导航 -->
      <div class="side-nav">
        <a-affix :offset-top="80">
          <a-menu mode="inline" :selected-keys="[activeSection]" @click="scrollToSection">
            <a-menu-item key="overview">
              <span>📋 行程概览</span>
            </a-menu-item>
            <a-menu-item key="budget" v-if="tripPlan.budget">
              <span>💰 预算明细</span>
            </a-menu-item>
            <a-menu-item key="evaluation">
              <span>🎯 质量质检</span>
            </a-menu-item>
            <a-menu-item key="map">
              <span>📍 景点地图</span>
            </a-menu-item>
            <a-sub-menu key="days" title="📅 每日行程">
              <a-menu-item v-for="(day, index) in tripPlan.days" :key="`day-${index}`">
                第{{ day.day_index + 1 }}天
              </a-menu-item>
            </a-sub-menu>
            <a-menu-item key="weather">
              <span>🌤️ 天气信息</span>
            </a-menu-item>
          </a-menu>
        </a-affix>
      </div>

      <!-- 主内容区 -->
      <div class="main-content">
        <!-- 顶部信息区:左侧概览+预算,右侧地图 -->
        <div class="top-info-section">
          <!-- 左侧:行程概览和预算明细 -->
          <div class="left-info">
            <!-- 行程概览 -->
            <a-card id="overview" :title="`${tripPlan.city}旅行计划`" :bordered="false" class="overview-card">
              <template #extra>
                <div v-if="evalReport" class="overview-score-chip" :class="scoreColorClass">
                  <span class="osc-icon">🎯</span>
                  <span class="osc-score">{{ evalReport.overall_score }}分</span>
                  <span class="osc-grade">{{ evalReport.grade.split(' ')[0] }}</span>
                </div>
              </template>
              <div class="overview-content">
                <div class="info-item">
                  <span class="info-label">📅 日期:</span>
                  <span class="info-value">{{ tripPlan.start_date }} 至 {{ tripPlan.end_date }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">💡 建议:</span>
                  <span class="info-value">{{ tripPlan.overall_suggestions }}</span>
                </div>
                <div v-if="tripPlan.knowledge_highlights && tripPlan.knowledge_highlights.length" class="info-item knowledge-box">
                  <span class="info-label">🏛️ 权威攻略速记:</span>
                  <div class="knowledge-tags">
                    <div v-for="(tip, kIdx) in tripPlan.knowledge_highlights" :key="kIdx" class="knowledge-tag-item">
                      {{ tip }}
                    </div>
                  </div>
                </div>
              </div>
            </a-card>

            <!-- 预算明细 -->
            <a-card id="budget" v-if="tripPlan.budget" title="💰 预算明细" :bordered="false" class="budget-card">
              <div class="budget-grid">
                <div class="budget-item">
                  <div class="budget-label">景点门票</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_attractions }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">酒店住宿</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_hotels }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">餐饮费用</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_meals }}</div>
                </div>
                <div class="budget-item">
                  <div class="budget-label">交通费用</div>
                  <div class="budget-value">¥{{ tripPlan.budget.total_transportation }}</div>
                </div>
              </div>
              <div class="budget-total">
                <span class="total-label">预估总费用</span>
                <span class="total-value">¥{{ tripPlan.budget.total }}</span>
              </div>
            </a-card>
          </div>

          <!-- 右侧:地图 -->
          <div class="right-map">
            <a-card id="map" title="📍 景点地图" :bordered="false" class="map-card">
              <div class="map-surface">
                <div id="amap-container"></div>
                <div v-if="mapStatus" class="map-status">{{ mapStatus }}</div>
              </div>
            </a-card>
          </div>
        </div>

        <!-- 行程质量与多维评估报告 (Phase 6) -->
        <a-card id="evaluation" title="🎯 智能体全方位质量质检报告" :bordered="false" class="eval-card">
          <template #extra>
            <a-space>
              <a-tag :color="observabilityStatus?.tracing_enabled ? 'cyan' : 'default'">
                {{ observabilityStatus?.tracing_enabled ? '🔍 LangSmith Tracing 已激活' : '🔍 多维工程质检' }}
              </a-tag>
              <a-button size="small" :loading="evalLoading" @click="fetchEvaluation(true)">
                🔄 重新质检
              </a-button>
            </a-space>
          </template>

          <div v-if="evalReport" class="eval-body">
            <div class="eval-score-banner">
              <div class="score-circle-box">
                <div class="score-num" :class="scoreColorClass">{{ evalReport.overall_score }}</div>
                <div class="score-label">综合质量分</div>
              </div>
              <div class="score-meta-box">
                <div class="grade-title">
                  <span class="grade-tag" :class="scoreColorClass">{{ evalReport.grade }}</span>
                  <span class="grade-sub">经完整性、空间动线合理性、预算严密性三大维度量化核验</span>
                </div>
                <div class="metrics-row">
                  <div class="m-pill">
                    <span class="m-k">动线总里程:</span>
                    <span class="m-v">{{ evalReport.metrics?.total_route_distance_km || 0 }} km</span>
                  </div>
                  <div class="m-pill">
                    <span class="m-k">最大单段跨度:</span>
                    <span class="m-v">{{ evalReport.metrics?.max_single_leg_km || 0 }} km</span>
                  </div>
                  <div class="m-pill">
                    <span class="m-k">预算算术校验:</span>
                    <span class="m-v">{{ evalReport.metrics?.budget_arithmetic_valid ? '✅ 严格一致' : '⚠️ 存在差额' }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 三大维度进度条 -->
            <div class="eval-dimensions-grid">
              <div class="dim-card" v-for="(dim, key) in evalReport.dimensions" :key="key">
                <div class="dim-head">
                  <span class="dim-name">{{ dim.dimension_name }}</span>
                  <span class="dim-score">{{ dim.score }} 分</span>
                </div>
                <a-progress
                  :percent="dim.score"
                  :status="dim.score >= 85 ? 'success' : dim.score >= 60 ? 'normal' : 'exception'"
                  :stroke-color="dim.score >= 85 ? '#52c41a' : dim.score >= 60 ? '#1890ff' : '#ff4d4f'"
                />
                <div class="dim-weight">权重: {{ (dim.weight * 100).toFixed(0) }}% · {{ dim.passed ? '达标' : '待优化' }}</div>
              </div>
            </div>

            <!-- 优化建议与提示 -->
            <div v-if="evalReport.suggestions && evalReport.suggestions.length" class="eval-suggestions-box">
              <div class="sugg-title">💡 智能质检诊断与建议：</div>
              <ul class="sugg-list">
                <li v-for="(sugg, sIdx) in evalReport.suggestions" :key="sIdx">
                  {{ sugg }}
                </li>
              </ul>
            </div>
          </div>
          <div v-else-if="evalLoading" class="eval-loading-box">
            <a-spin tip="正在对规划结果执行完整性、地理空间动线与预算严密性多维质检..." />
          </div>
        </a-card>

        <!-- 每日行程:可折叠 -->
        <a-card title="📅 每日行程" :bordered="false" class="days-card">
          <a-collapse v-model:activeKey="activeDays" accordion>
            <a-collapse-panel
              v-for="(day, index) in tripPlan.days"
              :key="index"
              :id="`day-${index}`"
            >
              <template #header>
                <div class="day-header">
                  <span class="day-title">第{{ day.day_index + 1 }}天</span>
                  <span class="day-date">{{ day.date }}</span>
                </div>
              </template>

              <!-- 行程基本信息 -->
              <div class="day-info">
                <div class="info-row">
                  <span class="label">📝 行程描述:</span>
                  <span class="value">{{ day.description }}</span>
                </div>
                <div class="info-row">
                  <span class="label">🚗 交通方式:</span>
                  <span class="value">{{ day.transportation }}</span>
                </div>
                <div class="info-row">
                  <span class="label">🏨 住宿:</span>
                  <span class="value">{{ day.accommodation }}</span>
                </div>
              </div>

              <!-- 景点安排 -->
              <a-divider orientation="left">🎯 景点安排</a-divider>
              <a-list
                :data-source="day.attractions"
                :grid="{ gutter: 16, column: 2 }"
              >
                <template #renderItem="{ item, index }">
                  <a-list-item>
                    <a-card :title="item.name" size="small" class="attraction-card">
                      <!-- 编辑模式下的操作按钮 -->
                      <template #extra v-if="editMode">
                        <a-space>
                          <a-button
                            size="small"
                            @click="moveAttraction(day.day_index, index, 'up')"
                            :disabled="index === 0"
                          >
                            ↑
                          </a-button>
                          <a-button
                            size="small"
                            @click="moveAttraction(day.day_index, index, 'down')"
                            :disabled="index === day.attractions.length - 1"
                          >
                            ↓
                          </a-button>
                          <a-button
                            size="small"
                            danger
                            @click="deleteAttraction(day.day_index, index)"
                          >
                            🗑️
                          </a-button>
                        </a-space>
                      </template>

                      <!-- 景点图片 -->
                      <div class="attraction-image-wrapper">
                        <img
                          :src="getAttractionImage(item.name, index)"
                          :alt="item.name"
                          class="attraction-image"
                          @error="handleImageError"
                        />
                        <div class="attraction-badge">
                          <span class="badge-number">{{ index + 1 }}</span>
                        </div>
                        <div v-if="item.ticket_price" class="price-tag">
                          ¥{{ item.ticket_price }}
                        </div>
                      </div>

                      <!-- 编辑模式下可编辑的字段 -->
                      <div v-if="editMode">
                        <p><strong>地址:</strong></p>
                        <a-input v-model:value="item.address" size="small" style="margin-bottom: 8px" />

                        <p><strong>游览时长(分钟):</strong></p>
                        <a-input-number v-model:value="item.visit_duration" :min="10" :max="480" size="small" style="width: 100%; margin-bottom: 8px" />

                        <p><strong>描述:</strong></p>
                        <a-textarea v-model:value="item.description" :rows="2" size="small" style="margin-bottom: 8px" />
                      </div>

                      <!-- 查看模式 -->
                      <div v-else>
                        <p><strong>地址:</strong> {{ item.address }}</p>
                        <p><strong>游览时长:</strong> {{ item.visit_duration }}分钟</p>
                        <p><strong>描述:</strong> {{ item.description }}</p>
                        <p v-if="item.rating"><strong>评分:</strong> {{ item.rating }}⭐</p>

                        <!-- RAG 知识库增强: 预约须知与避坑贴士 -->
                        <div v-if="item.booking_tips" class="rag-tip-box booking-box">
                          <span class="rag-badge booking">📌 预约须知</span>
                          <span class="rag-text">{{ item.booking_tips }}</span>
                        </div>
                        <div v-if="item.tips" class="rag-tip-box advice-box">
                          <span class="rag-badge advice">💡 避坑贴士</span>
                          <span class="rag-text">{{ item.tips }}</span>
                        </div>
                      </div>
                    </a-card>
                  </a-list-item>
                </template>
              </a-list>

              <!-- 酒店推荐 -->
              <a-divider v-if="day.hotel" orientation="left">🏨 住宿推荐</a-divider>
              <a-card v-if="day.hotel" size="small" class="hotel-card">
                <template #title>
                  <span class="hotel-title">{{ day.hotel.name }}</span>
                </template>
                <a-descriptions :column="2" size="small">
                  <a-descriptions-item label="地址">{{ day.hotel.address }}</a-descriptions-item>
                  <a-descriptions-item label="类型">{{ day.hotel.type }}</a-descriptions-item>
                  <a-descriptions-item label="价格范围">{{ day.hotel.price_range }}</a-descriptions-item>
                  <a-descriptions-item label="评分">{{ day.hotel.rating }}⭐</a-descriptions-item>
                  <a-descriptions-item label="距离" :span="2">{{ day.hotel.distance }}</a-descriptions-item>
                </a-descriptions>
              </a-card>

              <!-- 餐饮安排 -->
              <a-divider orientation="left">🍽️ 餐饮安排</a-divider>
              <a-descriptions :column="1" bordered size="small">
                <a-descriptions-item
                  v-for="meal in day.meals"
                  :key="meal.type"
                  :label="getMealLabel(meal.type)"
                >
                  {{ meal.name }}
                  <span v-if="meal.description"> - {{ meal.description }}</span>
                </a-descriptions-item>
              </a-descriptions>
            </a-collapse-panel>
          </a-collapse>
        </a-card>

        <a-card id="weather" title="天气信息" style="margin-top: 20px" :bordered="false">
        <a-alert
          v-if="missingWeatherDates.length > 0"
          type="info"
          show-icon
          :message="`当前仅显示行程日期内已有的天气预报；${missingWeatherDates.join('、')} 暂无预报，请临行前再查询。`"
          style="margin-bottom: 16px"
        />
        <a-list
          v-if="tripPlan.weather_info && tripPlan.weather_info.length > 0"
          :data-source="tripPlan.weather_info"
          :grid="{ gutter: 16, column: 3 }"
        >
          <template #renderItem="{ item }">
            <a-list-item>
              <a-card size="small" class="weather-card">
                <div class="weather-date">{{ item.date }}</div>
                <div v-if="item.source" class="weather-source">来源：{{ item.source }}</div>
                <div class="weather-info-row">
                  <span class="weather-icon">☀️</span>
                  <div>
                    <div class="weather-label">{{ item.source === 'Open-Meteo' ? '最高' : '白天' }}</div>
                    <div class="weather-value">{{ item.day_weather }} {{ item.day_temp }}°C</div>
                  </div>
                </div>
                <div class="weather-info-row">
                  <span class="weather-icon">🌙</span>
                  <div>
                    <div class="weather-label">{{ item.source === 'Open-Meteo' ? '最低' : '夜间' }}</div>
                    <div class="weather-value">{{ item.night_weather }} {{ item.night_temp }}°C</div>
                  </div>
                </div>
                <div v-if="item.wind_direction || item.wind_power" class="weather-wind">
                  💨 {{ item.wind_direction }} {{ item.wind_power }}
                </div>
              </a-card>
            </a-list-item>
          </template>
        </a-list>
        <a-empty v-else description="行程日期暂无可用天气预报" />
        </a-card>
      </div>
    </div>

    <a-empty v-else description="没有找到旅行计划数据">
      <template #image>
        <div style="font-size: 80px;">🗺️</div>
      </template>
      <template #description>
        <span style="color: #999;">暂无旅行计划数据,请先创建行程</span>
      </template>
      <a-button type="primary" @click="goBack">返回首页创建行程</a-button>
    </a-empty>

    <!-- 悬浮 AI 对话调整入口 -->
    <div class="floating-chat-trigger" @click="chatDrawerVisible = true" title="点击展开 AI 行程小助手">
      <span class="trigger-icon">💬</span>
      <span class="trigger-text">AI 对话调整</span>
    </div>

    <!-- AI 对话调整抽屉 -->
    <a-drawer
      v-model:open="chatDrawerVisible"
      title="🤖 AI 对话调整行程 (LangGraph 子图)"
      placement="right"
      width="440px"
      :body-style="{ display: 'flex', flexDirection: 'column', height: 'calc(100% - 55px)', padding: '16px' }"
    >
      <!-- 快捷调整标签 -->
      <div class="drawer-chips-wrap">
        <div class="chips-title">💡 常见调整指令：</div>
        <div class="chips-row">
          <button
            v-for="chip in drawerQuickChips"
            :key="chip"
            class="drawer-chip-btn"
            @click="chatInput = chip; sendDrawerChat()"
          >
            {{ chip }}
          </button>
        </div>
      </div>

      <!-- 对话消息列表 -->
      <div class="drawer-messages" ref="drawerMsgContainer">
        <div
          v-for="(msg, idx) in chatMessages"
          :key="idx"
          class="d-msg-row"
          :class="msg.role"
        >
          <div class="d-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
          <div class="d-bubble">
            <div class="d-bubble-content">{{ msg.content }}</div>
            <div class="d-bubble-eval" v-if="msg.evaluation">
              <span class="d-eval-tag">🎯 行程质检分: <strong>{{ msg.evaluation.overall_score }}分</strong> ({{ msg.evaluation.grade.split(' ')[0] }})</span>
            </div>
            <div class="d-bubble-time">{{ msg.time }}</div>
          </div>
        </div>
        <div v-if="chatLoading" class="d-msg-row assistant">
          <div class="d-avatar">🤖</div>
          <div class="d-bubble loading">
            <span>正在分析并更新行程中...</span>
          </div>
        </div>
      </div>

      <!-- 抽屉底部输入区 -->
      <div class="drawer-input-box">
        <a-textarea
          v-model:value="chatInput"
          placeholder="输入您的修改想法，如：把第2天的故宫换成颐和园..."
          :auto-size="{ minRows: 2, maxRows: 4 }"
          @keydown.enter.exact.prevent="sendDrawerChat"
        />
        <div class="drawer-input-footer">
          <span class="d-hint">Enter 发送 / Shift+Enter 换行</span>
          <a-button type="primary" :loading="chatLoading" @click="sendDrawerChat">
            发送指令
          </a-button>
        </div>
      </div>
    </a-drawer>

    <!-- 回到顶部按钮 -->
    <a-back-top :visibility-height="300">
      <div class="back-top-button">
        ↑
      </div>
    </a-back-top>
  </div>
</template>


<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { DownOutlined } from '@ant-design/icons-vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import dayjs from 'dayjs'
import type { Attraction, TripPlan, EvaluationReport, ObservabilityStatus } from '@/types'
import { getAttractionPhoto, chatModifyTripPlan, evaluateTripPlan, getObservabilityStatus } from '@/services/api'

const router = useRouter()
const tripPlan = ref<TripPlan | null>(null)
const editMode = ref(false)
const originalPlan = ref<TripPlan | null>(null)
const attractionPhotos = ref<Record<string, string>>({})
const activeSection = ref('overview')
const activeDays = ref<number[]>([0]) // 默认展开第一天

// AI 对话调整抽屉状态
const chatDrawerVisible = ref(false)
const chatInput = ref('')
const chatLoading = ref(false)
const drawerMsgContainer = ref<HTMLElement | null>(null)
const chatMessages = ref<Array<{ role: 'user' | 'assistant'; content: string; time: string; evaluation?: EvaluationReport }>>([
  {
    role: 'assistant',
    content: '您好！我是您的 AI 行程小助手。您可以随时告诉我如何调整当前行程，比如：“把第2天的故宫换成颐和园”、“预算控制在3000以内”、“推荐一家特色素食餐厅”。',
    time: '刚刚'
  }
])
const drawerQuickChips = [
  '把第2天的一个景点换成更小众的',
  '帮我推荐一家特色地道午餐',
  '预算降低 500 元',
  '行程太赶了，每天减少一个景点'
]

// 行程质量与多维评估状态 (Phase 6)
const evalReport = ref<EvaluationReport | null>(null)
const evalLoading = ref(false)
const observabilityStatus = ref<ObservabilityStatus | null>(null)

const scoreColorClass = computed(() => {
  const s = evalReport.value?.overall_score || 0
  if (s >= 90) return 'score-excellent'
  if (s >= 75) return 'score-good'
  if (s >= 60) return 'score-pass'
  return 'score-poor'
})

const fetchEvaluation = async (_force = false) => {
  if (!tripPlan.value) return
  evalLoading.value = true
  try {
    const threadId = sessionStorage.getItem('tripPlanThreadId') || undefined
    evalReport.value = await evaluateTripPlan(tripPlan.value, threadId)
  } catch (err: any) {
    console.error('获取行程评估失败:', err)
  } finally {
    evalLoading.value = false
  }
}

const fetchObservabilityStatus = async () => {
  try {
    observabilityStatus.value = await getObservabilityStatus()
  } catch (err) {
    console.error('获取可观测性状态失败:', err)
  }
}

const sendDrawerChat = async () => {
  const text = chatInput.value.trim()
  if (!text || chatLoading.value || !tripPlan.value) return
  chatInput.value = ''

  chatMessages.value.push({
    role: 'user',
    content: text,
    time: dayjs().format('HH:mm')
  })
  chatLoading.value = true

  nextTick(() => {
    if (drawerMsgContainer.value) drawerMsgContainer.value.scrollTop = drawerMsgContainer.value.scrollHeight
  })

  try {
    const res = await chatModifyTripPlan({
      message: text,
      trip_plan: tripPlan.value,
      chat_history: chatMessages.value.map(m => ({ role: m.role, content: m.content }))
    })

    if (res.success && res.data) {
      if (res.data.evaluation) {
        evalReport.value = res.data.evaluation
      }
      chatMessages.value.push({
        role: 'assistant',
        content: res.data.reply + (res.data.changes_summary ? `\n（✨ ${res.data.changes_summary}）` : ''),
        time: dayjs().format('HH:mm'),
        evaluation: res.data.evaluation,
      })

      if (res.data.updated_plan && res.data.modified) {
        tripPlan.value = res.data.updated_plan
        sessionStorage.setItem('tripPlan', JSON.stringify(res.data.updated_plan))
        message.success('行程与地图已联动更新！')
        if (!res.data.evaluation) {
          void fetchEvaluation()
        }
        nextTick(() => {
          void initMap()
        })
      }
    } else {
      chatMessages.value.push({
        role: 'assistant',
        content: res.message || '未能完成调整',
        time: dayjs().format('HH:mm')
      })
    }
  } catch (err: any) {
    chatMessages.value.push({
      role: 'assistant',
      content: `调整失败: ${err.message || err}`,
      time: dayjs().format('HH:mm')
    })
  } finally {
    chatLoading.value = false
    nextTick(() => {
      if (drawerMsgContainer.value) drawerMsgContainer.value.scrollTop = drawerMsgContainer.value.scrollHeight
    })
  }
}

const missingWeatherDates = computed(() => {
  if (!tripPlan.value) return []

  const forecastDates = new Set((tripPlan.value.weather_info ?? []).map(item => item.date))
  const missingDates: string[] = []
  const end = dayjs(tripPlan.value.end_date)
  for (let date = dayjs(tripPlan.value.start_date); date.isValid() && !date.isAfter(end, 'day'); date = date.add(1, 'day')) {
    const value = date.format('YYYY-MM-DD')
    if (!forecastDates.has(value)) missingDates.push(value)
  }
  return missingDates
})
let map: any = null
let mapProvider: 'amap' | 'leaflet' | null = null
let mapGeneration = 0
const mapStatus = ref('地图加载中…')

onMounted(async () => {
  const data = sessionStorage.getItem('tripPlan')
  if (data) {
    tripPlan.value = JSON.parse(data)
    // 地图先渲染，景点图片请求不阻塞地图初始化。
    await nextTick()
    void initMap()
    void loadAttractionPhotos()
    void fetchEvaluation()
    void fetchObservabilityStatus()
  }
})

onUnmounted(() => {
  mapGeneration += 1
  destroyMap()
})

const goBack = () => {
  router.push('/')
}

// 滚动到指定区域
const scrollToSection = ({ key }: { key: string }) => {
  activeSection.value = key
  const element = document.getElementById(key)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

// 切换编辑模式
const toggleEditMode = () => {
  editMode.value = true
  // 保存原始数据用于取消编辑
  originalPlan.value = JSON.parse(JSON.stringify(tripPlan.value))
  message.info('进入编辑模式')
}

// 保存修改
const saveChanges = () => {
  editMode.value = false
  // 更新sessionStorage
  if (tripPlan.value) {
    if (tripPlan.value.budget) {
      const budget = tripPlan.value.budget
      budget.total_attractions = tripPlan.value.days.reduce(
        (sum, day) => sum + day.attractions.reduce(
          (daySum, attraction) => daySum + (attraction.ticket_price || 0), 0
        ), 0
      )
      budget.total = budget.total_attractions + budget.total_hotels +
        budget.total_meals + budget.total_transportation
    }
    sessionStorage.setItem('tripPlan', JSON.stringify(tripPlan.value))
  }
  message.success('修改已保存')
  void fetchEvaluation()

  // 重新初始化地图以反映更改
  nextTick(() => {
    void initMap()
  })
}

// 取消编辑
const cancelEdit = () => {
  if (originalPlan.value) {
    tripPlan.value = JSON.parse(JSON.stringify(originalPlan.value))
  }
  editMode.value = false
  message.info('已取消编辑')
}

// 删除景点
const deleteAttraction = (dayIndex: number, attrIndex: number) => {
  if (!tripPlan.value) return

  const day = tripPlan.value.days[dayIndex]
  if (day.attractions.length <= 1) {
    message.warning('每天至少需要保留一个景点')
    return
  }

  day.attractions.splice(attrIndex, 1)
  message.success('景点已删除')
}

// 移动景点顺序
const moveAttraction = (dayIndex: number, attrIndex: number, direction: 'up' | 'down') => {
  if (!tripPlan.value) return

  const day = tripPlan.value.days[dayIndex]
  const attractions = day.attractions

  if (direction === 'up' && attrIndex > 0) {
    [attractions[attrIndex], attractions[attrIndex - 1]] = [attractions[attrIndex - 1], attractions[attrIndex]]
  } else if (direction === 'down' && attrIndex < attractions.length - 1) {
    [attractions[attrIndex], attractions[attrIndex + 1]] = [attractions[attrIndex + 1], attractions[attrIndex]]
  }
}

const getMealLabel = (type: string): string => {
  const labels: Record<string, string> = {
    breakfast: '早餐',
    lunch: '午餐',
    dinner: '晚餐',
    snack: '小吃'
  }
  return labels[type] || type
}

// 加载所有景点图片
const loadAttractionPhotos = async () => {
  if (!tripPlan.value) return

  const promises: Promise<void>[] = []
  const city = tripPlan.value.city

  tripPlan.value.days.forEach(day => {
    day.attractions.forEach(attraction => {
      const promise = getAttractionPhoto(attraction.name, city)
        .then(url => {
          if (url) {
            attractionPhotos.value[attraction.name] = url
          }
        })
        .catch(err => {
          console.error(`获取${attraction.name}图片失败:`, err)
        })

      promises.push(promise)
    })
  })

  await Promise.all(promises)
}

// 获取景点图片
const getAttractionImage = (name: string, index: number): string => {
  // 如果已加载真实图片,返回真实图片
  if (attractionPhotos.value[name]) {
    return attractionPhotos.value[name]
  }

  // 返回一个纯色占位图(避免跨域问题)
  const colors = [
    { start: '#667eea', end: '#764ba2' },
    { start: '#f093fb', end: '#f5576c' },
    { start: '#4facfe', end: '#00f2fe' },
    { start: '#43e97b', end: '#38f9d7' },
    { start: '#fa709a', end: '#fee140' }
  ]
  const colorIndex = index % colors.length
  const { start, end } = colors[colorIndex]

  // 使用base64编码避免中文问题
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
    <defs>
      <linearGradient id="grad${index}" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style="stop-color:${start};stop-opacity:1" />
        <stop offset="100%" style="stop-color:${end};stop-opacity:1" />
      </linearGradient>
    </defs>
    <rect width="400" height="300" fill="url(#grad${index})"/>
    <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="24" font-weight="bold" fill="white">${name}</text>
  </svg>`

  return `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`
}

// 图片加载失败时的处理
const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  // 使用灰色占位图
  img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="300"%3E%3Crect width="400" height="300" fill="%23f0f0f0"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="18" fill="%23999"%3E图片加载失败%3C/text%3E%3C/svg%3E'
}



// 导出为图片
const exportAsImage = async () => {
  try {
    message.loading({ content: '正在生成图片...', key: 'export', duration: 0 })

    const element = document.querySelector('.main-content') as HTMLElement
    if (!element) {
      throw new Error('未找到内容元素')
    }

    // 创建一个独立的容器
    const exportContainer = document.createElement('div')
    exportContainer.style.width = element.offsetWidth + 'px'
    exportContainer.style.backgroundColor = '#f5f7fa'
    exportContainer.style.padding = '20px'

    // 复制所有内容
    exportContainer.innerHTML = element.innerHTML

    // 处理地图截图
    const mapContainer = document.getElementById('amap-container')
    if (mapContainer && map) {
      const mapCanvas = mapContainer.querySelector('canvas')
      if (mapCanvas) {
        const mapSnapshot = mapCanvas.toDataURL('image/png')
        const exportMapContainer = exportContainer.querySelector('#amap-container')
        if (exportMapContainer) {
          exportMapContainer.innerHTML = `<img src="${mapSnapshot}" style="width:100%;height:100%;object-fit:cover;" />`
        }
      }
    }

    // 移除所有ant-card类,替换为纯div
    const cards = exportContainer.querySelectorAll('.ant-card')
    cards.forEach((card) => {
      const cardEl = card as HTMLElement
      try {
        cardEl.className = '' // 移除所有类
        cardEl.style.setProperty('background-color', '#ffffff')
        cardEl.style.setProperty('border-radius', '12px')
        cardEl.style.setProperty('box-shadow', '0 4px 12px rgba(0, 0, 0, 0.1)')
        cardEl.style.setProperty('margin-bottom', '20px')
        cardEl.style.setProperty('overflow', 'hidden')
      } catch (err) {
        console.error('设置卡片样式失败:', err)
      }
    })

    // 处理卡片头部
    const cardHeads = exportContainer.querySelectorAll('.ant-card-head')
    cardHeads.forEach((head) => {
      const headEl = head as HTMLElement
      try {
        headEl.style.setProperty('background-color', '#667eea')
        headEl.style.setProperty('color', '#ffffff')
        headEl.style.setProperty('padding', '16px 24px')
        headEl.style.setProperty('font-size', '18px')
        headEl.style.setProperty('font-weight', '600')
      } catch (err) {
        console.error('设置卡片头部样式失败:', err)
      }
    })

    // 处理卡片内容
    const cardBodies = exportContainer.querySelectorAll('.ant-card-body')
    cardBodies.forEach((body) => {
      const bodyEl = body as HTMLElement
      bodyEl.style.setProperty('background-color', '#ffffff')
      bodyEl.style.setProperty('padding', '24px')
    })

    // 处理酒店卡片头部
    const hotelCards = exportContainer.querySelectorAll('.hotel-card')
    hotelCards.forEach((card) => {
      const head = card.querySelector('.ant-card-head') as HTMLElement
      if (head) {
        head.style.setProperty('background-color', '#1976d2')
      }
      (card as HTMLElement).style.setProperty('background-color', '#e3f2fd')
    })

    // 处理天气卡片
    const weatherCards = exportContainer.querySelectorAll('.weather-card')
    weatherCards.forEach((card) => {
      (card as HTMLElement).style.setProperty('background-color', '#e0f7fa')
    })

    // 处理预算总计
    const budgetTotal = exportContainer.querySelector('.budget-total')
    if (budgetTotal) {
      const el = budgetTotal as HTMLElement
      el.style.setProperty('background-color', '#667eea')
      el.style.setProperty('color', '#ffffff')
      el.style.setProperty('padding', '20px')
      el.style.setProperty('border-radius', '12px')
      el.style.setProperty('margin-bottom', '20px')
    }

    // 处理预算项
    const budgetItems = exportContainer.querySelectorAll('.budget-item')
    budgetItems.forEach((item) => {
      const el = item as HTMLElement
      el.style.setProperty('background-color', '#f5f7fa')
      el.style.setProperty('padding', '16px')
      el.style.setProperty('border-radius', '8px')
      el.style.setProperty('margin-bottom', '12px')
    })

    // 添加到body(隐藏)
    exportContainer.style.position = 'absolute'
    exportContainer.style.left = '-9999px'
    document.body.appendChild(exportContainer)

    const canvas = await html2canvas(exportContainer, {
      backgroundColor: '#f5f7fa',
      scale: 2,
      logging: false,
      useCORS: true,
      allowTaint: true
    })

    // 移除容器
    document.body.removeChild(exportContainer)

    // 转换为图片并下载
    const link = document.createElement('a')
    link.download = `旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()

    message.success({ content: '图片导出成功!', key: 'export' })
  } catch (error: any) {
    console.error('导出图片失败:', error)
    message.error({ content: `导出图片失败: ${error.message}`, key: 'export' })
  }
}

// 导出为PDF
const exportAsPDF = async () => {
  try {
    message.loading({ content: '正在生成PDF...', key: 'export', duration: 0 })

    const element = document.querySelector('.main-content') as HTMLElement
    if (!element) {
      throw new Error('未找到内容元素')
    }

    // 创建一个独立的容器
    const exportContainer = document.createElement('div')
    exportContainer.style.width = element.offsetWidth + 'px'
    exportContainer.style.backgroundColor = '#f5f7fa'
    exportContainer.style.padding = '20px'

    // 复制所有内容
    exportContainer.innerHTML = element.innerHTML

    // 处理地图截图
    const mapContainer = document.getElementById('amap-container')
    if (mapContainer && map) {
      const mapCanvas = mapContainer.querySelector('canvas')
      if (mapCanvas) {
        const mapSnapshot = mapCanvas.toDataURL('image/png')
        const exportMapContainer = exportContainer.querySelector('#amap-container')
        if (exportMapContainer) {
          exportMapContainer.innerHTML = `<img src="${mapSnapshot}" style="width:100%;height:100%;object-fit:cover;" />`
        }
      }
    }

    // 移除所有ant-card类,替换为纯div
    const cards = exportContainer.querySelectorAll('.ant-card')
    cards.forEach((card) => {
      const cardEl = card as HTMLElement
      try {
        cardEl.className = ''
        cardEl.style.setProperty('background-color', '#ffffff')
        cardEl.style.setProperty('border-radius', '12px')
        cardEl.style.setProperty('box-shadow', '0 4px 12px rgba(0, 0, 0, 0.1)')
        cardEl.style.setProperty('margin-bottom', '20px')
        cardEl.style.setProperty('overflow', 'hidden')
      } catch (err) {
        console.error('设置卡片样式失败:', err)
      }
    })

    // 处理卡片头部
    const cardHeads = exportContainer.querySelectorAll('.ant-card-head')
    cardHeads.forEach((head) => {
      const headEl = head as HTMLElement
      try {
        headEl.style.setProperty('background-color', '#667eea')
        headEl.style.setProperty('color', '#ffffff')
        headEl.style.setProperty('padding', '16px 24px')
        headEl.style.setProperty('font-size', '18px')
        headEl.style.setProperty('font-weight', '600')
      } catch (err) {
        console.error('设置卡片头部样式失败:', err)
      }
    })

    // 处理卡片内容
    const cardBodies = exportContainer.querySelectorAll('.ant-card-body')
    cardBodies.forEach((body) => {
      const bodyEl = body as HTMLElement
      bodyEl.style.setProperty('background-color', '#ffffff')
      bodyEl.style.setProperty('padding', '24px')
    })

    // 处理酒店卡片头部
    const hotelCards = exportContainer.querySelectorAll('.hotel-card')
    hotelCards.forEach((card) => {
      const head = card.querySelector('.ant-card-head') as HTMLElement
      if (head) {
        head.style.setProperty('background-color', '#1976d2')
      }
      (card as HTMLElement).style.setProperty('background-color', '#e3f2fd')
    })

    // 处理天气卡片
    const weatherCards = exportContainer.querySelectorAll('.weather-card')
    weatherCards.forEach((card) => {
      (card as HTMLElement).style.setProperty('background-color', '#e0f7fa')
    })

    // 处理预算总计
    const budgetTotal = exportContainer.querySelector('.budget-total')
    if (budgetTotal) {
      const el = budgetTotal as HTMLElement
      el.style.setProperty('background-color', '#667eea')
      el.style.setProperty('color', '#ffffff')
      el.style.setProperty('padding', '20px')
      el.style.setProperty('border-radius', '12px')
      el.style.setProperty('margin-bottom', '20px')
    }

    // 处理预算项
    const budgetItems = exportContainer.querySelectorAll('.budget-item')
    budgetItems.forEach((item) => {
      const el = item as HTMLElement
      el.style.setProperty('background-color', '#f5f7fa')
      el.style.setProperty('padding', '16px')
      el.style.setProperty('border-radius', '8px')
      el.style.setProperty('margin-bottom', '12px')
    })

    // 添加到body(隐藏)
    exportContainer.style.position = 'absolute'
    exportContainer.style.left = '-9999px'
    document.body.appendChild(exportContainer)

    const canvas = await html2canvas(exportContainer, {
      backgroundColor: '#f5f7fa',
      scale: 2,
      logging: false,
      useCORS: true,
      allowTaint: true
    })

    // 移除容器
    document.body.removeChild(exportContainer)

    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4'
    })

    const imgWidth = 210 // A4宽度(mm)
    const imgHeight = (canvas.height * imgWidth) / canvas.width

    // 如果内容高度超过一页,分页处理
    let heightLeft = imgHeight
    let position = 0

    pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
    heightLeft -= 297 // A4高度

    while (heightLeft > 0) {
      position = heightLeft - imgHeight
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
      heightLeft -= 297
    }

    pdf.save(`旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.pdf`)

    message.success({ content: 'PDF导出成功!', key: 'export' })
  } catch (error: any) {
    console.error('导出PDF失败:', error)
    message.error({ content: `导出PDF失败: ${error.message}`, key: 'export' })
  }
}

// 初始化地图
type MappedAttraction = Attraction & { dayIndex: number; attrIndex: number }

const collectMapAttractions = (): MappedAttraction[] => {
  if (!tripPlan.value) return []
  return tripPlan.value.days.flatMap((day, dayIndex) =>
    day.attractions.flatMap((attraction, attrIndex) => {
      const longitude = Number(attraction.location?.longitude)
      const latitude = Number(attraction.location?.latitude)
      if (!Number.isFinite(longitude) || !Number.isFinite(latitude) ||
          Math.abs(longitude) > 180 || Math.abs(latitude) > 90 ||
          (longitude === 0 && latitude === 0)) return []
      return [{ ...attraction, location: { longitude, latitude }, dayIndex, attrIndex }]
    })
  )
}

const escapeHtml = (value: unknown): string => String(value ?? '').replace(/[&<>"']/g, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
})[character] || character)

const markerContent = (attraction: MappedAttraction): string => `
  <div style="padding: 10px;">
    <h4 style="margin: 0 0 8px 0;">${escapeHtml(attraction.name)}</h4>
    <p style="margin: 4px 0;"><strong>地址:</strong> ${escapeHtml(attraction.address)}</p>
    <p style="margin: 4px 0;"><strong>游览时长:</strong> ${escapeHtml(attraction.visit_duration)}分钟</p>
    <p style="margin: 4px 0;"><strong>描述:</strong> ${escapeHtml(attraction.description)}</p>
    <p style="margin: 4px 0; color: #1890ff;"><strong>第${attraction.dayIndex + 1}天 景点${attraction.attrIndex + 1}</strong></p>
  </div>
`

const destroyMap = () => {
  if (map) {
    if (mapProvider === 'leaflet') map.remove()
    else map.destroy()
  }
  map = null
  mapProvider = null
}

const initMap = async () => {
  const generation = ++mapGeneration
  destroyMap()
  mapStatus.value = '地图加载中…'
  const container = document.getElementById('amap-container')
  if (!container) return
  const attractions = collectMapAttractions()
  const key = (import.meta.env.VITE_AMAP_WEB_JS_KEY || '').trim()
  const securityCode = (import.meta.env.VITE_AMAP_SECURITY_JS_CODE || '').trim()

  if (key && securityCode && !key.startsWith('your_') && !securityCode.startsWith('your_')) {
    let timeoutId: number | undefined
    try {
      ;(window as any)._AMapSecurityConfig = { securityJsCode: securityCode }
      const AMap = await Promise.race([
        AMapLoader.load({ key, version: '2.0', plugins: ['AMap.Marker', 'AMap.Polyline', 'AMap.InfoWindow'] }),
        new Promise<never>((_, reject) => {
          timeoutId = window.setTimeout(() => reject(new Error('高德地图加载超时')), 12000)
        })
      ])
      if (generation !== mapGeneration) return
      map = new AMap.Map(container, {
        zoom: 12,
        center: [116.397128, 39.916527],
        viewMode: '2D'
      })
      mapProvider = 'amap'
      addAttractionMarkers(AMap, attractions)
      mapStatus.value = attractions.length ? '' : '行程景点暂无可用坐标'
      return
    } catch (error) {
      console.warn('高德地图不可用，切换到备用地图:', error)
      destroyMap()
    } finally {
      if (timeoutId !== undefined) window.clearTimeout(timeoutId)
    }
  }

  if (generation !== mapGeneration) return
  try {
    map = L.map(container, { scrollWheelZoom: false }).setView([20, 0], 2)
    mapProvider = 'leaflet'
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map)
    addLeafletMarkers(attractions)
    mapStatus.value = attractions.length ? '' : '行程景点暂无可用坐标'
    window.requestAnimationFrame(() => {
      if (generation === mapGeneration) map.invalidateSize()
    })
  } catch (error) {
    console.error('备用地图加载失败:', error)
    mapStatus.value = '地图加载失败，请刷新页面重试'
    destroyMap()
  }
}

// 添加景点标记
const addAttractionMarkers = (AMap: any, allAttractions: MappedAttraction[]) => {
  const markers: any[] = []
  allAttractions.forEach((attraction, index) => {
    const marker = new AMap.Marker({
      position: [attraction.location.longitude, attraction.location.latitude],
      title: attraction.name,
      label: {
        content: `<div style="background: #4CAF50; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">${index + 1}</div>`,
        offset: new AMap.Pixel(0, -30)
      }
    })

    // 创建信息窗口
    const infoWindow = new AMap.InfoWindow({
      content: markerContent(attraction),
      offset: new AMap.Pixel(0, -30)
    })

    // 点击标记显示信息窗口
    marker.on('click', () => {
      infoWindow.open(map, marker.getPosition())
    })

    markers.push(marker)
  })

  // 添加标记到地图
  map.add(markers)

  // 自动调整视野以包含所有标记
  if (allAttractions.length > 0) {
    map.setFitView(markers)
  }

  // 绘制路线
  drawRoutes(AMap, allAttractions)
}

const addLeafletMarkers = (attractions: MappedAttraction[]) => {
  const markers = attractions.map((attraction, index) => {
    const icon = L.divIcon({
      className: 'attraction-pin',
      html: `<span>${index + 1}</span>`,
      iconSize: [30, 30],
      iconAnchor: [15, 30]
    })
    return L.marker([attraction.location.latitude, attraction.location.longitude], { icon })
      .addTo(map)
      .bindPopup(markerContent(attraction))
  })

  const dayGroups = new Map<number, MappedAttraction[]>()
  attractions.forEach(attraction => {
    const group = dayGroups.get(attraction.dayIndex) || []
    group.push(attraction)
    dayGroups.set(attraction.dayIndex, group)
  })
  dayGroups.forEach(group => {
    if (group.length > 1) {
      L.polyline(group.map(item => [item.location.latitude, item.location.longitude]), {
        color: '#1890ff', weight: 4, opacity: 0.8
      }).addTo(map)
    }
  })

  if (markers.length === 1) {
    map.setView(markers[0].getLatLng(), 13)
  } else if (markers.length > 1) {
    map.fitBounds(L.featureGroup(markers).getBounds(), { padding: [32, 32], maxZoom: 14 })
  }
}

// 绘制路线
const drawRoutes = (AMap: any, attractions: any[]) => {
  if (attractions.length < 2) return

  // 按天分组绘制路线
  const dayGroups: any = {}
  attractions.forEach(attr => {
    if (!dayGroups[attr.dayIndex]) {
      dayGroups[attr.dayIndex] = []
    }
    dayGroups[attr.dayIndex].push(attr)
  })

  // 为每天的景点绘制路线
  Object.values(dayGroups).forEach((dayAttractions: any) => {
    if (dayAttractions.length < 2) return

    const path = dayAttractions.map((attr: any) => [
      attr.location.longitude,
      attr.location.latitude
    ])

    const polyline = new AMap.Polyline({
      path: path,
      strokeColor: '#1890ff',
      strokeWeight: 4,
      strokeOpacity: 0.8,
      strokeStyle: 'solid',
      showDir: true // 显示方向箭头
    })

    map.add(polyline)
  })
}
</script>

<style scoped>
.result-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  padding: 40px 20px;
}

.page-header {
  max-width: 1200px;
  margin: 0 auto 30px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  animation: fadeInDown 0.6s ease-out;
}

.back-button {
  border-radius: 8px;
  font-weight: 500;
}

/* 内容布局 */
.content-wrapper {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  gap: 24px;
}

.side-nav {
  width: 240px;
  flex-shrink: 0;
}

.side-nav :deep(.ant-menu) {
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  background: white;
}

.side-nav :deep(.ant-menu-item) {
  margin: 4px 8px;
  border-radius: 8px;
  transition: all 0.3s ease;
}

.side-nav :deep(.ant-menu-item-selected) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.side-nav :deep(.ant-menu-item:hover) {
  background: rgba(102, 126, 234, 0.1);
}

.main-content {
  flex: 1;
  min-width: 0;
}

/* 景点图片样式 */
.attraction-image-wrapper {
  position: relative;
  margin-bottom: 12px;
  border-radius: 8px;
  overflow: hidden;
}

.attraction-image {
  width: 100%;
  height: 200px;
  object-fit: cover;
  transition: transform 0.3s ease;
}

.attraction-image-wrapper:hover .attraction-image {
  transform: scale(1.05);
}

.attraction-badge {
  position: absolute;
  top: 12px;
  left: 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.badge-number {
  font-size: 18px;
}

.price-tag {
  position: absolute;
  top: 12px;
  right: 12px;
  background: rgba(255, 77, 79, 0.9);
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-weight: bold;
  font-size: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

/* 天气卡片样式 */
.weather-card {
  background: linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 100%);
  border: none !important;
  transition: all 0.3s ease;
}

.weather-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
}

.weather-date {
  font-size: 16px;
  font-weight: bold;
  color: #00796b;
  margin-bottom: 4px;
  text-align: center;
}

.weather-source {
  color: #52676a;
  font-size: 12px;
  margin-bottom: 10px;
  text-align: center;
}

.weather-info-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.weather-icon {
  font-size: 24px;
}

.weather-label {
  font-size: 12px;
  color: #666;
}

.weather-value {
  font-size: 16px;
  font-weight: 600;
  color: #00796b;
}

.weather-wind {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(0, 121, 107, 0.2);
  text-align: center;
  color: #00796b;
  font-size: 14px;
}

/* 回到顶部按钮 */
.back-top-button {
  width: 50px;
  height: 50px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: bold;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  cursor: pointer;
  transition: all 0.3s ease;
}

.back-top-button:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
}

/* 酒店卡片样式 */
.hotel-card {
  background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
  border: none !important;
}

.hotel-card :deep(.ant-card-head) {
  background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%);
}

.hotel-title {
  color: white !important;
  font-weight: 600;
}

/* 顶部信息区布局 */
.top-info-section {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
}

.left-info {
  flex: 0 0 400px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.right-map {
  flex: 1;
  min-width: 0;
}

/* 行程概览卡片 */
.overview-card {
  height: fit-content;
}

.overview-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 14px;
  font-weight: 600;
  color: #666;
}

.info-value {
  font-size: 15px;
  color: #333;
  line-height: 1.6;
}

/* 预算卡片 */
.budget-card {
  height: fit-content;
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.budget-item {
  text-align: center;
  padding: 12px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

.budget-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 8px;
}

.budget-value {
  font-size: 20px;
  font-weight: 700;
  color: #1890ff;
}

.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 8px;
  color: white;
}

.total-label {
  font-size: 16px;
  font-weight: 600;
}

.total-value {
  font-size: 28px;
  font-weight: 700;
}

/* 地图卡片 */
.map-card {
  height: 100%;
  min-height: 500px;
}

.map-card :deep(.ant-card-body) {
  height: calc(100% - 57px);
  padding: 0;
}

.map-surface {
  position: relative;
  width: 100%;
  height: 440px;
}

#amap-container {
  width: 100%;
  height: 100%;
}

.map-status {
  position: absolute;
  inset: 0;
  z-index: 1001;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  color: #475569;
  background: rgba(248, 250, 252, 0.9);
  text-align: center;
}

.map-surface :deep(.attraction-pin) {
  border: 2px solid white;
  border-radius: 50% 50% 50% 0;
  color: white;
  background: #1890ff;
  transform: rotate(-45deg);
  box-shadow: 0 2px 7px rgba(0, 0, 0, 0.3);
}

.map-surface :deep(.attraction-pin span) {
  display: flex;
  width: 26px;
  height: 26px;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  transform: rotate(45deg);
}

/* 每日行程卡片 */
.days-card {
  margin-top: 20px;
}

.day-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.day-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.day-date {
  font-size: 14px;
  color: #999;
}

.day-info {
  margin-bottom: 20px;
  padding: 16px;
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

.info-row {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}

.info-row:last-child {
  margin-bottom: 0;
}

.info-row .label {
  font-weight: 600;
  color: #666;
  min-width: 100px;
}

.info-row .value {
  color: #333;
  flex: 1;
}

/* 卡片样式优化 */
:deep(.ant-card) {
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  margin-bottom: 20px;
  transition: all 0.3s ease;
  animation: fadeInUp 0.6s ease-out;
}

:deep(.ant-card:hover) {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

:deep(.ant-card-head) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white !important;
  border-radius: 12px 12px 0 0;
  font-weight: 600;
}

:deep(.ant-card-head-title) {
  color: white !important;
  font-size: 18px;
}

:deep(.ant-card-head-title span) {
  color: white !important;
}

/* Collapse样式 */
:deep(.ant-collapse) {
  border: none;
  background: transparent;
}

:deep(.ant-collapse-item) {
  margin-bottom: 16px;
  border: 1px solid #e8e8e8;
  border-radius: 12px;
  overflow: hidden;
}

:deep(.ant-collapse-header) {
  background: linear-gradient(135deg, #f5f7fa 0%, #ffffff 100%);
  padding: 16px 20px !important;
  font-weight: 600;
}

:deep(.ant-collapse-content) {
  border-top: 1px solid #e8e8e8;
}

:deep(.ant-collapse-content-box) {
  padding: 20px;
}

/* 统计卡片样式 */
:deep(.ant-statistic-title) {
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}

:deep(.ant-statistic-content) {
  font-size: 24px;
  font-weight: 600;
  color: #1890ff;
}

/* 景点卡片样式 */
:deep(.ant-list-item) {
  transition: all 0.3s ease;
}

:deep(.ant-list-item:hover) {
  transform: scale(1.02);
}

/* 动画 */
@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .result-container {
    padding: 20px 10px;
  }

  .page-header {
    flex-direction: column;
    gap: 16px;
  }

  .top-info-section {
    flex-direction: column;
  }

  .left-info {
    flex: auto;
  }
}

/* AI 对话调整浮标与抽屉样式 */
.floating-chat-trigger {
  position: fixed;
  bottom: 40px;
  right: 40px;
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: #ffffff;
  padding: 12px 20px;
  border-radius: 30px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.35);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 999;
}

.floating-chat-trigger:hover {
  transform: translateY(-3px) scale(1.03);
  box-shadow: 0 12px 30px rgba(37, 99, 235, 0.45);
}

.trigger-icon {
  font-size: 20px;
}

.trigger-text {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.drawer-chips-wrap {
  background: #f8fafc;
  padding: 10px 12px;
  border-radius: 10px;
  margin-bottom: 12px;
  border: 1px solid #e2e8f0;
}

.chips-title {
  font-size: 11px;
  color: #64748b;
  font-weight: 600;
  margin-bottom: 6px;
}

.chips-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.drawer-chip-btn {
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 12px;
  padding: 3px 8px;
  font-size: 11px;
  color: #334155;
  cursor: pointer;
  transition: all 0.15s;
}

.drawer-chip-btn:hover {
  border-color: #3b82f6;
  color: #2563eb;
  background: #eff6ff;
}

.drawer-messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 8px 4px;
  margin-bottom: 12px;
}

.d-msg-row {
  display: flex;
  gap: 10px;
}

.d-msg-row.user {
  flex-direction: row-reverse;
}

.d-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.d-msg-row.user .d-avatar {
  background: #dbeafe;
}

.d-bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.5;
}

.d-msg-row.user .d-bubble {
  background: #2563eb;
  color: #ffffff;
  border-bottom-right-radius: 2px;
}

.d-msg-row.assistant .d-bubble {
  background: #f1f5f9;
  color: #1e293b;
  border-bottom-left-radius: 2px;
}

.d-bubble.loading {
  color: #64748b;
  font-style: italic;
}

.d-bubble-time {
  font-size: 10px;
  margin-top: 4px;
  opacity: 0.6;
  text-align: right;
}

.drawer-input-box {
  border-top: 1px solid #f1f5f9;
  padding-top: 10px;
}

.drawer-input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

.d-hint {
  font-size: 11px;
  color: #94a3b8;
}

/* RAG 知识库增强卡片样式 */
.knowledge-box {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #e2e8f0;
}

.knowledge-tags {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}

.knowledge-tag-item {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
}

.rag-tip-box {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rag-tip-box.booking-box {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #1e40af;
}

.rag-tip-box.advice-box {
  background: #fffbeb;
  border: 1px solid #fde68a;
  color: #92400e;
}

.rag-badge {
  display: inline-block;
  font-weight: 700;
  font-size: 11px;
  width: fit-content;
  padding: 1px 6px;
  border-radius: 4px;
}

.rag-badge.booking {
  background: #3b82f6;
  color: #ffffff;
}

.rag-badge.advice {
  background: #f59e0b;
  color: #ffffff;
}

.rag-text {
  font-size: 12px;
  color: inherit;
}

/* Phase 6 质量质检评估卡片样式 */
.eval-card {
  margin-bottom: 24px;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
}

.eval-body {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.eval-score-banner {
  display: flex;
  align-items: center;
  gap: 24px;
  background: linear-gradient(135deg, #f8fafc 0%, #eff6ff 100%);
  padding: 16px 20px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
}

.score-circle-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 90px;
  height: 90px;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.12);
  flex-shrink: 0;
}

.score-num {
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
}

.score-num.score-excellent {
  color: #16a34a;
}
.score-num.score-good {
  color: #2563eb;
}
.score-num.score-pass {
  color: #d97706;
}
.score-num.score-poor {
  color: #dc2626;
}

.score-label {
  font-size: 11px;
  color: #64748b;
  margin-top: 4px;
}

.score-meta-box {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.grade-title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.grade-tag {
  font-size: 14px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 6px;
}

.grade-tag.score-excellent {
  background: #dcfce7;
  color: #15803d;
}
.grade-tag.score-good {
  background: #dbeafe;
  color: #1d4ed8;
}
.grade-tag.score-pass {
  background: #fef3c7;
  color: #b45309;
}
.grade-tag.score-poor {
  background: #fee2e2;
  color: #b91c1c;
}

.grade-sub {
  font-size: 12px;
  color: #64748b;
}

.metrics-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.m-pill {
  background: #ffffff;
  border: 1px solid #cbd5e1;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 12px;
  display: flex;
  gap: 4px;
}

.m-k {
  color: #64748b;
}

.m-v {
  font-weight: 600;
  color: #1e293b;
}

.eval-dimensions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.dim-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px 14px;
}

.dim-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.dim-name {
  font-weight: 600;
  font-size: 13px;
  color: #334155;
}

.dim-score {
  font-weight: 700;
  font-size: 14px;
  color: #0f172a;
}

.dim-weight {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 4px;
}

.eval-suggestions-box {
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 12px 16px;
}

.sugg-title {
  font-size: 13px;
  font-weight: 700;
  color: #92400e;
  margin-bottom: 6px;
}

.sugg-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: #78350f;
  line-height: 1.6;
}

.eval-loading-box {
  padding: 24px;
  text-align: center;
}

/* 概览卡片顶栏评分徽章 */
.overview-score-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  font-size: 12px;
  font-weight: 700;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.overview-score-chip.score-excellent {
  background: #ecfdf5;
  border-color: #a7f3d0;
  color: #059669;
}

.overview-score-chip.score-good {
  background: #eff6ff;
  border-color: #bfdbfe;
  color: #2563eb;
}

.overview-score-chip.score-pass {
  background: #fffbeb;
  border-color: #fde68a;
  color: #d97706;
}

.overview-score-chip.score-poor {
  background: #fef2f2;
  border-color: #fecaca;
  color: #dc2626;
}

.overview-score-chip .osc-score {
  font-weight: 800;
}

.overview-score-chip .osc-grade {
  font-size: 11px;
  opacity: 0.9;
}

/* 抽屉气泡内的质检评分标签 */
.d-bubble-eval {
  margin-top: 6px;
  padding-top: 4px;
  border-top: 1px dashed rgba(148, 163, 184, 0.3);
}

.d-eval-tag {
  font-size: 11px;
  color: #2563eb;
  background: rgba(37, 99, 235, 0.08);
  padding: 2px 8px;
  border-radius: 6px;
  display: inline-block;
  font-weight: 600;
}
</style>


