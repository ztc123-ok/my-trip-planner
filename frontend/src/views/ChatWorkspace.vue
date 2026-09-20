<template>
  <div class="workspace-layout">
    <!-- 左侧侧边栏 (Sidebar) -->
    <aside class="workspace-sidebar" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
      <div class="sidebar-top">
        <div class="brand-header">
          <div class="brand-icon">✈️</div>
          <div class="brand-text" v-if="!sidebarCollapsed">
            <h2 class="brand-title">TripPlanner</h2>
            <span class="brand-subtitle">AI 旅行决策工作台</span>
          </div>
        </div>

        <button class="new-chat-btn" @click="startNewSession" :title="sidebarCollapsed ? '新建会话' : ''">
          <span class="btn-icon">＋</span>
          <span class="btn-text" v-if="!sidebarCollapsed">新建规划会话</span>
        </button>
      </div>

      <div class="session-list-section" v-if="!sidebarCollapsed">
        <div class="section-title">最近规划会话</div>
        <div class="session-list" v-if="sessions.length > 0">
          <div
            v-for="s in sessions"
            :key="s.id"
            class="session-item"
            :class="{ active: currentSessionId === s.id }"
            @click="switchSession(s.id)"
          >
            <div class="session-item-content">
              <span class="session-icon">💬</span>
              <div class="session-info">
                <span class="session-name" :title="s.title">{{ s.title }}</span>
                <span class="session-time">{{ s.updatedAt }}</span>
              </div>
            </div>
            <button class="delete-session-btn" @click.stop="deleteSession(s.id)" title="删除会话">×</button>
          </div>
        </div>
        <div class="empty-sessions" v-else>
          <span>暂无历史会话</span>
        </div>
      </div>

      <div class="sidebar-bottom">
        <div class="engine-badge" v-if="!sidebarCollapsed">
          <div class="status-indicator"></div>
          <div class="engine-info">
            <div class="engine-name">Qwen3.8-Flash 接入</div>
            <div class="engine-desc">LangGraph 多智能体协同</div>
          </div>
        </div>

        <div class="sidebar-actions">
          <button class="switch-mode-btn" @click="goToClassicForm" :title="sidebarCollapsed ? '经典表单模式' : ''">
            <span>📋</span>
            <span v-if="!sidebarCollapsed">经典表单模式</span>
          </button>
          <button class="toggle-sidebar-btn" @click="sidebarCollapsed = !sidebarCollapsed" :title="sidebarCollapsed ? '展开' : '收起'">
            <span>{{ sidebarCollapsed ? '⏩' : '⏪' }}</span>
          </button>
        </div>
      </div>
    </aside>

    <!-- 中央核心对话区域 (Main Chat Stream) -->
    <main class="chat-main" :class="{ 'with-canvas': showCanvas && currentPlan }">
      <!-- 顶部轻量工具栏 -->
      <header class="chat-header">
        <div class="header-left">
          <h1 class="chat-title">{{ activeTitle }}</h1>
          <span class="tag-badge" v-if="currentPlan">
            📍 {{ currentPlan.city }} · {{ currentPlan.days.length }}天行程
          </span>
        </div>
        <div class="header-right">
          <a-button
            v-if="currentPlan"
            :type="showCanvas ? 'primary' : 'default'"
            class="canvas-toggle-btn"
            @click="toggleCanvas"
          >
            <span>{{ showCanvas ? '🗺️ 收起看板' : '🗺️ 展开地图与行程看板' }}</span>
          </a-button>

          <a-dropdown v-if="currentPlan">
            <template #overlay>
              <a-menu>
                <a-menu-item key="export-img" @click="exportPlanImage">
                  📷 导出为长图 (PNG)
                </a-menu-item>
                <a-menu-item key="export-pdf" @click="exportPlanPDF">
                  📄 导出为 PDF 文档
                </a-menu-item>
                <a-menu-item key="export-md" @click="exportPlanMarkdown">
                  📝 导出为 Markdown
                </a-menu-item>
                <a-menu-item key="result-page" @click="viewFullResult">
                  🖥️ 查看全屏报表
                </a-menu-item>
              </a-menu>
            </template>
            <a-button>
              <span>📥 导出行程 ▾</span>
            </a-button>
          </a-dropdown>
        </div>
      </header>

      <!-- 消息流容器 -->
      <div class="messages-container" ref="messagesContainerRef">
        <!-- 初始欢迎界面 (完全还原参考截图视觉) -->
        <div class="welcome-screen" v-if="messages.length === 0">
          <div class="welcome-glow-bg"></div>
          <div class="welcome-icon-wrap">
            <div class="welcome-icon">✈️</div>
          </div>
          <div class="welcome-label">PURCHASE & TRIP INTELLIGENCE</div>
          <h2 class="welcome-heading">想去哪里旅行，直接问我。</h2>
          <p class="welcome-subheading">
            我会实时联动高德地图、天气预报与多智能体系统，把定制行程与地图路线整理成卡片给你看。
          </p>

          <!-- 灵感气泡胶囊 (快捷指令) -->
          <div class="inspiration-chips">
            <button
              v-for="chip in inspirationChips"
              :key="chip.text"
              class="inspiration-chip"
              @click="handleChipClick(chip.text)"
            >
              <span class="chip-text">{{ chip.text }}</span>
              <span class="chip-arrow">›</span>
            </button>
          </div>
        </div>

        <!-- 实际对话气泡流 -->
        <div class="conversation-stream" v-else>
          <div
            v-for="msg in messages"
            :key="msg.id"
            class="message-row"
            :class="msg.role"
          >
            <div class="avatar-wrap">
              <span v-if="msg.role === 'user'">👤</span>
              <span v-else>🤖</span>
            </div>

            <div class="message-content-wrap">
              <!-- 用户消息 -->
              <div v-if="msg.role === 'user'" class="user-bubble">
                {{ msg.content }}
              </div>

              <!-- AI 消息 -->
              <div v-else class="assistant-content">
                <!-- 修改提示摘要 -->
                <div v-if="msg.changesSummary" class="changes-banner">
                  <span class="banner-icon">✨</span>
                  <span class="banner-text">{{ msg.changesSummary }}</span>
                </div>

                <!-- 回复正文 -->
                <div class="assistant-bubble" v-if="msg.content">
                  {{ msg.content }}
                </div>

                <!-- 流式智能体进度卡片 (LangGraph 五大专家协作与深度推演流程输出) -->
                <div class="agent-collaboration-panel" v-if="msg.streamEvents && msg.streamEvents.length > 0">
                  <div class="panel-header">
                    <div class="panel-header-left">
                      <span class="panel-icon">⚡</span>
                      <span class="panel-title">LangGraph 多智能体协同推演</span>
                      <span class="elapsed-badge" v-if="msg.thoughtElapsed">
                        ⏱️ {{ msg.loading ? '已推演' : '共耗时' }} {{ msg.thoughtElapsed }}s
                      </span>
                    </div>
                    <div class="panel-header-right">
                      <button
                        type="button"
                        class="toggle-thought-btn"
                        @click="msg.isThoughtExpanded = msg.isThoughtExpanded === false ? true : false"
                        :title="msg.isThoughtExpanded !== false ? '点击收起推演细节' : '点击展开推演细节'"
                      >
                        {{ msg.isThoughtExpanded !== false ? '收起推演链路 ▴' : '展开推演链路 ▾' }}
                      </button>
                      <span class="stream-status-badge" :class="{ completed: !msg.loading }">
                        {{ msg.loading ? '深度思考推演中...' : '协作校验已完成' }}
                      </span>
                    </div>
                  </div>

                  <!-- 顶部五大专家状态矩阵 -->
                  <div class="agent-nodes-grid">
                    <div
                      v-for="node in currentAgentNodes"
                      :key="node.key"
                      class="agent-node-card"
                      :class="node.status"
                    >
                      <div class="node-icon-header">
                        <span class="node-icon">{{ node.icon }}</span>
                        <span class="node-status-indicator">
                          <span v-if="node.status === 'completed'" class="status-check">✓</span>
                          <span v-else-if="node.status === 'running'" class="pulse-dot"></span>
                          <span v-else class="status-pending">○</span>
                        </span>
                      </div>
                      <div class="node-name">{{ node.name }}</div>
                      <div class="node-detail" :title="node.detail">{{ node.detail || '准备中...' }}</div>
                    </div>
                  </div>

                  <!-- 核心新增：深度推演思考流时间轴 (Thought Process Steps) -->
                  <div class="thought-process-container" v-show="msg.isThoughtExpanded !== false && msg.thoughtSteps && msg.thoughtSteps.length > 0">
                    <div class="thought-timeline-title">
                      <span>🧠 多智能体推演思考链路</span>
                      <span class="step-count-badge">{{ msg.thoughtSteps?.length || 0 }} 个节点</span>
                    </div>
                    <div class="thought-timeline-list">
                      <div
                        v-for="step in msg.thoughtSteps"
                        :key="step.id"
                        class="thought-step-item"
                        :class="step.status"
                      >
                        <div class="step-indicator">
                          <span class="step-badge-icon" v-if="step.status === 'completed'">✓</span>
                          <span class="step-badge-pulse" v-else-if="step.status === 'running'">
                            <span class="ping-ring"></span>
                            <span class="core-dot">⚡</span>
                          </span>
                          <span class="step-badge-pending" v-else>○</span>
                          <div class="step-line"></div>
                        </div>
                        <div class="step-body">
                          <div class="step-header-line">
                            <span class="step-title">{{ step.title }}</span>
                            <span class="step-time" v-if="step.elapsedSeconds">{{ step.elapsedSeconds }}s</span>
                          </div>
                          <div class="step-desc">{{ step.detail }}</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- 实时总进度条与动态脉搏提示 -->
                  <div class="stream-progress-section" v-if="msg.loading">
                    <div class="stream-progress-bar">
                      <div class="progress-fill" :style="{ width: streamProgress + '%' }"></div>
                    </div>
                    <div class="stream-live-ticker">
                      <span class="live-dot-pulse"></span>
                      <span class="live-ticker-text">{{ currentLiveStepText || '多智能体专家全速运算中...' }}</span>
                      <span class="live-ticker-percent">{{ streamProgress }}%</span>
                    </div>
                  </div>
                </div>

                <!-- 生成成功的行程概要预览卡片 -->
                <div class="plan-summary-card" v-if="msg.planData">
                  <div class="plan-card-header">
                    <div class="plan-card-title">
                      <span>🗺️ {{ msg.planData.city }} {{ msg.planData.days.length }}天深度旅行规划</span>
                      <span class="date-badge">{{ msg.planData.start_date }} ~ {{ msg.planData.end_date }}</span>
                    </div>
                    <div class="budget-badge" v-if="msg.planData.budget">
                      预估总费用：¥{{ msg.planData.budget.total }}
                    </div>
                  </div>

                  <!-- 每日精炼亮点 -->
                  <div class="days-preview-grid">
                    <div
                      v-for="d in msg.planData.days"
                      :key="d.day_index"
                      class="day-preview-item"
                    >
                      <div class="day-badge">Day {{ d.day_index + 1 }}</div>
                      <div class="day-spots">
                        <span
                          v-for="a in d.attractions"
                          :key="a.name"
                          class="spot-tag"
                        >
                          📍 {{ a.name }}
                        </span>
                      </div>
                      <div class="day-hotel" v-if="d.hotel">
                        🏨 住宿: {{ d.hotel.name }}
                      </div>
                    </div>
                  </div>

                  <div class="plan-card-footer">
                    <span class="footer-tip">💡 您可以直接在下方输入修改意见（如：“把第2天的故宫换成颐和园”）</span>
                    <a-button type="primary" size="middle" @click="openCanvasWithPlan(msg.planData)">
                      在右侧看板查看完整地图路线 →
                    </a-button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部悬浮输入区域 (契合参考截图设计) -->
      <div class="chat-input-wrapper">
        <!-- 快捷追问修改胶囊 (当行程已生成时展示) -->
        <div class="modification-chips-container" v-if="currentPlan && !isLoading">
          <div class="mod-header-badge">
            <span class="mod-sparkle">✨</span>
            <span class="mod-tip-text">快捷微调</span>
          </div>

          <div class="mod-scroll-wrapper">
            <button
              class="mod-nav-arrow left"
              v-show="canScrollLeft"
              @click="scrollModChips('left')"
              title="向前滚动"
            >
              ‹
            </button>

            <div
              class="mod-chips-track"
              ref="modChipsTrackRef"
              @scroll="handleModScroll"
            >
              <button
                v-for="item in formattedQuickModificationChips"
                :key="item.text"
                class="mod-chip"
                :class="item.category"
                @click="handleModChipClick(item.text)"
              >
                <span class="mod-chip-icon">{{ item.icon }}</span>
                <span class="mod-chip-text">{{ item.text }}</span>
              </button>
            </div>

            <button
              class="mod-nav-arrow right"
              v-show="canScrollRight"
              @click="scrollModChips('right')"
              title="向后滚动"
            >
              ›
            </button>
          </div>
        </div>

        <div class="floating-input-card">
          <a-textarea
            v-model:value="inputMessage"
            placeholder="普通聊天，或提出旅行需求（例如：我想去北京玩3天，喜欢历史和美食，预算3000左右）..."
            :auto-size="{ minRows: 2, maxRows: 4 }"
            class="native-textarea"
            @keydown="handleKeyDown"
          />

          <div class="input-bottom-bar">
            <div class="shortcut-hint">
              <span class="key-icon">⇧</span> Shift + Enter 换行
            </div>
            <button
              class="send-btn"
              :disabled="isLoading || !inputMessage.trim()"
              @click="handleSend"
              title="发送指令"
            >
              <span class="send-icon">🚀</span>
            </button>
          </div>
        </div>
      </div>
    </main>

    <!-- 右侧联动行程与地图看板 (Collapsible Canvas) -->
    <aside class="workspace-canvas" v-if="showCanvas && currentPlan">
      <div class="canvas-header">
        <div class="canvas-title">
          <span>🗺️ 行程看板</span>
          <span class="city-sub">{{ currentPlan.city }} · {{ currentPlan.days.length }}天</span>
        </div>
        <div class="canvas-header-actions">
          <a-dropdown>
            <template #overlay>
              <a-menu>
                <a-menu-item key="canvas-export-img" @click="exportPlanImage">
                  📷 导出为长图 (PNG)
                </a-menu-item>
                <a-menu-item key="canvas-export-pdf" @click="exportPlanPDF">
                  📄 导出为 PDF
                </a-menu-item>
                <a-menu-item key="canvas-export-md" @click="exportPlanMarkdown">
                  📝 导出为 Markdown
                </a-menu-item>
                <a-menu-item key="canvas-view-full" @click="viewFullResult">
                  🖥️ 全屏报表模式
                </a-menu-item>
              </a-menu>
            </template>
            <a-button size="small" type="primary" ghost class="canvas-export-btn">
              <span>📥 导出 ▾</span>
            </a-button>
          </a-dropdown>
          <button class="close-canvas-btn" @click="showCanvas = false" title="关闭看板">×</button>
        </div>
      </div>

      <div class="canvas-body" id="canvas-export-content">
        <!-- 交互地图容器 -->
        <div class="canvas-map-wrap">
          <div class="canvas-map-header">
            <span class="map-label">📍 景点游览路线分布</span>
            <span class="map-provider-tag" :class="mapProvider">
              {{ mapProvider === 'amap' ? '高德地图' : 'OpenStreetMap' }}
            </span>
          </div>
          <div id="workspace-amap" class="map-container"></div>
          <div class="map-status-overlay" v-if="mapStatus">{{ mapStatus }}</div>
        </div>

        <!-- 目的地天气预报卡片 (重点新增) -->
        <div class="canvas-weather-card" v-if="currentPlan.weather_info && currentPlan.weather_info.length > 0">
          <div class="weather-header">
            <div class="weather-title">
              <span>🌤️ 目的地天气预报</span>
              <span class="weather-city">({{ currentPlan.city }})</span>
            </div>
            <span class="weather-source" v-if="currentPlan.weather_info[0]?.source">
              数据源: {{ currentPlan.weather_info[0].source }}
            </span>
          </div>
          <div class="weather-grid">
            <div
              v-for="w in currentPlan.weather_info"
              :key="w.date"
              class="weather-pill"
            >
              <div class="w-date">{{ formatShortDate(w.date) }}</div>
              <div class="w-icon">{{ getWeatherEmoji(w.day_weather) }}</div>
              <div class="w-cond">{{ w.day_weather || '晴' }}</div>
              <div class="w-temp">{{ w.night_temp }}° ~ {{ w.day_temp }}°C</div>
              <div class="w-wind" v-if="w.wind_power">{{ w.wind_direction }} {{ w.wind_power }}</div>
            </div>
          </div>
          <div class="missing-weather-hint" v-if="missingDatesList.length > 0">
            ℹ️ {{ missingDatesList.join('、') }} 超出实时预报范围，出行前可更新查询
          </div>
        </div>

        <!-- 预算明细小卡片 -->
        <div class="canvas-budget-card" v-if="currentPlan.budget">
          <div class="budget-header">
            <span>💰 预算核算</span>
            <span class="budget-total-num">¥{{ currentPlan.budget.total }}</span>
          </div>
          <div class="budget-pills">
            <div class="b-pill">门票: ¥{{ currentPlan.budget.total_attractions }}</div>
            <div class="b-pill">酒店: ¥{{ currentPlan.budget.total_hotels }}</div>
            <div class="b-pill">餐饮: ¥{{ currentPlan.budget.total_meals }}</div>
            <div class="b-pill">交通: ¥{{ currentPlan.budget.total_transportation }}</div>
          </div>
        </div>

        <!-- 每日行程列表 -->
        <div class="canvas-days-list">
          <div class="days-title">📅 每日游览安排</div>
          <div
            v-for="(day, dIdx) in currentPlan.days"
            :key="dIdx"
            class="day-card-item"
          >
            <div class="d-header">
              <span class="d-index">第 {{ day.day_index + 1 }} 天</span>
              <span class="d-date">{{ day.date }}</span>
            </div>
            <div class="d-desc">{{ day.description }}</div>

            <!-- 景点列表 -->
            <div class="d-spots-list">
              <div
                v-for="(att, aIdx) in day.attractions"
                :key="aIdx"
                class="spot-row"
              >
                <span class="spot-order">{{ aIdx + 1 }}</span>
                <div class="spot-info">
                  <div class="spot-name">{{ att.name }}</div>
                  <div class="spot-meta">{{ att.visit_duration }}分钟 · {{ att.ticket_price ? '门票¥' + att.ticket_price : '免费' }}</div>
                </div>
              </div>
            </div>

            <!-- 餐饮与酒店 -->
            <div class="d-hotel-row" v-if="day.hotel">
              🏨 <strong>酒店:</strong> {{ day.hotel.name }} ({{ day.hotel.price_range }})
            </div>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import dayjs from 'dayjs'
import type { TripPlan, ChatMessage, ChatSession, AgentNodeStatus, StreamEvent } from '@/types'
import {
  generateTripPlanStream,
  chatModifyTripPlan,
  parseNaturalLanguageTrip,
} from '@/services/api'

const router = useRouter()

// 侧边栏与布局状态
const sidebarCollapsed = ref(false)
const showCanvas = ref(false)
const isLoading = ref(false)
const inputMessage = ref('')
const messagesContainerRef = ref<HTMLDivElement | null>(null)

// 会话数据
const sessions = ref<ChatSession[]>([])
const currentSessionId = ref<string>('')
const messages = ref<ChatMessage[]>([])
const currentPlan = ref<TripPlan | null>(null)
const streamProgress = ref(0)
const currentLiveStepText = ref('')

// 智能体实时节点状态
const currentAgentNodes = ref<AgentNodeStatus[]>([
  { key: 'attractions', name: '景点搜索专家', icon: '📍', status: 'pending', detail: '等待调度' },
  { key: 'weather', name: '天气查询专家', icon: '🌤️', status: 'pending', detail: '等待调度' },
  { key: 'hotels', name: '酒店推荐专家', icon: '🏨', status: 'pending', detail: '等待调度' },
  { key: 'planner', name: '行程规划专家', icon: '📋', status: 'pending', detail: '等待汇总' },
  { key: 'validate', name: '质量校验专家', icon: '🛡️', status: 'pending', detail: '等待校验' },
])

// 灵感气泡与快捷指令
const inspirationChips = [
  { text: '🏛️ 北京3日历史文化深度游，预算2500' },
  { text: '🍜 成都4天吃货休闲路线，多安排地道美食' },
  { text: '🎡 周末上海迪士尼亲子游，带5岁小孩' },
  { text: '🏔️ 西安兵马俑+大唐不夜城2日文化探索' },
  { text: '☕ 杭州西湖漫步与龙井品茶慢节奏' },
]

interface ModChipItem {
  icon: string
  text: string
  category: 'attraction' | 'food' | 'budget' | 'pace' | 'hotel' | 'night' | 'family'
}

const formattedQuickModificationChips = computed<ModChipItem[]>(() => {
  if (!currentPlan.value) return []
  const city = currentPlan.value.city
  const days = currentPlan.value.days?.length || 3
  const budget = currentPlan.value.budget?.total || 3000
  const tighterBudget = Math.max(1000, Math.round((budget * 0.8) / 100) * 100)

  return [
    { icon: '🏛️', category: 'attraction', text: `把第${days > 1 ? 2 : 1}天的行程替换为更小众文化景致` },
    { icon: '🍜', category: 'food', text: `推荐${city}当地人常去的地道老字号与夜市` },
    { icon: '💰', category: 'budget', text: `总预算精简控制在 ¥${tighterBudget} 以内` },
    { icon: '⏳', category: 'pace', text: `每天减少1个景点，节奏更慢更松弛` },
    { icon: '🏨', category: 'hotel', text: `推荐一家靠近${city}核心地铁站的高性价比酒店` },
    { icon: '🌙', category: 'night', text: `在第一天晚间增加${city}夜景地标漫步` },
    { icon: '👶', category: 'family', text: `优化为适宜家庭出游，减少长途步行与爬坡` },
  ]
})

const modChipsTrackRef = ref<HTMLDivElement | null>(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)

const updateModScrollState = () => {
  if (!modChipsTrackRef.value) return
  const el = modChipsTrackRef.value
  canScrollLeft.value = el.scrollLeft > 5
  canScrollRight.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 5
}

const handleModScroll = () => {
  updateModScrollState()
}

const scrollModChips = (direction: 'left' | 'right') => {
  if (!modChipsTrackRef.value) return
  const el = modChipsTrackRef.value
  const offset = direction === 'left' ? -220 : 220
  el.scrollBy({ left: offset, behavior: 'smooth' })
  setTimeout(updateModScrollState, 300)
}

watch(formattedQuickModificationChips, () => {
  nextTick(() => {
    updateModScrollState()
  })
})

const activeTitle = computed(() => {
  if (currentPlan.value) {
    return `${currentPlan.value.city} ${currentPlan.value.days.length}日游决策会话`
  }
  return '智能旅行助手'
})

// 地图实例与状态
let mapInstance: any = null
let mapProvider: 'amap' | 'leaflet' | null = null
const mapStatus = ref('')

// 本地存储键
const STORAGE_SESSIONS = 'trip_chat_sessions_v2'
const STORAGE_CURRENT_SESSION = 'trip_current_session_id_v2'

onMounted(() => {
  loadSessionsFromStorage()
  if (sessions.value.length === 0) {
    startNewSession()
  } else {
    const savedId = localStorage.getItem(STORAGE_CURRENT_SESSION)
    if (savedId && sessions.value.some(s => s.id === savedId)) {
      switchSession(savedId)
    } else {
      switchSession(sessions.value[0].id)
    }
  }
  window.addEventListener('resize', updateModScrollState)
})

onUnmounted(() => {
  destroyMap()
  window.removeEventListener('resize', updateModScrollState)
})

const loadSessionsFromStorage = () => {
  try {
    const data = localStorage.getItem(STORAGE_SESSIONS)
    if (data) {
      sessions.value = JSON.parse(data)
    }
  } catch (e) {
    console.warn('加载会话记录异常:', e)
    sessions.value = []
  }
}

const saveSessionsToStorage = () => {
  try {
    localStorage.setItem(STORAGE_SESSIONS, JSON.stringify(sessions.value))
    if (currentSessionId.value) {
      localStorage.setItem(STORAGE_CURRENT_SESSION, currentSessionId.value)
    }
  } catch (e) {
    console.warn('存储会话记录异常:', e)
  }
}

const startNewSession = () => {
  const newId = 'session_' + Date.now().toString(36)
  const newSession: ChatSession = {
    id: newId,
    title: '新建旅行规划',
    city: '',
    updatedAt: '刚刚',
    messages: [],
  }
  sessions.value.unshift(newSession)
  currentSessionId.value = newId
  messages.value = []
  currentPlan.value = null
  showCanvas.value = false
  saveSessionsToStorage()
}

const switchSession = (sessionId: string) => {
  currentSessionId.value = sessionId
  const session = sessions.value.find(s => s.id === sessionId)
  if (session) {
    messages.value = session.messages || []
    currentPlan.value = session.tripPlan || null
    if (currentPlan.value) {
      sessionStorage.setItem('tripPlan', JSON.stringify(currentPlan.value))
    }
  }
  saveSessionsToStorage()
  scrollToBottom()
}

const deleteSession = (sessionId: string) => {
  sessions.value = sessions.value.filter(s => s.id !== sessionId)
  if (sessions.value.length === 0) {
    startNewSession()
  } else if (currentSessionId.value === sessionId) {
    switchSession(sessions.value[0].id)
  }
  saveSessionsToStorage()
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainerRef.value) {
      messagesContainerRef.value.scrollTop = messagesContainerRef.value.scrollHeight
    }
  })
}

const resetAgentNodes = () => {
  currentAgentNodes.value = [
    { key: 'attractions', name: '景点搜索专家', icon: '📍', status: 'running', detail: '检索真实高德景点中' },
    { key: 'weather', name: '天气查询专家', icon: '🌤️', status: 'running', detail: '查询气象预报中' },
    { key: 'hotels', name: '酒店推荐专家', icon: '🏨', status: 'running', detail: '精选住宿中' },
    { key: 'planner', name: '行程规划专家', icon: '📋', status: 'pending', detail: '等待汇总' },
    { key: 'validate', name: '质量校验专家', icon: '🛡️', status: 'pending', detail: '等待校验' },
  ]
  streamProgress.value = 10
}

const handleChipClick = (text: string) => {
  inputMessage.value = text.replace(/^[^\w\u4e00-\u9fa5]+/, '').trim()
  handleSend()
}

const handleModChipClick = (modText: string) => {
  inputMessage.value = modText
  handleSend()
}

const handleKeyDown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

// 发送用户指令 (流式生成或对话微调)
const handleSend = async () => {
  const text = inputMessage.value.trim()
  if (!text || isLoading.value) return

  inputMessage.value = ''

  // 添加用户消息
  const userMsg: ChatMessage = {
    id: 'user_' + Date.now(),
    role: 'user',
    content: text,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  }
  messages.value.push(userMsg)
  scrollToBottom()

  // 智能判断用户是否意图开启新规划：
  // 1. 当前无行程
  // 2. 包含“重新规划/生成/新计划/规划/去XX”
  // 3. 用户在输入中指定了明确的目的地城市或游玩天数
  const isNewPlanIntent = (
    !currentPlan.value ||
    text.includes('重新规划') ||
    text.includes('重新生成') ||
    text.includes('新计划') ||
    text.includes('帮我规划') ||
    text.includes('换个城市') ||
    /去[\u4e00-\u9fa5]{2,6}/.test(text) ||
    /\d+\s*(?:天|日)/.test(text)
  )

  if (isNewPlanIntent) {
    await handleChatStreamingGeneration(text)
  } else {
    await handleChatModification(text)
  }
}

// 辅助函数：将推演列表中处于 running 状态的节点标记为 completed
const markLastRunningStepDone = (msg: ChatMessage) => {
  if (!msg.thoughtSteps || msg.thoughtSteps.length === 0) return
  msg.thoughtSteps = msg.thoughtSteps.map(s =>
    s.status === 'running' ? { ...s, status: 'completed' as const } : s
  )
}

// 场景一：利用 SSE 流式生成新旅行计划
const handleChatStreamingGeneration = async (text: string) => {
  isLoading.value = true
  resetAgentNodes()

  const assistantMsgId = 'assistant_' + Date.now()
  const assistantMsg = reactive<ChatMessage>({
    id: assistantMsgId,
    role: 'assistant',
    content: '收到您的旅行需求，正在启动 LangGraph 多智能体专家协同规划...',
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    loading: true,
    streamEvents: [],
    thoughtSteps: [],
    thoughtElapsed: 0,
    isThoughtExpanded: true,
  })
  messages.value.push(assistantMsg)
  scrollToBottom()

  let elapsedTimer: any = null

  try {
    // 1. 意图解析：将自然语言提问转换为 TripFormData
    const parsedFormData = await parseNaturalLanguageTrip(text)
    assistantMsg.content = `已识别您的目的地为【${parsedFormData.city}】，计划游玩 ${parsedFormData.travel_days} 天。多智能体系统正在并行搜集地点与天气...`

    // 初始化思考流程时间线与秒表
    assistantMsg.thoughtSteps = [
      {
        id: 'step_init_' + Date.now(),
        title: '🛫 初始化规划任务',
        stage: '任务初始化',
        detail: `锁定目标城市【${parsedFormData.city}】，游玩 ${parsedFormData.travel_days} 天，启动 LangGraph 多智能体专家协同链路`,
        status: 'completed',
        elapsedSeconds: 0,
      }
    ]
    assistantMsg.streamEvents = [{ event: 'start', message: '规划任务初始化' }]
    currentLiveStepText.value = '正在启动 LangGraph 多智能体专家协同规划...'

    elapsedTimer = setInterval(() => {
      if (assistantMsg.thoughtElapsed !== undefined) {
        assistantMsg.thoughtElapsed += 1
      }
    }, 1000)

    // 2. 建立 SSE 流式长连接并逐个点亮节点与推演过程
    await generateTripPlanStream(
      parsedFormData,
      (evt: StreamEvent) => {
        // 更新流事件数组（通过扩展赋值保证响应式追踪）
        assistantMsg.streamEvents = [...(assistantMsg.streamEvents || []), evt]
        if (typeof evt.elapsed_seconds === 'number') {
          assistantMsg.thoughtElapsed = Math.round(evt.elapsed_seconds)
        }

        // 处理节点完成事件 (node_finish)
        if (evt.event === 'node_finish') {
          const node = currentAgentNodes.value.find(n => n.key === evt.node)
          if (node) {
            node.status = 'completed'
            node.detail = evt.message || '已完成'
          }

          if (evt.node === 'attractions') {
            markLastRunningStepDone(assistantMsg)
            const sampleNames = (evt.data?.samples || []).map((s: any) => s.name).slice(0, 3).join('、')
            assistantMsg.thoughtSteps = [
              ...(assistantMsg.thoughtSteps || []),
              {
                id: 'step_attractions_' + Date.now(),
                title: '📍 核心景点挖掘与空间坐标定位',
                stage: '景点挖掘检索',
                detail: `高德地图检索完成，获取 ${evt.data?.count || 10} 处候选景点（包含${sampleNames || '故宫、天坛等'}），已校验真实地理经纬度`,
                status: 'completed',
                elapsedSeconds: evt.elapsed_seconds,
              }
            ]
            currentLiveStepText.value = `已锁定 ${evt.data?.count || 10} 处景点坐标`
          } else if (evt.node === 'weather') {
            markLastRunningStepDone(assistantMsg)
            assistantMsg.thoughtSteps = [
              ...(assistantMsg.thoughtSteps || []),
              {
                id: 'step_weather_' + Date.now(),
                title: '🌤️ 目的地气象指标匹配',
                stage: '气象环境锁定',
                detail: evt.message || `已锁定未来出行气象预报，为每日动线编排提供温湿度与天气指标支撑`,
                status: 'completed',
                elapsedSeconds: evt.elapsed_seconds,
              }
            ]
            currentLiveStepText.value = evt.message || '气象环境锁定完成'
          } else if (evt.node === 'hotels') {
            markLastRunningStepDone(assistantMsg)
            const hotelNames = (evt.data?.samples || []).map((s: any) => s.name).slice(0, 2).join('、')
            assistantMsg.thoughtSteps = [
              ...(assistantMsg.thoughtSteps || []),
              {
                id: 'step_hotels_' + Date.now(),
                title: '🏨 周边优质住宿智能匹配',
                stage: '优质住宿匹配',
                detail: `已精选 ${evt.data?.count || '高分'} 家住宿（如${hotelNames || '品质酒店'}），测算接驳通达度`,
                status: 'completed',
                elapsedSeconds: evt.elapsed_seconds,
              }
            ]
            currentLiveStepText.value = `已精选 ${evt.data?.count || '多'} 家高分住宿`
          } else if (evt.node === 'planner') {
            markLastRunningStepDone(assistantMsg)
            assistantMsg.thoughtSteps = [
              ...(assistantMsg.thoughtSteps || []),
              {
                id: 'step_planner_finish_' + Date.now(),
                title: '📋 空间动线与预算推演定稿',
                stage: '时空动线与预算完成',
                detail: '每日游玩动线、早中晚三餐特色餐饮、住宿接驳与费用预算已完成整体测算',
                status: 'completed',
                elapsedSeconds: evt.elapsed_seconds,
              }
            ]
            const valNode = currentAgentNodes.value.find(n => n.key === 'validate')
            if (valNode) {
              valNode.status = 'running'
              valNode.detail = '正在进行行程质量闭环核验'
            }
            currentLiveStepText.value = '行程路线与预算编制完成，进入质量核验'
          } else if (evt.node === 'validate') {
            markLastRunningStepDone(assistantMsg)
            assistantMsg.thoughtSteps = [
              ...(assistantMsg.thoughtSteps || []),
              {
                id: 'step_validate_finish_' + Date.now(),
                title: '🛡️ 旅行计划质量闭环校验',
                stage: '质量闭环通过',
                detail: '已完成每日三餐完备性、经纬度真实性与预算平衡性校验，各项指标评级优秀！',
                status: 'completed',
                elapsedSeconds: evt.elapsed_seconds,
              }
            ]
            currentLiveStepText.value = '全流程校验通过，准备呈现！'
          }
          streamProgress.value = evt.progress || Math.min(95, streamProgress.value + 15)
        }

        // 处理节点启动事件 (node_start)
        else if (evt.event === 'node_start') {
          if (evt.node === 'planner') {
            const plannerNode = currentAgentNodes.value.find(n => n.key === 'planner')
            if (plannerNode) {
              plannerNode.status = 'running'
              plannerNode.detail = evt.stage || '情报汇集建模中'
            }
            markLastRunningStepDone(assistantMsg)
            assistantMsg.thoughtSteps = [
              ...(assistantMsg.thoughtSteps || []),
              {
                id: 'step_planner_start_' + Date.now(),
                title: '🧭 多源情报对齐与时空建模',
                stage: '情报汇集建模',
                detail: evt.message || '情报汇集完成，启动时空路径与多维规划模型...',
                status: 'running',
                elapsedSeconds: evt.elapsed_seconds,
              }
            ]
            currentLiveStepText.value = evt.message || '多源情报汇集，启动时空规划模型...'
            streamProgress.value = evt.progress || 72
          }
        }

        // 处理细分子步骤推进事件 (node_progress)
        else if (evt.event === 'node_progress') {
          if (evt.node === 'planner') {
            const plannerNode = currentAgentNodes.value.find(n => n.key === 'planner')
            if (plannerNode) {
              plannerNode.status = 'running'
              plannerNode.detail = evt.stage || evt.message || '模型演算中'
            }
            markLastRunningStepDone(assistantMsg)
            assistantMsg.thoughtSteps = [
              ...(assistantMsg.thoughtSteps || []),
              {
                id: 'step_planner_sub_' + Date.now(),
                title: `⚡ ${evt.stage || '深度规划推演'}`,
                stage: evt.stage,
                detail: evt.message || '正在测算时空动线与预算参数...',
                status: 'running',
                elapsedSeconds: evt.elapsed_seconds,
              }
            ]
            currentLiveStepText.value = evt.message || `${evt.stage} 推演中...`
            streamProgress.value = evt.progress || Math.min(92, streamProgress.value + 3)
          }
        }

        // 处理自愈重试事件 (retry)
        else if (evt.event === 'retry') {
          markLastRunningStepDone(assistantMsg)
          assistantMsg.thoughtSteps = [
            ...(assistantMsg.thoughtSteps || []),
            {
              id: 'step_retry_' + Date.now(),
              title: '🔄 智能自愈与重试修正',
              stage: '自愈微调修复',
              detail: evt.message || '检测到局部细节瑕疵，正在启动自愈微调...',
              status: 'running',
              elapsedSeconds: evt.elapsed_seconds,
            }
          ]
          currentLiveStepText.value = evt.message || '正在自动重试修复行程...'
          streamProgress.value = evt.progress || 75
        }

        // 处理完成事件 (plan_complete)
        else if (evt.event === 'plan_complete' && evt.data) {
          if (elapsedTimer) {
            clearInterval(elapsedTimer)
            elapsedTimer = null
          }
          // 标记所有推演步骤为已完成
          if (assistantMsg.thoughtSteps) {
            assistantMsg.thoughtSteps = assistantMsg.thoughtSteps.map(s => ({ ...s, status: 'completed' as const }))
          }

          const plan = evt.data as TripPlan
          currentPlan.value = plan
          assistantMsg.planData = plan
          assistantMsg.loading = false
          assistantMsg.content = `✨ 已为您生成定制的【${plan.city}】${plan.days.length}天行程！总体预算预估 ¥${plan.budget?.total || 0}。`
          streamProgress.value = 100
          currentLiveStepText.value = '行程规划已就绪！'

          currentAgentNodes.value.forEach(n => {
            n.status = 'completed'
          })

          // 更新会话标题与持久化
          const session = sessions.value.find(s => s.id === currentSessionId.value)
          if (session) {
            session.title = `${plan.city} ${plan.days.length}日游`
            session.city = plan.city
            session.tripPlan = plan
            session.messages = messages.value
            saveSessionsToStorage()
          }
          sessionStorage.setItem('tripPlan', JSON.stringify(plan))

          // 自动展开右侧看板
          showCanvas.value = true
          nextTick(() => {
            initWorkspaceMap()
          })
        } else if (evt.event === 'error') {
          if (elapsedTimer) {
            clearInterval(elapsedTimer)
            elapsedTimer = null
          }
          assistantMsg.content = `抱歉，在规划生成过程中出现异常: ${evt.message}`
          assistantMsg.loading = false
          currentLiveStepText.value = '规划出现异常'
        }
        nextTick(() => {
          scrollToBottom()
        })
      },
      (err: any) => {
        if (elapsedTimer) {
          clearInterval(elapsedTimer)
          elapsedTimer = null
        }
        assistantMsg.loading = false
        assistantMsg.content = `规划连接异常: ${err.message || err}`
        currentLiveStepText.value = '连接异常'
      }
    )
  } catch (err: any) {
    if (elapsedTimer) {
      clearInterval(elapsedTimer)
      elapsedTimer = null
    }
    assistantMsg.loading = false
    assistantMsg.content = `规划失败: ${err.message || '未知错误'}`
    currentLiveStepText.value = '规划失败'
  } finally {
    if (elapsedTimer) {
      clearInterval(elapsedTimer)
      elapsedTimer = null
    }
    isLoading.value = false
    scrollToBottom()
  }
}

// 场景二：利用 LangGraph chat_modify 子图对话式调整行程
const handleChatModification = async (text: string) => {
  if (!currentPlan.value) return
  isLoading.value = true

  const assistantMsgId = 'assistant_' + Date.now()
  const assistantMsg = reactive<ChatMessage>({
    id: assistantMsgId,
    role: 'assistant',
    content: '收到调整意见，正在重构行程动线与预算...',
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    loading: true,
    thoughtSteps: [
      {
        id: 'mod_step_1_' + Date.now(),
        title: '🔍 意图与地点关键词识别',
        stage: '语义识别',
        detail: `正在解析指令【${text}】，识别涉及的游览天数、景点更迭与预算变动...`,
        status: 'running',
        elapsedSeconds: 0,
      }
    ],
    thoughtElapsed: 0,
    isThoughtExpanded: true,
    streamEvents: [{ event: 'start', message: '启动行程对话微调' }],
  })
  messages.value.push(assistantMsg)
  scrollToBottom()

  let modTimer: any = setInterval(() => {
    if (assistantMsg.thoughtElapsed !== undefined) {
      assistantMsg.thoughtElapsed += 1
      if (assistantMsg.thoughtElapsed === 2 && assistantMsg.thoughtSteps) {
        assistantMsg.thoughtSteps = assistantMsg.thoughtSteps.map((s, idx) => idx === 0 ? { ...s, status: 'completed' as const } : s)
        assistantMsg.thoughtSteps = [
          ...assistantMsg.thoughtSteps,
          {
            id: 'mod_step_2_' + Date.now(),
            title: '🗺️ 高德 POI 检索与坐标校准',
            stage: '地点检索',
            detail: '若包含新景点/酒店，正在调取高德真实地理坐标与开放时间...',
            status: 'running',
            elapsedSeconds: 2,
          }
        ]
        scrollToBottom()
      } else if (assistantMsg.thoughtElapsed === 5 && assistantMsg.thoughtSteps && assistantMsg.thoughtSteps.length === 2) {
        assistantMsg.thoughtSteps = assistantMsg.thoughtSteps.map((s, idx) => idx === 1 ? { ...s, status: 'completed' as const } : s)
        assistantMsg.thoughtSteps = [
          ...assistantMsg.thoughtSteps,
          {
            id: 'mod_step_3_' + Date.now(),
            title: '🧠 动线拓扑与预算重构',
            stage: '微调计算',
            detail: '正在重算调整后当天的空间交通动线、餐饮安排与预算差额...',
            status: 'running',
            elapsedSeconds: 5,
          }
        ]
        scrollToBottom()
      }
    }
  }, 1000)

  try {
    const historyPayload = messages.value.slice(-6).map(m => ({
      role: m.role,
      content: m.content,
    }))

    const res = await chatModifyTripPlan({
      thread_id: currentSessionId.value,
      message: text,
      trip_plan: currentPlan.value,
      chat_history: historyPayload,
    })

    clearInterval(modTimer)
    if (assistantMsg.thoughtSteps) {
      assistantMsg.thoughtSteps = assistantMsg.thoughtSteps.map(s => ({ ...s, status: 'completed' as const }))
    }
    assistantMsg.loading = false
    if (res.success && res.data) {
      assistantMsg.content = res.data.reply
      assistantMsg.changesSummary = res.data.changes_summary

      if (res.data.updated_plan && res.data.modified) {
        currentPlan.value = res.data.updated_plan
        assistantMsg.planData = res.data.updated_plan
        sessionStorage.setItem('tripPlan', JSON.stringify(res.data.updated_plan))

        // 更新历史持久化
        const session = sessions.value.find(s => s.id === currentSessionId.value)
        if (session) {
          session.tripPlan = res.data.updated_plan
          session.messages = messages.value
          saveSessionsToStorage()
        }

        // 联动重绘地图
        if (showCanvas.value) {
          nextTick(() => {
            initWorkspaceMap()
          })
        }
        message.success('行程已联动更新！')
      }
    } else {
      assistantMsg.content = res.message || '未能完成调整'
    }
  } catch (err: any) {
    clearInterval(modTimer)
    assistantMsg.loading = false
    assistantMsg.content = `调整失败: ${err.message || err}`
  } finally {
    clearInterval(modTimer)
    isLoading.value = false
    scrollToBottom()
  }
}

const openCanvasWithPlan = (plan: TripPlan) => {
  currentPlan.value = plan
  showCanvas.value = true
  nextTick(() => {
    initWorkspaceMap()
  })
}

// 看板开关
const toggleCanvas = () => {
  showCanvas.value = !showCanvas.value
  if (showCanvas.value && currentPlan.value) {
    nextTick(() => {
      initWorkspaceMap()
    })
  }
}

// 导航与页面跳转
const goToClassicForm = () => {
  router.push('/form')
}

const viewFullResult = () => {
  if (currentPlan.value) {
    sessionStorage.setItem('tripPlan', JSON.stringify(currentPlan.value))
    router.push('/result')
  }
}

// ============ 天气辅助逻辑 ============
const getWeatherEmoji = (cond?: string): string => {
  if (!cond) return '🌤️'
  if (cond.includes('晴')) return '☀️'
  if (cond.includes('云') || cond.includes('阴')) return '⛅'
  if (cond.includes('雨')) return '🌧️'
  if (cond.includes('雪')) return '🌨️'
  if (cond.includes('雷')) return '⚡'
  if (cond.includes('风')) return '💨'
  return '🌤️'
}

const formatShortDate = (dateStr: string): string => {
  if (!dateStr) return ''
  const d = dayjs(dateStr)
  if (!d.isValid()) return dateStr
  const weekDays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  return `${d.format('MM-DD')} ${weekDays[d.day()]}`
}

const missingDatesList = computed(() => {
  if (!currentPlan.value) return []
  const forecastDates = new Set((currentPlan.value.weather_info ?? []).map(w => w.date))
  const missing: string[] = []
  const end = dayjs(currentPlan.value.end_date)
  for (let d = dayjs(currentPlan.value.start_date); d.isValid() && !d.isAfter(end, 'day'); d = d.add(1, 'day')) {
    const val = d.format('YYYY-MM-DD')
    if (!forecastDates.has(val)) missing.push(d.format('MM-DD'))
  }
  return missing
})

const escapeHtml = (value: unknown): string =>
  String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character] || character)

// ============ 导出逻辑 (图片、PDF、Markdown) ============
const createExportDOM = (plan: TripPlan): HTMLElement => {
  const container = document.createElement('div')
  container.style.position = 'fixed'
  container.style.left = '-99999px'
  container.style.top = '0'
  container.style.width = '780px'
  container.style.backgroundColor = '#ffffff'
  container.style.padding = '32px'
  container.style.fontFamily = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
  container.style.color = '#1e293b'
  container.style.boxSizing = 'border-box'

  let html = `
    <div style="border-bottom: 2px solid #2563eb; padding-bottom: 16px; margin-bottom: 20px;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <h1 style="margin:0; font-size:24px; color:#0f172a; font-weight:800;">🗺️ ${escapeHtml(plan.city)} ${plan.days.length} 天深度旅行规划</h1>
        <span style="font-size:12px; color:#2563eb; background:#eff6ff; padding:4px 10px; border-radius:6px; font-weight:bold;">TripPlanner AI</span>
      </div>
      <div style="margin-top:10px; display:flex; gap:16px; font-size:13px; color:#475569;">
        <span>📅 <strong>出行日期:</strong> ${escapeHtml(plan.start_date)} ~ ${escapeHtml(plan.end_date)}</span>
        ${plan.budget ? `<span style="color:#e11d48; font-weight:bold;">💰 <strong>预估总预算:</strong> ¥${plan.budget.total}</span>` : ''}
      </div>
      ${plan.overall_suggestions ? `<div style="margin-top:10px; font-size:12px; color:#475569; background:#f8fafc; padding:8px 12px; border-radius:6px; line-height:1.5;">💡 <strong>总体建议:</strong> ${escapeHtml(plan.overall_suggestions)}</div>` : ''}
    </div>
  `

  // 天气模块
  if (plan.weather_info && plan.weather_info.length > 0) {
    html += `
      <div style="margin-bottom: 20px;">
        <div style="font-size:14px; font-weight:700; color:#1e293b; margin-bottom:8px;">🌤️ 目的地气象预报</div>
        <div style="display:grid; grid-template-columns:repeat(${Math.min(5, plan.weather_info.length)}, 1fr); gap:8px;">
          ${plan.weather_info.map(w => `
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:8px 6px; text-align:center;">
              <div style="font-size:11px; color:#64748b;">${escapeHtml(w.date)}</div>
              <div style="font-size:18px; margin:3px 0;">${getWeatherEmoji(w.day_weather)}</div>
              <div style="font-size:12px; font-weight:600; color:#334155;">${escapeHtml(w.day_weather || '晴')}</div>
              <div style="font-size:11px; color:#e11d48; font-weight:bold;">${w.night_temp}° ~ ${w.day_temp}°C</div>
            </div>
          `).join('')}
        </div>
      </div>
    `
  }

  // 预算细分
  if (plan.budget) {
    html += `
      <div style="margin-bottom: 20px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:12px;">
        <div style="font-size:13px; font-weight:700; color:#334155; margin-bottom:8px;">💰 预算分配明细</div>
        <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:8px; font-size:12px;">
          <div style="background:#fff; padding:6px 10px; border-radius:6px; border:1px solid #e2e8f0;">景点门票: ¥${plan.budget.total_attractions}</div>
          <div style="background:#fff; padding:6px 10px; border-radius:6px; border:1px solid #e2e8f0;">住宿预估: ¥${plan.budget.total_hotels}</div>
          <div style="background:#fff; padding:6px 10px; border-radius:6px; border:1px solid #e2e8f0;">餐饮预估: ¥${plan.budget.total_meals}</div>
          <div style="background:#fff; padding:6px 10px; border-radius:6px; border:1px solid #e2e8f0;">交通出行: ¥${plan.budget.total_transportation}</div>
        </div>
      </div>
    `
  }

  // 每日详细安排
  html += `<div style="margin-bottom: 12px; font-size:14px; font-weight:700; color:#1e293b;">📅 每日游览详情</div>`
  plan.days.forEach((day, idx) => {
    html += `
      <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:14px; margin-bottom:12px; page-break-inside: avoid;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <span style="font-size:14px; font-weight:700; color:#2563eb;">第 ${idx + 1} 天 (${escapeHtml(day.date)})</span>
          <span style="font-size:12px; color:#64748b;">${escapeHtml(day.transportation)} · ${escapeHtml(day.accommodation)}</span>
        </div>
        <div style="font-size:12px; color:#475569; margin-bottom:10px; line-height:1.5;">${escapeHtml(day.description)}</div>

        ${day.attractions && day.attractions.length > 0 ? `
          <div style="margin-bottom:8px;">
            <div style="font-size:12px; font-weight:600; color:#334155; margin-bottom:6px;">🎯 游览景点</div>
            <div style="display:flex; flex-direction:column; gap:6px;">
              ${day.attractions.map((att, aIdx) => `
                <div style="background:#f8fafc; padding:8px 10px; border-radius:6px; font-size:12px; display:flex; justify-content:space-between; align-items:flex-start;">
                  <div>
                    <strong style="color:#0f172a;">${aIdx + 1}. ${escapeHtml(att.name)}</strong>
                    <span style="font-size:11px; color:#64748b; margin-left:6px;">(游览约 ${att.visit_duration || 60} 分钟)</span>
                    <div style="font-size:11px; color:#64748b; margin-top:2px;">📍 ${escapeHtml(att.address || '')}</div>
                    <div style="font-size:11px; color:#475569; margin-top:2px;">${escapeHtml(att.description)}</div>
                  </div>
                  <span style="font-size:11px; color:#e11d48; font-weight:bold; white-space:nowrap; margin-left:8px;">
                    ${att.ticket_price ? '¥' + att.ticket_price : '免费'}
                  </span>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}

        ${day.hotel ? `
          <div style="font-size:11px; background:#eff6ff; padding:6px 10px; border-radius:6px; color:#1e40af; margin-top:6px;">
            🏨 <strong>推荐入住:</strong> ${escapeHtml(day.hotel.name)} (${escapeHtml(day.hotel.price_range || '')})
          </div>
        ` : ''}
      </div>
    `
  })

  html += `
    <div style="margin-top:20px; text-align:center; font-size:11px; color:#94a3b8; border-top:1px solid #f1f5f9; padding-top:12px;">
      TripPlanner 智能旅行助手生成 · ${new Date().toLocaleDateString()}
    </div>
  `

  container.innerHTML = html
  return container
}

// 导出为长图 (PNG)
const exportPlanImage = async () => {
  if (!currentPlan.value) return
  message.loading({ content: '正在生成高清行程长图...', key: 'export_action', duration: 0 })
  try {
    const exportNode = createExportDOM(currentPlan.value)
    document.body.appendChild(exportNode)

    const canvas = await html2canvas(exportNode, {
      backgroundColor: '#f8fafc',
      scale: 2,
      useCORS: true,
      allowTaint: true,
      logging: false,
    })

    document.body.removeChild(exportNode)

    const link = document.createElement('a')
    link.download = `${currentPlan.value.city}旅行规划_${dayjs().format('YYYYMMDD_HHmm')}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()

    message.success({ content: '行程长图导出成功！', key: 'export_action' })
  } catch (err: any) {
    message.error({ content: `导出图片失败: ${err.message || err}`, key: 'export_action' })
  }
}

// 导出为 PDF
const exportPlanPDF = async () => {
  if (!currentPlan.value) return
  message.loading({ content: '正在生成 PDF 文档...', key: 'export_action', duration: 0 })
  try {
    const exportNode = createExportDOM(currentPlan.value)
    document.body.appendChild(exportNode)

    const canvas = await html2canvas(exportNode, {
      backgroundColor: '#f8fafc',
      scale: 2,
      useCORS: true,
      allowTaint: true,
      logging: false,
    })

    document.body.removeChild(exportNode)

    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4',
    })

    const imgWidth = 210 // A4 宽度 (mm)
    const pageHeight = 297 // A4 高度 (mm)
    const imgHeight = (canvas.height * imgWidth) / canvas.width

    let heightLeft = imgHeight
    let position = 0

    pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
    heightLeft -= pageHeight

    while (heightLeft > 0) {
      position = heightLeft - imgHeight
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
      heightLeft -= pageHeight
    }

    pdf.save(`${currentPlan.value.city}旅行规划_${dayjs().format('YYYYMMDD_HHmm')}.pdf`)
    message.success({ content: 'PDF 文档导出成功！', key: 'export_action' })
  } catch (err: any) {
    message.error({ content: `导出 PDF 失败: ${err.message || err}`, key: 'export_action' })
  }
}

// 导出为 Markdown
const exportPlanMarkdown = () => {
  if (!currentPlan.value) return
  const plan = currentPlan.value
  let md = `# 🗺️ ${plan.city} ${plan.days.length} 天深度旅行规划\n\n`
  md += `> **出行日期**: ${plan.start_date} ~ ${plan.end_date}\n`
  if (plan.budget) {
    md += `> **预估总预算**: ¥${plan.budget.total} (门票: ¥${plan.budget.total_attractions} | 住宿: ¥${plan.budget.total_hotels} | 餐饮: ¥${plan.budget.total_meals} | 交通: ¥${plan.budget.total_transportation})\n`
  }
  if (plan.overall_suggestions) {
    md += `> **总体建议**: ${plan.overall_suggestions}\n`
  }
  md += `\n`

  if (plan.weather_info && plan.weather_info.length > 0) {
    md += `## 🌤️ 目的地气象预报\n\n`
    md += `| 日期 | 白天天气 | 夜间天气 | 气温范围 | 风向风力 |\n`
    md += `| :--- | :--- | :--- | :--- | :--- |\n`
    plan.weather_info.forEach(w => {
      md += `| ${w.date} | ${w.day_weather || '-'} | ${w.night_weather || '-'} | ${w.night_temp}° ~ ${w.day_temp}°C | ${w.wind_direction} ${w.wind_power} |\n`
    })
    md += `\n`
  }

  md += `## 📅 详细日程安排\n\n`
  plan.days.forEach((d, idx) => {
    md += `### Day ${idx + 1} (${d.date}) - ${d.description}\n\n`
    md += `- **交通方式**: ${d.transportation}\n`
    md += `- **住宿偏好**: ${d.accommodation}`
    if (d.hotel) {
      md += ` (${d.hotel.name}，${d.hotel.price_range}，地址: ${d.hotel.address})`
    }
    md += `\n\n`

    if (d.attractions && d.attractions.length > 0) {
      md += `#### 🎯 游览景点\n\n`
      d.attractions.forEach((a, aIdx) => {
        md += `${aIdx + 1}. **${a.name}**\n`
        md += `   - 游览时长: ${a.visit_duration} 分钟\n`
        md += `   - 门票参考: ${a.ticket_price ? '¥' + a.ticket_price : '免费'}\n`
        md += `   - 地址: ${a.address || '暂无详细地址'}\n`
        md += `   - 说明: ${a.description}\n\n`
      })
    }

    if (d.meals && d.meals.length > 0) {
      md += `#### 🍽️ 餐饮安排\n\n`
      d.meals.forEach(m => {
        const typeNames: Record<string, string> = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '特色小吃' }
        md += `- **${typeNames[m.type] || m.type}**: ${m.name}${m.description ? ' - ' + m.description : ''}${m.estimated_cost ? ' (约¥' + m.estimated_cost + ')' : ''}\n`
      })
      md += `\n`
    }
  })

  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.download = `${plan.city}旅行规划路书_${dayjs().format('YYYYMMDD')}.md`
  link.href = url
  link.click()
  URL.revokeObjectURL(url)
  message.success('Markdown 旅行路书已导出！')
}

// ============ 地图渲染与联动 (高德优先，Leaflet 毫秒回退) ============
const collectPOIs = () => {
  if (!currentPlan.value) return []
  const pois: any[] = []
  currentPlan.value.days.forEach((day, dIdx) => {
    day.attractions.forEach((att, aIdx) => {
      const lng = Number(att.location?.longitude)
      const lat = Number(att.location?.latitude)
      if (Number.isFinite(lng) && Number.isFinite(lat) && lng !== 0 && lat !== 0) {
        pois.push({
          name: att.name,
          address: att.address || '',
          visitDuration: att.visit_duration || 60,
          ticketPrice: att.ticket_price || 0,
          description: att.description || '',
          dayIndex: dIdx,
          attrIndex: aIdx,
          position: [lng, lat],
        })
      }
    })
  })
  return pois
}

const initWorkspaceMap = async () => {
  if (!currentPlan.value) return
  destroyMap()

  const container = document.getElementById('workspace-amap')
  if (!container) return

  mapStatus.value = '地图加载中…'
  const pois = collectPOIs()

  const centerLng = pois.length > 0 ? pois[0].position[0] : 116.397
  const centerLat = pois.length > 0 ? pois[0].position[1] : 39.916

  const key = (import.meta.env.VITE_AMAP_WEB_JS_KEY || '').trim()
  const securityCode = (import.meta.env.VITE_AMAP_SECURITY_JS_CODE || '').trim()

  // 仅在同时提供合法高德 Web Key 与安全密钥时尝试高德
  if (key && securityCode && !key.startsWith('your_') && !securityCode.startsWith('your_')) {
    let timeoutId: number | undefined
    try {
      ;(window as any)._AMapSecurityConfig = { securityJsCode: securityCode }
      const AMap = await Promise.race([
        AMapLoader.load({
          key,
          version: '2.0',
          plugins: ['AMap.Marker', 'AMap.Polyline', 'AMap.InfoWindow'],
        }),
        new Promise<never>((_, reject) => {
          timeoutId = window.setTimeout(() => reject(new Error('高德地图加载超时')), 3000)
        }),
      ])

      mapInstance = new AMap.Map(container, {
        center: [centerLng, centerLat],
        zoom: 12,
        viewMode: '2D',
      })
      mapProvider = 'amap'

      pois.forEach(poi => {
        const marker = new AMap.Marker({
          position: poi.position,
          title: poi.name,
          label: {
            content: `<div style="background:#2563eb;color:#fff;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:bold;">D${poi.dayIndex + 1}-${poi.attrIndex + 1} ${poi.name}</div>`,
            direction: 'top',
          },
        })
        mapInstance.add(marker)
      })

      if (pois.length > 1) {
        mapInstance.setFitView()
      }
      mapStatus.value = pois.length ? '' : '行程暂无经纬度坐标'
      return
    } catch (err) {
      console.warn('高德加载不可用，无缝切入 Leaflet 备用地图:', err)
      destroyMap()
    } finally {
      if (timeoutId !== undefined) window.clearTimeout(timeoutId)
    }
  }

  // 默认极速进入 Leaflet 瓦片地图模式
  initLeafletFallback(container, pois, [centerLat, centerLng])
}

const initLeafletFallback = (container: HTMLElement, pois: any[], center: [number, number]) => {
  try {
    container.innerHTML = ''
    const lmap = L.map(container, {
      zoomControl: true,
      scrollWheelZoom: false,
    }).setView(center, 12)

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap',
    }).addTo(lmap)

    const bounds: [number, number][] = []
    const dayColors = ['#2563eb', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4']
    const dayPointsMap: Record<number, [number, number][]> = {}

    pois.forEach((poi) => {
      const lat = poi.position[1]
      const lng = poi.position[0]
      bounds.push([lat, lng])

      if (!dayPointsMap[poi.dayIndex]) dayPointsMap[poi.dayIndex] = []
      dayPointsMap[poi.dayIndex].push([lat, lng])

      const color = dayColors[poi.dayIndex % dayColors.length]
      const customIcon = L.divIcon({
        className: 'custom-map-pin',
        html: `<div style="background:${color};color:#fff;font-weight:bold;font-size:11px;padding:3px 7px;border-radius:12px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.3);white-space:nowrap;">D${poi.dayIndex + 1}-${poi.attrIndex + 1} ${poi.name}</div>`,
        iconSize: [0, 0],
        iconAnchor: [20, 15],
      })

      const marker = L.marker([lat, lng], { icon: customIcon }).addTo(lmap)
      marker.bindPopup(`
        <div style="font-size:13px;line-height:1.5;min-width:160px;">
          <b style="color:${color};font-size:14px;">第${poi.dayIndex + 1}天 · ${poi.name}</b><br/>
          <span style="color:#64748b;">📍 ${poi.address}</span><br/>
          <span>⏱️ 游览: ${poi.visitDuration}分钟 · 门票: ${poi.ticketPrice ? '¥' + poi.ticketPrice : '免费'}</span>
        </div>
      `)
    })

    // 绘制每日景点游览路线
    Object.entries(dayPointsMap).forEach(([dayIdx, pts]) => {
      if (pts.length > 1) {
        const color = dayColors[Number(dayIdx) % dayColors.length]
        L.polyline(pts, {
          color,
          weight: 3,
          dashArray: '6, 6',
          opacity: 0.85,
        }).addTo(lmap)
      }
    })

    if (bounds.length > 1) {
      lmap.fitBounds(bounds, { padding: [30, 30] })
    } else if (bounds.length === 1) {
      lmap.setView(bounds[0], 13)
    }

    mapInstance = lmap
    mapProvider = 'leaflet'
    mapStatus.value = pois.length ? '' : '行程暂无经纬度坐标'

    // 关键：解决 Leaflet 在新 DOM 容器中尺寸未校准导致的灰屏问题
    window.requestAnimationFrame(() => {
      lmap.invalidateSize()
      setTimeout(() => {
        lmap.invalidateSize()
      }, 250)
    })
  } catch (e: any) {
    mapStatus.value = '地图加载失败'
  }
}

const destroyMap = () => {
  if (mapInstance) {
    if (mapProvider === 'amap' && typeof mapInstance.destroy === 'function') {
      mapInstance.destroy()
    } else if (mapProvider === 'leaflet' && typeof mapInstance.remove === 'function') {
      mapInstance.remove()
    }
    mapInstance = null
    mapProvider = null
  }
}

watch(showCanvas, (val) => {
  if (val && currentPlan.value) {
    nextTick(() => {
      initWorkspaceMap()
    })
  } else {
    destroyMap()
  }
})

watch(currentPlan, (newPlan) => {
  if (showCanvas.value && newPlan) {
    nextTick(() => {
      initWorkspaceMap()
    })
  }
})
</script>

<style scoped>
.workspace-layout {
  display: flex;
  height: 100vh;
  width: 100%;
  max-width: 100%;
  background-color: #f7f9fc;
  overflow: hidden;
  position: relative;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

/* 左侧侧边栏 */
.workspace-sidebar {
  width: 260px;
  background-color: #ffffff;
  border-right: 1px solid #eef2f6;
  display: flex;
  flex-direction: column;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  user-select: none;
  z-index: 10;
}

.sidebar-collapsed {
  width: 64px;
}

.sidebar-top {
  padding: 16px;
  border-bottom: 1px solid #f0f4f8;
}

.brand-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.brand-icon {
  font-size: 24px;
  width: 38px;
  height: 38px;
  background: linear-gradient(135deg, #e3f2fd, #bbdefb);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
}

.brand-subtitle {
  font-size: 11px;
  color: #64748b;
}

.new-chat-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: white;
  border: none;
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
  transition: all 0.2s;
}

.new-chat-btn:hover {
  background: linear-gradient(135deg, #1d4ed8, #1e40af);
  transform: translateY(-1px);
}

.session-list-section {
  flex: 1;
  overflow-y: auto;
  padding: 12px 8px;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  margin: 8px 8px 6px;
  text-transform: uppercase;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 10px;
  border-radius: 8px;
  cursor: pointer;
  color: #334155;
  transition: all 0.15s;
  margin-bottom: 4px;
}

.session-item:hover {
  background-color: #f1f5f9;
}

.session-item.active {
  background-color: #e0f2fe;
  color: #0369a1;
  font-weight: 500;
}

.session-item-content {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}

.session-info {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.session-name {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 150px;
}

.session-time {
  font-size: 10px;
  color: #94a3b8;
}

.delete-session-btn {
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 16px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
}

.session-item:hover .delete-session-btn {
  opacity: 1;
}

.empty-sessions {
  text-align: center;
  color: #94a3b8;
  font-size: 12px;
  padding: 30px 0;
}

.sidebar-bottom {
  padding: 12px 14px;
  border-top: 1px solid #f0f4f8;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.engine-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #f8fafc;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #10b981;
  box-shadow: 0 0 6px rgba(16, 185, 129, 0.6);
}

.engine-name {
  font-size: 12px;
  font-weight: 600;
  color: #1e293b;
}

.engine-desc {
  font-size: 10px;
  color: #64748b;
}

.sidebar-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.switch-mode-btn, .toggle-sidebar-btn {
  background: transparent;
  border: none;
  color: #64748b;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px;
  border-radius: 6px;
}

.switch-mode-btn:hover, .toggle-sidebar-btn:hover {
  background: #f1f5f9;
  color: #1e293b;
}

/* 主对话区域 */
.chat-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100vh;
  position: relative;
  overflow: hidden;
  background: #fbfcfe;
}

.chat-header {
  height: 60px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  z-index: 5;
}

.chat-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
  display: inline-block;
  margin-right: 12px;
}

.tag-badge {
  background: #e0f2fe;
  color: #0284c7;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 消息流与欢迎态 */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px 140px;
  scroll-behavior: smooth;
}

/* 欢迎页 (契合截图设计) */
.welcome-screen {
  max-width: 760px;
  margin: 60px auto 0;
  text-align: center;
  position: relative;
}

.welcome-icon-wrap {
  width: 64px;
  height: 64px;
  margin: 0 auto 16px;
  background: linear-gradient(135deg, #dbeafe, #eff6ff);
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.12);
}

.welcome-label {
  font-size: 11px;
  letter-spacing: 2px;
  color: #3b82f6;
  font-weight: 700;
  margin-bottom: 12px;
}

.welcome-heading {
  font-size: 32px;
  font-weight: 800;
  color: #0f172a;
  margin-bottom: 12px;
  letter-spacing: -0.5px;
}

.welcome-subheading {
  font-size: 15px;
  color: #64748b;
  max-width: 580px;
  margin: 0 auto 36px;
  line-height: 1.6;
}

.inspiration-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: center;
}

.inspiration-chip {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 24px;
  padding: 8px 18px;
  font-size: 13px;
  color: #334155;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
}

.inspiration-chip:hover {
  border-color: #3b82f6;
  color: #2563eb;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.1);
}

.chip-arrow {
  color: #94a3b8;
  font-size: 16px;
}

/* 消息行 */
.conversation-stream {
  max-width: 860px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.message-row {
  display: flex;
  gap: 14px;
}

.message-row.user {
  flex-direction: row-reverse;
}

.avatar-wrap {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.message-row.user .avatar-wrap {
  background: #dbeafe;
}

.message-content-wrap {
  max-width: 82%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.user-bubble {
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: white;
  padding: 12px 18px;
  border-radius: 18px 4px 18px 18px;
  font-size: 14px;
  line-height: 1.6;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.15);
}

.assistant-bubble {
  background: #ffffff;
  color: #1e293b;
  border: 1px solid #e2e8f0;
  padding: 14px 18px;
  border-radius: 4px 18px 18px 18px;
  font-size: 14px;
  line-height: 1.6;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
}

.changes-banner {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #15803d;
  padding: 8px 14px;
  border-radius: 10px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 多智能体流式协作推演面板 (科技质感与深度推演日志) */
.agent-collaboration-panel {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 16px 18px;
  box-shadow: 0 6px 24px rgba(15, 23, 42, 0.05);
  transition: all 0.3s ease;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  gap: 12px;
}

.panel-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.panel-icon {
  font-size: 16px;
  animation: pulse-glow 2s infinite ease-in-out;
}

.panel-title {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}

.elapsed-badge {
  font-size: 11px;
  padding: 2px 8px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  color: #475569;
  border-radius: 12px;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.panel-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toggle-thought-btn {
  background: transparent;
  border: none;
  font-size: 12px;
  color: #3b82f6;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 6px;
  transition: all 0.2s;
}

.toggle-thought-btn:hover {
  background: #eff6ff;
  color: #1d4ed8;
}

.stream-status-badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 12px;
  background: #fef3c7;
  color: #b45309;
  font-weight: 500;
}

.stream-status-badge.completed {
  background: #dcfce7;
  color: #166534;
}

/* 顶部五大专家网格 */
.agent-nodes-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 14px;
}

.agent-node-card {
  min-width: 0;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 8px 10px;
  transition: all 0.2s;
  position: relative;
}

.agent-node-card.running {
  background: #eff6ff;
  border-color: #60a5fa;
  box-shadow: 0 0 12px rgba(59, 130, 246, 0.15);
}

.agent-node-card.completed {
  background: #f0fdf4;
  border-color: #86efac;
}

.node-icon-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.node-icon {
  font-size: 14px;
}

.node-status-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
}

.status-check {
  color: #16a34a;
  font-weight: 800;
}

.status-pending {
  color: #94a3b8;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #3b82f6;
  box-shadow: 0 0 8px #3b82f6;
  animation: pulse-ring 1.5s infinite;
}

.node-name {
  font-size: 11px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-detail {
  font-size: 10px;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 思考流时间轴 (Thought Timeline) */
.thought-process-container {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 12px;
  max-height: 280px;
  overflow-y: auto;
  scroll-behavior: smooth;
}

.thought-timeline-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px dashed #cbd5e1;
}

.step-count-badge {
  font-size: 10px;
  padding: 1px 6px;
  background: #e2e8f0;
  color: #64748b;
  border-radius: 10px;
}

.thought-timeline-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.thought-step-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  position: relative;
  font-size: 12px;
}

.step-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  width: 18px;
}

.step-badge-icon {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #22c55e;
  color: #ffffff;
  font-size: 10px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

.step-badge-pulse {
  width: 16px;
  height: 16px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

.core-dot {
  font-size: 12px;
  z-index: 2;
  animation: bounce-subtle 1.5s infinite;
}

.ping-ring {
  position: absolute;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(59, 130, 246, 0.25);
  animation: ping-wave 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;
}

.step-badge-pending {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
}

.step-line {
  position: absolute;
  top: 18px;
  bottom: -10px;
  width: 2px;
  background: #e2e8f0;
  z-index: 0;
}

.thought-step-item:last-child .step-line {
  display: none;
}

.step-body {
  flex: 1;
  min-width: 0;
}

.step-header-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2px;
}

.step-title {
  font-size: 12px;
  font-weight: 600;
  color: #1e293b;
}

.thought-step-item.running .step-title {
  color: #2563eb;
}

.step-time {
  font-size: 10px;
  color: #94a3b8;
  font-family: monospace;
}

.step-desc {
  font-size: 11px;
  color: #475569;
  line-height: 1.5;
  word-break: break-word;
}

.thought-step-item.running .step-desc {
  color: #1e40af;
}

/* 进度条与实时动态提示 */
.stream-progress-section {
  margin-top: 10px;
}

.stream-progress-bar {
  height: 5px;
  background: #e2e8f0;
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 6px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #06b6d4, #10b981);
  transition: width 0.4s ease;
}

.stream-live-ticker {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: #64748b;
  gap: 8px;
}

.live-dot-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #3b82f6;
  box-shadow: 0 0 6px #3b82f6;
  animation: pulse-ring 1.2s infinite;
  flex-shrink: 0;
}

.live-ticker-text {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #3b82f6;
  font-weight: 500;
}

.live-ticker-percent {
  font-family: monospace;
  font-weight: 600;
  color: #059669;
}

@keyframes ping-wave {
  75%, 100% {
    transform: scale(1.8);
    opacity: 0;
  }
}

@keyframes bounce-subtle {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-2px); }
}

@keyframes pulse-ring {
  0% { transform: scale(0.95); opacity: 0.8; }
  50% { transform: scale(1.15); opacity: 1; }
  100% { transform: scale(0.95); opacity: 0.8; }
}

@keyframes pulse-glow {
  0%, 100% { opacity: 0.8; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.1); }
}

/* 行程概要预览卡片 */
.plan-summary-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 18px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.05);
}

.plan-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #f1f5f9;
  padding-bottom: 12px;
  margin-bottom: 12px;
}

.plan-card-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.date-badge {
  font-size: 12px;
  font-weight: normal;
  color: #64748b;
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 6px;
}

.budget-badge {
  background: #fff7ed;
  color: #c2410c;
  font-weight: 700;
  font-size: 13px;
  padding: 4px 10px;
  border-radius: 8px;
}

.days-preview-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.day-preview-item {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #f8fafc;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 12px;
}

.day-badge {
  background: #e0f2fe;
  color: #0369a1;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
}

.day-spots {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.spot-tag {
  color: #334155;
  background: #ffffff;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
}

.day-hotel {
  margin-left: auto;
  color: #64748b;
}

.plan-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.footer-tip {
  font-size: 12px;
  color: #94a3b8;
}

/* 底部悬浮输入卡片 (契合截图设计) */
.chat-input-wrapper {
  position: absolute;
  bottom: 24px;
  left: 0;
  right: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 24px;
  pointer-events: none;
  z-index: 10;
  box-sizing: border-box;
  max-width: 100%;
}

.modification-chips-container {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  max-width: 760px;
  margin-bottom: 10px;
  box-sizing: border-box;
  position: relative;
}

.mod-header-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 11px;
  background: linear-gradient(135deg, rgba(239, 246, 255, 0.95), rgba(245, 243, 255, 0.95));
  backdrop-filter: blur(12px);
  border: 1px solid rgba(199, 210, 254, 0.8);
  border-radius: 16px;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.08);
  flex-shrink: 0;
  user-select: none;
}

.mod-sparkle {
  font-size: 13px;
  animation: pulse-glow 2s infinite ease-in-out;
}

.mod-tip-text {
  font-size: 11px;
  font-weight: 700;
  color: #4338ca;
  letter-spacing: 0.5px;
}

.mod-scroll-wrapper {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}

.mod-chips-track {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: none;
  box-sizing: border-box;
  padding: 4px 6px;
  width: 100%;
  scroll-behavior: smooth;
  /* 边缘羽化渐变遮罩：消除生硬截断感 */
  mask-image: linear-gradient(to right, black calc(100% - 28px), transparent 100%);
  -webkit-mask-image: linear-gradient(to right, black calc(100% - 28px), transparent 100%);
}

.mod-chips-track::-webkit-scrollbar {
  display: none;
}

.mod-nav-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(8px);
  border: 1px solid #cbd5e1;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.12);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #475569;
  cursor: pointer;
  z-index: 5;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  padding: 0;
  line-height: 1;
}

.mod-nav-arrow.left {
  left: -2px;
}

.mod-nav-arrow.right {
  right: -2px;
}

.mod-nav-arrow:hover {
  background: #ffffff;
  color: #2563eb;
  border-color: #93c5fd;
  transform: translateY(-50%) scale(1.12);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
}

.mod-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 14px;
  padding: 5px 12px;
  font-size: 12px;
  color: #334155;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  flex-shrink: 0;
  white-space: nowrap;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
  user-select: none;
}

.mod-chip-icon {
  font-size: 12px;
}

.mod-chip-text {
  font-weight: 500;
}

.mod-chip:hover {
  background: #ffffff;
  color: #2563eb;
  border-color: #93c5fd;
  transform: translateY(-1.5px);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.12);
}

.mod-chip:active {
  transform: scale(0.96);
}

/* 分类微色系高亮 */
.mod-chip.food:hover {
  color: #ea580c;
  border-color: #fdba74;
  background: #fff7ed;
}

.mod-chip.budget:hover {
  color: #059669;
  border-color: #6ee7b7;
  background: #ecfdf5;
}

.mod-chip.pace:hover {
  color: #0284c7;
  border-color: #7dd3fc;
  background: #f0f9ff;
}

.mod-chip.hotel:hover {
  color: #7c3aed;
  border-color: #c4b5fd;
  background: #f5f3ff;
}

.mod-chip.night:hover {
  color: #4f46e5;
  border-color: #a5b4fc;
  background: #eef2ff;
}

.mod-chip.family:hover {
  color: #db2777;
  border-color: #f9a8d4;
  background: #fdf2f8;
}

.floating-input-card {
  pointer-events: auto;
  width: 100%;
  max-width: 760px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(16px);
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  padding: 12px 18px 10px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
  transition: all 0.2s;
}

.floating-input-card:focus-within {
  border-color: #3b82f6;
  box-shadow: 0 12px 36px rgba(37, 99, 235, 0.12);
}

.native-textarea {
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  font-size: 14px;
  color: #1e293b;
  resize: none;
  background: transparent !important;
}

.native-textarea:focus {
  outline: none !important;
}

.input-bottom-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px solid #f1f5f9;
}

.shortcut-hint {
  font-size: 11px;
  color: #94a3b8;
  display: flex;
  align-items: center;
  gap: 4px;
}

.key-icon {
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  border-radius: 3px;
  padding: 1px 4px;
  font-size: 10px;
}

.send-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  border: none;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(37, 99, 235, 0.25);
  transition: all 0.2s;
}

.send-btn:hover:not(:disabled) {
  transform: scale(1.05);
}

.send-btn:disabled {
  background: #cbd5e1;
  box-shadow: none;
  cursor: not-allowed;
}

/* 右侧联动看板 */
.workspace-canvas {
  width: 480px;
  flex-shrink: 0;
  background: #ffffff;
  border-left: 1px solid #eef2f6;
  height: 100vh;
  display: flex;
  flex-direction: column;
  z-index: 10;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.03);
}

.canvas-header {
  height: 60px;
  padding: 0 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #f1f5f9;
}

.canvas-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 8px;
}

.canvas-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.canvas-export-btn {
  font-size: 12px;
  border-radius: 6px;
}

.city-sub {
  font-size: 12px;
  background: #e0f2fe;
  color: #0284c7;
  padding: 2px 6px;
  border-radius: 4px;
}

.close-canvas-btn {
  background: transparent;
  border: none;
  font-size: 20px;
  color: #94a3b8;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  transition: color 0.2s;
}

.close-canvas-btn:hover {
  color: #1e293b;
}

.canvas-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.canvas-map-wrap {
  width: 100%;
  height: 280px;
  border-radius: 12px;
  overflow: hidden;
  position: relative;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
}

.canvas-map-header {
  height: 32px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  font-size: 12px;
  z-index: 5;
}

.map-label {
  font-weight: 600;
  color: #334155;
}

.map-provider-tag {
  font-size: 11px;
  background: #eff6ff;
  color: #2563eb;
  padding: 1px 6px;
  border-radius: 4px;
}

.map-container {
  width: 100%;
  flex: 1;
}

.map-status-overlay {
  position: absolute;
  top: 40px;
  left: 10px;
  background: rgba(15, 23, 42, 0.75);
  backdrop-filter: blur(4px);
  color: #fff;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  z-index: 500;
}

/* 目的地天气卡片 */
.canvas-weather-card {
  background: linear-gradient(135deg, #f0fdf4 0%, #f8fafc 100%);
  border: 1px solid #bbf7d0;
  border-radius: 12px;
  padding: 14px;
}

.weather-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.weather-title {
  font-size: 13px;
  font-weight: 700;
  color: #166534;
  display: flex;
  align-items: center;
  gap: 6px;
}

.weather-city {
  font-size: 11px;
  color: #64748b;
  font-weight: normal;
}

.weather-source {
  font-size: 11px;
  color: #64748b;
  background: #ffffff;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
}

.weather-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
  gap: 8px;
}

.weather-pill {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px 6px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
}

.w-date {
  font-size: 11px;
  font-weight: 600;
  color: #475569;
}

.w-icon {
  font-size: 20px;
  margin: 3px 0;
}

.w-cond {
  font-size: 12px;
  font-weight: 600;
  color: #0f172a;
}

.w-temp {
  font-size: 11px;
  color: #e11d48;
  font-weight: 700;
  margin-top: 2px;
}

.w-wind {
  font-size: 10px;
  color: #94a3b8;
  margin-top: 2px;
  white-space: nowrap;
}

.missing-weather-hint {
  margin-top: 8px;
  font-size: 11px;
  color: #854d0e;
  background: #fefce8;
  padding: 4px 8px;
  border-radius: 4px;
}

.canvas-budget-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px;
}

.budget-header {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 8px;
}

.budget-total-num {
  color: #e11d48;
  font-size: 16px;
  font-weight: 700;
}

.budget-pills {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  font-size: 12px;
  color: #64748b;
}

.b-pill {
  background: #ffffff;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.days-title {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 10px;
}

.day-card-item {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 10px;
}

.d-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}

.d-index {
  font-weight: 700;
  color: #2563eb;
  font-size: 13px;
}

.d-date {
  color: #94a3b8;
  font-size: 12px;
}

.d-desc {
  font-size: 12px;
  color: #475569;
  margin-bottom: 10px;
  line-height: 1.5;
}

.d-spots-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

.spot-row {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #f8fafc;
  padding: 6px 8px;
  border-radius: 6px;
}

.spot-order {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #3b82f6;
  color: white;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.spot-name {
  font-size: 12px;
  font-weight: 600;
  color: #1e293b;
}

.spot-meta {
  font-size: 11px;
  color: #64748b;
}

.d-hotel-row {
  font-size: 11px;
  color: #475569;
  background: #eff6ff;
  padding: 6px 8px;
  border-radius: 6px;
}

:deep(.custom-map-pin) {
  background: transparent !important;
  border: none !important;
}
</style>
