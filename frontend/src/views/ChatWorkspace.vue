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

                <!-- 前置行程参数快速确认胶囊 (Pre-Trip Parameter Card) -->
                <div class="pre-trip-param-card" v-if="msg.isParamConfirmPending && msg.pendingParams">
                  <div class="param-card-header">
                    <div class="param-header-left">
                      <span class="param-badge-icon">🧭</span>
                      <div class="param-title-box">
                        <div class="param-card-title">
                          {{ msg.pendingParams.has_explicit_duration ? `出发时间确认 · ${msg.pendingParams.travel_days}日深度游` : '行程基准要素确认' }}
                        </div>
                        <div class="param-card-subtitle">
                          {{ msg.pendingParams.has_explicit_duration ? `已锁定 ${msg.pendingParams.travel_days} 天行程容量与偏好，请点选您的出发日期以精准锁定高德实时气象与开闭馆排期` : '已为您锁定目标城市，可快速微调出发时间与偏好，确保高德气象与推荐容量严密吻合' }}
                        </div>
                      </div>
                    </div>
                    <span class="param-status-tag">{{ msg.pendingParams.has_explicit_duration ? '请定出发日' : '待核对' }}</span>
                  </div>

                  <div class="param-form-grid">
                    <!-- 目的地城市 -->
                    <div class="param-grid-item">
                      <label class="param-label">📍 目的地城市</label>
                      <input
                        type="text"
                        class="param-input"
                        v-model="msg.pendingParams.city"
                        placeholder="输入城市名称"
                      />
                    </div>

                    <!-- 出行日期与天数 -->
                    <div class="param-grid-item dates-item">
                      <label class="param-label">📅 出发与返程日期</label>
                      <div class="param-date-row">
                        <input
                          type="date"
                          class="param-input date-input"
                          :value="msg.pendingParams.start_date"
                          @change="(e: any) => handlePreParamDateChange(msg, 'start', e.target.value)"
                        />
                        <span class="date-sep">至</span>
                        <input
                          type="date"
                          class="param-input date-input"
                          :value="msg.pendingParams.end_date"
                          @change="(e: any) => handlePreParamDateChange(msg, 'end', e.target.value)"
                        />
                        <span class="param-days-badge">共 {{ msg.pendingParams.travel_days }} 天</span>
                      </div>
                    </div>

                    <!-- 旅行偏好选择 -->
                    <div class="param-grid-item full-width">
                      <label class="param-label">✨ 旅行偏好风格</label>
                      <div class="param-pref-tags">
                        <span
                          v-for="pref in ['历史文化', '特色美食', '自然风光', '休闲度假', '亲子娱乐', '网红打卡']"
                          :key="pref"
                          class="pref-choice-pill"
                          :class="{ active: (msg.pendingParams.preferences || []).includes(pref) }"
                          @click="togglePreParamPreference(msg, pref)"
                        >
                          {{ pref }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div class="param-card-actions">
                    <button
                      type="button"
                      class="param-confirm-btn primary"
                      @click="handleConfirmPreParams(msg, false)"
                    >
                      🚀 确认参数 · 启动多智能体推演
                    </button>
                    <button
                      type="button"
                      class="param-confirm-btn secondary"
                      @click="handleConfirmPreParams(msg, true)"
                      title="直接使用默认推算的近期时间开始规划"
                    >
                      ⚡ 按默认近期直出
                    </button>
                  </div>
                </div>

                <!-- In-Chat HITL 人机协同候选确认卡片 (当进入协同挂起状态或已确认时展示) -->
                <div
                  class="in-chat-hitl-card"
                  v-if="msg.hitlCandidateData"
                  :class="{ 'is-confirmed': msg.hitlConfirmed }"
                >
                  <div class="hitl-card-header">
                    <div class="hitl-header-main">
                      <span class="hitl-badge-icon">🤝</span>
                      <div class="hitl-title-box">
                        <div class="hitl-title">人机协同候选确认中心 (In-Chat HITL)</div>
                        <div class="hitl-subtitle">
                          多智能体已完成数据采集并挂起，请勾选您中意的景点与住宿注入规划
                        </div>
                      </div>
                    </div>
                    <div class="hitl-status-pill" :class="{ confirmed: msg.hitlConfirmed }">
                      {{ msg.hitlConfirmed ? '✓ 协同决策已锁定' : '⏳ 等待您的确认' }}
                    </div>
                  </div>

                  <!-- 出行周期轻量确认/微调条 -->
                  <div class="hitl-date-bar">
                    <div class="date-bar-left">
                      <span class="date-bar-icon">📅</span>
                      <span class="date-bar-label">出行周期确认：</span>
                      <div class="date-inputs-wrap" v-if="!msg.hitlConfirmed">
                        <input
                          type="date"
                          class="hitl-date-input"
                          :value="msg.hitlStartDate"
                          @change="(e: any) => handleHitlDateChange(msg, 'start', e.target.value)"
                          title="点击修改出发日期"
                        />
                        <span class="date-separator">至</span>
                        <input
                          type="date"
                          class="hitl-date-input"
                          :value="msg.hitlEndDate"
                          @change="(e: any) => handleHitlDateChange(msg, 'end', e.target.value)"
                          title="点击修改返程日期"
                        />
                        <span class="date-days-pill">共 {{ msg.hitlTravelDays || msg.hitlCandidateData.travel_days || 1 }} 天</span>
                      </div>
                      <span class="date-confirmed-val" v-else>
                        {{ msg.hitlStartDate || '未设定' }} 至 {{ msg.hitlEndDate || '未设定' }} (共 {{ msg.hitlTravelDays || msg.hitlCandidateData.travel_days || 1 }} 天)
                      </span>
                    </div>
                    <span class="date-tip-sub" v-if="!msg.hitlConfirmed">
                      💡 默认自动推算近期出发，点击日期可直接校准真实行程时间
                    </span>
                  </div>

                  <!-- 天数/时效失配预警与一键重查条 (Invalidation & Re-search) -->
                  <div
                    class="hitl-stale-warning"
                    v-if="!msg.hitlConfirmed && msg.initialTravelDays && msg.hitlTravelDays !== msg.initialTravelDays"
                  >
                    <div class="stale-warning-content">
                      <span class="stale-warning-icon">⚠️</span>
                      <div class="stale-warning-info">
                        <div class="stale-title">游玩天数由 <strong>{{ msg.initialTravelDays }}天</strong> 调整为 <strong>{{ msg.hitlTravelDays }}天</strong></div>
                        <div class="stale-desc">
                          原有候选景点池（共 {{ msg.hitlCandidateData.candidate_attractions?.length || 0 }} 处）与气象基于原周期采集，建议重新检索以匹配更多路线与适期气象。
                        </div>
                      </div>
                    </div>
                    <button
                      type="button"
                      class="hitl-refresh-btn"
                      :disabled="msg.hitlRefreshing"
                      @click="handleRefreshHitlCandidates(msg)"
                    >
                      {{ msg.hitlRefreshing ? '🔄 正在同步...' : '🔄 重新匹配新周期候选' }}
                    </button>
                  </div>

                  <!-- 目的地未来气象胶囊横条 -->
                  <div
                    class="hitl-weather-bar"
                    v-if="msg.hitlCandidateData.weather_info && msg.hitlCandidateData.weather_info.length > 0"
                  >
                    <span class="weather-bar-title">🌤️ 目的地未来气象参考：</span>
                    <div class="weather-bar-tags">
                      <span
                        v-for="w in msg.hitlCandidateData.weather_info"
                        :key="w.date"
                        class="weather-mini-tag"
                      >
                        {{ formatShortDate(w.date) }} {{ getWeatherEmoji(w.day_weather) }} {{ w.day_weather }} ({{ w.night_temp }}°~{{ w.day_temp }}°C)
                      </span>
                    </div>
                  </div>

                  <!-- 知识库权威攻略提醒横条 (RAG 增强) -->
                  <div
                    class="hitl-knowledge-bar"
                    v-if="msg.hitlCandidateData.knowledge_highlights && msg.hitlCandidateData.knowledge_highlights.length > 0"
                  >
                    <span class="knowledge-bar-title">🏛️ 官方知识库放票与避坑提醒：</span>
                    <div class="knowledge-bar-tags">
                      <div
                        v-for="(tip, kIdx) in msg.hitlCandidateData.knowledge_highlights"
                        :key="kIdx"
                        class="knowledge-mini-tag"
                      >
                        {{ tip }}
                      </div>
                    </div>
                  </div>

                  <!-- 候选景点多选区 -->
                  <div class="hitl-section">
                    <div class="hitl-section-header">
                      <div class="section-title">
                        <span>📍 候选核心景点</span>
                        <span class="count-tag">
                          已勾选 <strong>{{ (msg.hitlSelectedAttractions || []).length }}</strong> / {{ msg.hitlCandidateData.candidate_attractions?.length || 0 }} 处
                        </span>
                      </div>
                      <div class="section-actions" v-if="!msg.hitlConfirmed">
                        <button type="button" class="mini-text-btn" @click="selectAllHitlAttractions(msg)">全选</button>
                        <span class="divider">|</span>
                        <button type="button" class="mini-text-btn" @click="clearHitlAttractions(msg)">清空</button>
                      </div>
                    </div>

                    <div class="hitl-attractions-grid">
                      <div
                        v-for="poi in msg.hitlCandidateData.candidate_attractions"
                        :key="poi.name"
                        class="hitl-poi-card"
                        :class="{
                          'is-selected': (msg.hitlSelectedAttractions || []).includes(poi.name),
                          'is-disabled': msg.hitlConfirmed
                        }"
                        @click="!msg.hitlConfirmed && toggleHitlAttraction(msg, poi.name)"
                      >
                        <div class="poi-checkbox">
                          <span class="check-icon" v-if="(msg.hitlSelectedAttractions || []).includes(poi.name)">✓</span>
                        </div>
                        <div class="poi-details">
                          <div class="poi-top-row">
                            <span class="poi-name" :title="poi.name">{{ poi.name }}</span>
                            <span class="poi-rating" v-if="poi.rating">⭐ {{ poi.rating }}</span>
                          </div>
                          <div class="poi-mid-row">
                            <span class="poi-type" v-if="poi.type">{{ poi.type.split(';')[0] }}</span>
                          </div>
                          <div class="poi-address" :title="poi.address">{{ poi.address || '地址详见行程地图' }}</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- 候选酒店单选区 -->
                  <div
                    class="hitl-section"
                    v-if="msg.hitlCandidateData.candidate_hotels && msg.hitlCandidateData.candidate_hotels.length > 0"
                  >
                    <div class="hitl-section-header">
                      <div class="section-title">
                        <span>🏨 候选推荐住宿（单选）</span>
                      </div>
                    </div>

                    <div class="hitl-hotels-grid">
                      <div
                        v-for="hotel in msg.hitlCandidateData.candidate_hotels"
                        :key="hotel.name"
                        class="hitl-hotel-card"
                        :class="{
                          'is-selected': msg.hitlSelectedHotel === hotel.name,
                          'is-disabled': msg.hitlConfirmed
                        }"
                        @click="!msg.hitlConfirmed && selectHitlHotel(msg, hotel.name)"
                      >
                        <div class="hotel-radio">
                          <span class="radio-core" v-if="msg.hitlSelectedHotel === hotel.name"></span>
                        </div>
                        <div class="hotel-details">
                          <div class="hotel-top-row">
                            <span class="hotel-name" :title="hotel.name">{{ hotel.name }}</span>
                            <span class="hotel-price" v-if="hotel.price_range">{{ hotel.price_range }}</span>
                          </div>
                          <div class="hotel-meta">
                            <span class="hotel-rating" v-if="hotel.rating">⭐ {{ hotel.rating }}</span>
                            <span class="hotel-tag" v-if="hotel.tag">{{ hotel.tag }}</span>
                            <span
                              class="hotel-distance"
                              v-if="getHotelDistanceDisplay(hotel, msg.hitlCandidateData.candidate_attractions)"
                              :title="getHotelDistanceDisplay(hotel, msg.hitlCandidateData.candidate_attractions)"
                            >
                              📍 {{ getHotelDistanceDisplay(hotel, msg.hitlCandidateData.candidate_attractions) }}
                            </span>
                          </div>
                          <div class="hotel-address" :title="hotel.address">{{ hotel.address || '核心商圈' }}</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- 补充微调偏好输入 -->
                  <div class="hitl-feedback-box" v-if="!msg.hitlConfirmed">
                    <div class="feedback-title">
                      <span>✍️ 补充定制意见或特殊偏好（选填）：</span>
                    </div>
                    <a-input
                      v-model:value="msg.hitlUserFeedback"
                      placeholder="例如：第一天想先在酒店周边简单逛逛，少走路；多安排老字号美食..."
                      :disabled="msg.hitlConfirmed || msg.hitlSubmitting"
                      class="hitl-feedback-input"
                      @keydown.enter.stop="handleConfirmInChatHitl(msg)"
                    />
                  </div>
                  <div class="hitl-feedback-display" v-else-if="msg.hitlUserFeedback">
                    <span class="fb-tag">定制偏好：</span>
                    <span class="fb-content">{{ msg.hitlUserFeedback }}</span>
                  </div>

                  <!-- 卡片底部操作栏 -->
                  <div class="hitl-footer">
                    <div class="hitl-footer-summary">
                      已选 <strong>{{ (msg.hitlSelectedAttractions || []).length }}</strong> 处景点，
                      住宿：<strong>{{ msg.hitlSelectedHotel || '自动推荐' }}</strong>
                    </div>
                    <div class="hitl-footer-btns">
                      <button
                        type="button"
                        class="hitl-btn-skip"
                        v-if="!msg.hitlConfirmed"
                        :disabled="msg.hitlSubmitting"
                        @click="handleSkipHitlToAuto(msg)"
                        title="采用默认推荐的全部候选并直接规划"
                      >
                        ⚡ 全部推荐
                      </button>
                      <button
                        type="button"
                        class="hitl-btn-confirm"
                        :class="{ loading: msg.hitlSubmitting, confirmed: msg.hitlConfirmed }"
                        :disabled="msg.hitlConfirmed || msg.hitlSubmitting"
                        @click="handleConfirmInChatHitl(msg)"
                      >
                        <span v-if="msg.hitlSubmitting">🚀 规划引擎融合计算中...</span>
                        <span v-else-if="msg.hitlConfirmed">✓ 协同方案已执行</span>
                        <span v-else>✓ 确认选择并开始时空规划</span>
                      </button>
                    </div>
                  </div>
                </div>

                <!-- 生成成功的行程概要预览卡片 (全新现代卡片化排版) -->
                <div class="plan-summary-card" v-if="msg.planData">
                  <div class="plan-card-header">
                    <div class="plan-card-header-left">
                      <div class="plan-header-icon">🗺️</div>
                      <div class="plan-header-titles">
                        <div class="plan-main-title">
                          {{ msg.planData.city }} {{ msg.planData.days.length }}天深度旅行规划
                        </div>
                        <div class="plan-sub-meta">
                          <span class="date-badge">📅 {{ msg.planData.start_date }} ~ {{ msg.planData.end_date }}</span>
                          <span class="days-count-badge">{{ msg.planData.days.length }}天精炼动线</span>
                        </div>
                      </div>
                    </div>
                    <div class="plan-card-header-right" v-if="msg.planData.budget">
                      <div class="budget-badge-premium">
                        <span class="budget-label">预估总费用</span>
                        <span class="budget-amount">¥{{ msg.planData.budget.total }}</span>
                      </div>
                    </div>
                  </div>

                  <!-- 官方知识库权威亮点提醒 (RAG 增强) -->
                  <div
                    class="plan-knowledge-highlights-strip"
                    v-if="msg.planData.knowledge_highlights && msg.planData.knowledge_highlights.length > 0"
                  >
                    <span class="kh-strip-title">🏛️ 权威攻略速记：</span>
                    <div class="kh-strip-tags">
                      <span
                        v-for="(tip, kIdx) in msg.planData.knowledge_highlights"
                        :key="kIdx"
                        class="kh-tag-pill"
                      >
                        {{ tip }}
                      </span>
                    </div>
                  </div>

                  <!-- 每日精细规划卡片流水线 -->
                  <div class="days-preview-grid">
                    <div
                      v-for="d in msg.planData.days"
                      :key="d.day_index"
                      class="day-preview-item"
                    >
                      <!-- 每日顶栏：Day 徽标 + 主题描述 + 交通 -->
                      <div class="day-item-topbar">
                        <div class="day-item-title-box">
                          <span class="day-badge">Day {{ d.day_index + 1 }}</span>
                          <span class="day-date-tag">{{ formatShortDate(d.date) }}</span>
                          <span class="day-desc-text" :title="d.description">{{ d.description }}</span>
                        </div>
                        <div class="day-item-meta-badges">
                          <span class="day-traffic-tag" v-if="d.transportation">
                            🚗 {{ d.transportation }}
                          </span>
                        </div>
                      </div>

                      <!-- 游览景点动线 (带次序箭头与信息) -->
                      <div class="day-spots-route-wrap">
                        <div class="spots-route-label">游览动线:</div>
                        <div class="spots-route-list">
                          <template v-for="(a, aIdx) in d.attractions" :key="a.name">
                            <div class="spot-route-chip" :title="a.booking_tips || a.tips || a.description">
                              <span class="spot-order-num">{{ aIdx + 1 }}</span>
                              <span class="spot-chip-name">{{ a.name }}</span>
                              <span class="spot-chip-duration" v-if="a.visit_duration">{{ a.visit_duration }}min</span>
                              <span class="spot-chip-price" v-if="a.ticket_price">¥{{ a.ticket_price }}</span>
                              <span class="spot-chip-rag-dot" v-if="a.booking_tips || a.tips" title="含官方避坑与放票须知">📌</span>
                            </div>
                            <span class="route-arrow-icon" v-if="aIdx < d.attractions.length - 1">➔</span>
                          </template>
                        </div>
                      </div>

                      <!-- 美食餐饮推荐 (紧凑条) -->
                      <div class="day-meals-strip" v-if="d.meals && d.meals.length > 0">
                        <span class="meals-label">🍽️ 特色餐饮:</span>
                        <div class="meals-tags">
                          <span v-for="m in d.meals" :key="m.type" class="meal-tag">
                            <strong class="meal-type">{{ m.type === 'breakfast' ? '早' : m.type === 'lunch' ? '午' : m.type === 'dinner' ? '晚' : '味' }}:</strong>
                            {{ m.name }}
                          </span>
                        </div>
                      </div>

                      <!-- 住宿推荐条 (独立横栏对齐，带精准距离) -->
                      <div class="day-hotel-card" v-if="d.hotel">
                        <div class="hotel-card-left">
                          <span class="hotel-lead-icon">🏨</span>
                          <span class="hotel-lead-text">推荐住宿:</span>
                          <span class="hotel-title-text" :title="d.hotel.name">{{ d.hotel.name }}</span>
                          <span class="hotel-price-pill" v-if="d.hotel.price_range">{{ d.hotel.price_range }}</span>
                          <span class="hotel-rating-pill" v-if="d.hotel.rating">⭐ {{ d.hotel.rating }}</span>
                        </div>
                        <div class="hotel-card-right" v-if="d.hotel.distance">
                          <span class="hotel-distance-pill" :title="d.hotel.distance">
                            📍 {{ d.hotel.distance }}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- 卡片操作底部工具栏 -->
                  <div class="plan-card-footer">
                    <span class="footer-tip">💡 您可以直接在下方输入修改意见（如：“把第2天的故宫换成颐和园”）</span>
                    <a-button type="primary" size="middle" class="canvas-open-btn" @click="openCanvasWithPlan(msg.planData)">
                      <span>在右侧看板查看完整地图路线 →</span>
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
            <div class="bar-left-controls">
              <button
                type="button"
                class="hitl-toggle-pill"
                :class="{ active: isHitlEnabled }"
                @click="isHitlEnabled = !isHitlEnabled"
                :title="isHitlEnabled ? '点击关闭人机协同，恢复全自动流式规划' : '点击开启人机协同(HITL)，将在规划前由您亲自挑选候选景点与酒店'"
              >
                <span class="hitl-pill-dot"></span>
                <span class="hitl-pill-icon">{{ isHitlEnabled ? '🤝' : '🤖' }}</span>
                <span class="hitl-pill-text">人机协同 (HITL)</span>
                <span class="hitl-pill-tag">{{ isHitlEnabled ? '已开启' : '自动' }}</span>
              </button>
              <div class="shortcut-hint">
                <span class="key-icon">⇧</span> Shift + Enter 换行
              </div>
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
              <span>🏨 <strong>酒店:</strong> {{ day.hotel.name }} ({{ day.hotel.price_range }})</span>
              <span class="d-hotel-distance-tag" v-if="day.hotel.distance"> · 📍 {{ day.hotel.distance }}</span>
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
import type { TripPlan, TripFormData, ChatMessage, ChatSession, AgentNodeStatus, StreamEvent, POIInfo } from '@/types'
import {
  generateTripPlanStream,
  chatModifyTripPlan,
  parseNaturalLanguageTrip,
  routeChatIntent,
  prepareTripPlan,
  confirmTripPlan,
} from '@/services/api'

const router = useRouter()

// 侧边栏与布局状态
const sidebarCollapsed = ref(false)
const showCanvas = ref(false)
const isLoading = ref(false)
const isHitlEnabled = ref(false)
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

  // 彻底废除前端客户端正则，全权委托大模型语义意图路由 (/api/trip/chat/intent)：
  let isNewPlan = false
  let parsedFormData: TripFormData | null = null

  try {
    const routeRes = await routeChatIntent({
      text,
      has_current_plan: Boolean(currentPlan.value),
      current_city: currentPlan.value?.city || '',
      chat_history: messages.value.slice(-6).map(m => ({ role: m.role, content: m.content })),
    })

    if (routeRes.success && routeRes.data) {
      isNewPlan = routeRes.data.intent === 'new_plan'
      if (isNewPlan && routeRes.data.parsed_form_data) {
        parsedFormData = routeRes.data.parsed_form_data
      }
    } else {
      isNewPlan = !currentPlan.value
    }
  } catch (routeErr) {
    console.warn('语义路由请求异常，采用上下文保底策略:', routeErr)
    isNewPlan = !currentPlan.value
  }

  if (isNewPlan) {
    try {
      if (!parsedFormData) {
        parsedFormData = await parseNaturalLanguageTrip(text)
      }

      // 只要用户未明确指定具体的出发时间（哪怕提到了4天等时长），都挂载前置参数确认胶囊
      const isStartDateExplicit = Boolean(parsedFormData.has_explicit_start_date)
      if (!isStartDateExplicit) {
        const assistantMsgId = 'assistant_pre_' + Date.now()
        const promptContent = parsedFormData.clarification_prompt || (
          parsedFormData.has_explicit_duration
            ? `已为您锁定目的地【${parsedFormData.city}】与【${parsedFormData.travel_days}日游】。为了精准匹配高德实时气象与景区开闭馆排期，请问您打算哪天出发呢？`
            : `已为您识别目的地【${parsedFormData.city}】。为了确保高德实时气象与推荐景点的时空容量严密吻合，建议核对出发时间与偏好：`
        )
        const assistantMsg = reactive<ChatMessage>({
          id: assistantMsgId,
          role: 'assistant',
          content: promptContent,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          loading: false,
          isParamConfirmPending: true,
          pendingParams: { ...parsedFormData },
        })
        messages.value.push(assistantMsg)
        scrollToBottom()
        return
      }

      // 若大模型判定已明确给出出发日期（如明天/下周五/10月1日），则零打断直通执行！
      if (isHitlEnabled.value) {
        await handleChatHitlPreparation(parsedFormData)
      } else {
        await handleChatStreamingGeneration(parsedFormData)
      }
    } catch (err: any) {
      message.error('新建规划意图解析失败: ' + (err.message || err))
    }
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
const handleChatStreamingGeneration = async (input: string | TripFormData, existingMsg?: ChatMessage) => {
  isLoading.value = true
  resetAgentNodes()

  const assistantMsg = existingMsg || reactive<ChatMessage>({
    id: 'assistant_' + Date.now(),
    role: 'assistant',
    content: '收到您的旅行需求，正在启动 LangGraph 多智能体专家协同规划...',
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    loading: true,
    streamEvents: [],
    thoughtSteps: [],
    thoughtElapsed: 0,
    isThoughtExpanded: true,
  })
  if (!existingMsg) {
    messages.value.push(assistantMsg)
  }
  assistantMsg.loading = true
  assistantMsg.isParamConfirmPending = false
  scrollToBottom()

  let elapsedTimer: any = null

  try {
    const parsedFormData = typeof input === 'string' ? await parseNaturalLanguageTrip(input) : input
    assistantMsg.content = `已锁定目的地【${parsedFormData.city}】，出行周期 ${parsedFormData.start_date} ~ ${parsedFormData.end_date}（共 ${parsedFormData.travel_days} 天）。多智能体系统正在并行搜集地点与天气...`

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

// 场景二：人机协同 (HITL) 阶段一 —— 并行收集候选资源并挂起等待用户确认
const handleChatHitlPreparation = async (input: string | TripFormData, existingMsg?: ChatMessage) => {
  isLoading.value = true
  resetAgentNodes()

  const assistantMsg = existingMsg || reactive<ChatMessage>({
    id: 'assistant_' + Date.now(),
    role: 'assistant',
    content: '收到旅行需求，已启动人机协同模式 (HITL)。正在并行搜集真实景点、气象与酒店候选...',
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    loading: true,
    streamEvents: [{ event: 'start', message: '启动人机协同候选收集' }],
    thoughtSteps: [],
    thoughtElapsed: 0,
    isThoughtExpanded: true,
  })
  if (!existingMsg) {
    messages.value.push(assistantMsg)
  }
  assistantMsg.loading = true
  assistantMsg.isParamConfirmPending = false
  scrollToBottom()

  let elapsedTimer: any = setInterval(() => {
    if (assistantMsg.thoughtElapsed !== undefined) {
      assistantMsg.thoughtElapsed += 1
    }
  }, 1000)

  try {
    const parsedFormData = typeof input === 'string' ? await parseNaturalLanguageTrip(input) : input
    assistantMsg.content = `已锁定目的地【${parsedFormData.city}】，计划出行 ${parsedFormData.start_date} ~ ${parsedFormData.end_date}（共 ${parsedFormData.travel_days} 天）。多智能体系统正在检索高德候选资源与气象环境...`

    assistantMsg.thoughtSteps = [
      {
        id: 'step_hitl_init_' + Date.now(),
        title: '🛫 初始化人机协同规划任务',
        stage: '任务初始化',
        detail: `锁定目标城市【${parsedFormData.city}】，游玩 ${parsedFormData.travel_days} 天，启动 HITL 候选阶段`,
        status: 'completed',
        elapsedSeconds: 0,
      },
      {
        id: 'step_hitl_fetch_' + Date.now(),
        title: '🌐 多智能体并行搜集候选资源',
        stage: '并行收集',
        detail: '景点搜索专家、天气查询专家与酒店推荐专家正在并行执行高德 API 检索...',
        status: 'running',
        elapsedSeconds: assistantMsg.thoughtElapsed,
      }
    ]
    currentLiveStepText.value = '多智能体并行检索候选景点、天气与酒店...'

    // 2. 调用 prepareTripPlan 在 planner 节点前触发 LangGraph 挂起
    const res = await prepareTripPlan(parsedFormData)

    clearInterval(elapsedTimer)
    elapsedTimer = null

    if (res.success && res.data) {
      const candidateData = res.data

      // 点亮前三个并行搜索专家
      const attNode = currentAgentNodes.value.find(n => n.key === 'attractions')
      if (attNode) {
        attNode.status = 'completed'
        attNode.detail = `已获取 ${candidateData.candidate_attractions?.length || 0} 处候选景点`
      }
      const weaNode = currentAgentNodes.value.find(n => n.key === 'weather')
      if (weaNode) {
        weaNode.status = 'completed'
        weaNode.detail = `已锁定 ${candidateData.weather_info?.length || 0} 天气象数据`
      }
      const hotNode = currentAgentNodes.value.find(n => n.key === 'hotels')
      if (hotNode) {
        hotNode.status = 'completed'
        hotNode.detail = `已筛选 ${candidateData.candidate_hotels?.length || 0} 家推荐住宿`
      }

      // 规划专家标记为等待用户确认
      const planNode = currentAgentNodes.value.find(n => n.key === 'planner')
      if (planNode) {
        planNode.status = 'pending'
        planNode.detail = '等待用户挑选确认'
      }

      streamProgress.value = 50
      currentLiveStepText.value = '候选数据已采集完毕，等待用户确认选择'

      // 更新推演思考链路
      markLastRunningStepDone(assistantMsg)
      assistantMsg.thoughtSteps = [
        ...(assistantMsg.thoughtSteps || []),
        {
          id: 'step_hitl_interrupt_' + Date.now(),
          title: '🤝 候选收集完毕 · LangGraph 触发协同挂起 (Interrupt)',
          stage: '人机协同挂起',
          detail: `已锁定 ${candidateData.candidate_attractions?.length || 0} 处真实景点与 ${candidateData.candidate_hotels?.length || 0} 家优选住宿。LangGraph 执行在 planner 节点前挂起，等待您在下方卡片中确认挑选。`,
          status: 'completed',
          elapsedSeconds: assistantMsg.thoughtElapsed,
        }
      ]

      // 挂载候选数据与默认预选
      assistantMsg.hitlCandidateData = candidateData
      const defaultAttractions = (candidateData.candidate_attractions || [])
        .slice(0, Math.min(5, candidateData.candidate_attractions.length))
        .map(a => a.name)
      assistantMsg.hitlSelectedAttractions = defaultAttractions
      assistantMsg.hitlSelectedHotel = candidateData.candidate_hotels?.[0]?.name || ''
      assistantMsg.hitlStartDate = candidateData.start_date || (parsedFormData as any).start_date || ''
      assistantMsg.hitlEndDate = candidateData.end_date || (parsedFormData as any).end_date || ''
      assistantMsg.hitlTravelDays = candidateData.travel_days || (parsedFormData as any).travel_days || 1
      assistantMsg.initialTravelDays = candidateData.travel_days || (parsedFormData as any).travel_days || 1
      assistantMsg.initialStartDate = candidateData.start_date || (parsedFormData as any).start_date || ''
      assistantMsg.hitlUserFeedback = ''
      assistantMsg.hitlConfirmed = false
      assistantMsg.hitlSubmitting = false
      assistantMsg.loading = false
      assistantMsg.content = `✨ 已在【${candidateData.city}】为您挖掘到 ${candidateData.candidate_attractions?.length || 0} 处高分候选景点与 ${candidateData.candidate_hotels?.length || 0} 家优质住宿。请在下方卡片中勾选您心仪的项目，确认后将立即为您生成专属时空动线！`
    } else {
      assistantMsg.loading = false
      assistantMsg.content = res.message || '获取候选数据失败'
      currentLiveStepText.value = '准备候选失败'
    }
  } catch (err: any) {
    if (elapsedTimer) clearInterval(elapsedTimer)
    assistantMsg.loading = false
    assistantMsg.content = `准备人机协同规划失败: ${err.message || err}`
    currentLiveStepText.value = '准备失败'
  } finally {
    if (elapsedTimer) clearInterval(elapsedTimer)
    isLoading.value = false
    scrollToBottom()
  }
}

// In-Chat HITL 卡片操作辅助逻辑
const toggleHitlAttraction = (msg: ChatMessage, poiName: string) => {
  if (msg.hitlConfirmed) return
  const current = msg.hitlSelectedAttractions || []
  if (current.includes(poiName)) {
    msg.hitlSelectedAttractions = current.filter(n => n !== poiName)
  } else {
    msg.hitlSelectedAttractions = [...current, poiName]
  }
}

const selectAllHitlAttractions = (msg: ChatMessage) => {
  if (msg.hitlConfirmed || !msg.hitlCandidateData?.candidate_attractions) return
  msg.hitlSelectedAttractions = msg.hitlCandidateData.candidate_attractions.map(a => a.name)
}

const clearHitlAttractions = (msg: ChatMessage) => {
  if (msg.hitlConfirmed) return
  msg.hitlSelectedAttractions = []
}

const selectHitlHotel = (msg: ChatMessage, hotelName: string) => {
  if (msg.hitlConfirmed) return
  msg.hitlSelectedHotel = hotelName
}

const handleHitlDateChange = (msg: ChatMessage, type: 'start' | 'end', val: string) => {
  if (type === 'start') {
    msg.hitlStartDate = val
    if (msg.hitlEndDate && msg.hitlStartDate > msg.hitlEndDate) {
      msg.hitlEndDate = val
    }
  } else {
    msg.hitlEndDate = val
    if (msg.hitlStartDate && msg.hitlEndDate < msg.hitlStartDate) {
      msg.hitlStartDate = val
    }
  }
  if (msg.hitlStartDate && msg.hitlEndDate) {
    try {
      const s = new Date(msg.hitlStartDate)
      const e = new Date(msg.hitlEndDate)
      const diff = Math.max(1, Math.round((e.getTime() - s.getTime()) / (1000 * 3600 * 24)) + 1)
      msg.hitlTravelDays = diff
    } catch {
      // ignore
    }
  }
}

// 前置参数轻量确认交互函数
const handlePreParamDateChange = (msg: ChatMessage, type: 'start' | 'end', val: string) => {
  if (!msg.pendingParams) return
  const isFixedDuration = Boolean(msg.pendingParams.has_explicit_duration && msg.pendingParams.travel_days > 0)
  if (type === 'start') {
    msg.pendingParams.start_date = val
    if (isFixedDuration) {
      // 保持用户已指定的固定时长联动（出发日改变，返程日自动顺延，天数稳定不变）
      try {
        const s = new Date(val)
        s.setDate(s.getDate() + (msg.pendingParams.travel_days - 1))
        msg.pendingParams.end_date = s.toISOString().split('T')[0]
      } catch {
        // ignore
      }
    } else if (msg.pendingParams.end_date && msg.pendingParams.start_date > msg.pendingParams.end_date) {
      msg.pendingParams.end_date = val
    }
  } else {
    msg.pendingParams.end_date = val
    if (msg.pendingParams.start_date && msg.pendingParams.end_date < msg.pendingParams.start_date) {
      msg.pendingParams.start_date = val
    }
  }
  if (msg.pendingParams.start_date && msg.pendingParams.end_date) {
    try {
      const s = new Date(msg.pendingParams.start_date)
      const e = new Date(msg.pendingParams.end_date)
      const diff = Math.max(1, Math.round((e.getTime() - s.getTime()) / (1000 * 3600 * 24)) + 1)
      msg.pendingParams.travel_days = diff
    } catch {
      // ignore
    }
  }
}

const togglePreParamPreference = (msg: ChatMessage, pref: string) => {
  if (!msg.pendingParams) return
  const list = msg.pendingParams.preferences || []
  if (list.includes(pref)) {
    msg.pendingParams.preferences = list.filter(p => p !== pref)
  } else {
    msg.pendingParams.preferences = [...list, pref]
  }
}

const handleConfirmPreParams = async (msg: ChatMessage, useDefault: boolean = false) => {
  if (!msg.pendingParams) return
  msg.isParamConfirmPending = false
  const params: TripFormData = { ...msg.pendingParams }
  if (useDefault) {
    // 保持系统推测的参数
  }
  msg.content = `已锁定【${params.city}】${params.start_date} ~ ${params.end_date}（共 ${params.travel_days} 天）行程参数，多智能体系统开始为您规划...`

  if (isHitlEnabled.value) {
    await handleChatHitlPreparation(params, msg)
  } else {
    await handleChatStreamingGeneration(params, msg)
  }
}

// In-Chat HITL 候选重新匹配函数 (Invalidation & Re-search)
const handleRefreshHitlCandidates = async (msg: ChatMessage) => {
  if (msg.hitlConfirmed || msg.hitlRefreshing || !msg.hitlCandidateData) return
  msg.hitlRefreshing = true
  try {
    const refreshFormData: TripFormData = {
      city: msg.hitlCandidateData.city,
      start_date: msg.hitlStartDate || msg.hitlCandidateData.start_date || '',
      end_date: msg.hitlEndDate || msg.hitlCandidateData.end_date || '',
      travel_days: msg.hitlTravelDays || msg.hitlCandidateData.travel_days || 1,
      transportation: '公共交通',
      accommodation: '舒适型酒店',
      preferences: ['历史文化', '美食'],
      free_text_input: msg.hitlUserFeedback || '',
    }

    message.loading({ content: `正在重新检索【${refreshFormData.city}】${refreshFormData.travel_days}日游候选景点与天气...`, key: 'hitl_refresh' })
    const res = await prepareTripPlan(refreshFormData)

    if (res.success && res.data) {
      const candidateData = res.data
      msg.hitlCandidateData = candidateData
      const defaultAttractions = (candidateData.candidate_attractions || [])
        .slice(0, Math.min(Math.max(5, candidateData.travel_days * 2), candidateData.candidate_attractions.length))
        .map(a => a.name)
      msg.hitlSelectedAttractions = defaultAttractions
      msg.hitlSelectedHotel = candidateData.candidate_hotels?.[0]?.name || ''
      msg.initialTravelDays = candidateData.travel_days
      msg.initialStartDate = candidateData.start_date
      msg.hitlStartDate = candidateData.start_date
      msg.hitlEndDate = candidateData.end_date
      msg.hitlTravelDays = candidateData.travel_days
      message.success({ content: `已成功为您刷新为 ${candidateData.travel_days} 天行程候选资源！`, key: 'hitl_refresh' })
    } else {
      message.error({ content: res.message || '刷新候选数据失败', key: 'hitl_refresh' })
    }
  } catch (err: any) {
    message.error({ content: '刷新候选数据失败: ' + (err.message || err), key: 'hitl_refresh' })
  } finally {
    msg.hitlRefreshing = false
  }
}

const handleSkipHitlToAuto = async (msg: ChatMessage) => {
  if (msg.hitlConfirmed || !msg.hitlCandidateData) return
  // 全量选中候选景点与默认酒店
  if (msg.hitlCandidateData.candidate_attractions) {
    msg.hitlSelectedAttractions = msg.hitlCandidateData.candidate_attractions.map(a => a.name)
  }
  if (!msg.hitlSelectedHotel && msg.hitlCandidateData.candidate_hotels?.length) {
    msg.hitlSelectedHotel = msg.hitlCandidateData.candidate_hotels[0].name
  }
  await handleConfirmInChatHitl(msg)
}

// 人机协同 (HITL) 阶段二 —— 用户确认并恢复 LangGraph 执行
const handleConfirmInChatHitl = async (msg: ChatMessage) => {
  if (msg.hitlConfirmed || msg.hitlSubmitting || !msg.hitlCandidateData) return

  const selectedAttractions = msg.hitlSelectedAttractions || []
  if (selectedAttractions.length === 0) {
    message.warning('请至少勾选 1 处心仪的景点哦！')
    return
  }

  msg.hitlSubmitting = true
  msg.hitlConfirmed = true
  msg.loading = true
  isLoading.value = true

  // 状态矩阵推进
  const plannerNode = currentAgentNodes.value.find(n => n.key === 'planner')
  if (plannerNode) {
    plannerNode.status = 'running'
    plannerNode.detail = '融入协同偏好推演中'
  }
  streamProgress.value = 75
  currentLiveStepText.value = '正在根据您勾选的景点与酒店恢复规划推演...'

  // 追加推演步骤
  const samplePois = selectedAttractions.slice(0, 3).join('、')
  msg.thoughtSteps = [
    ...(msg.thoughtSteps || []),
    {
      id: 'step_hitl_resume_' + Date.now(),
      title: '🚀 注入人机协同意向 · 恢复时空规划推演',
      stage: '协同恢复执行',
      detail: `已锁定出行周期【${msg.hitlStartDate || '近期'} 至 ${msg.hitlEndDate || '近期'} (共 ${msg.hitlTravelDays || msg.hitlCandidateData.travel_days || 1} 天)】、${selectedAttractions.length} 处景点（如${samplePois}），住宿【${msg.hitlSelectedHotel || '默认推荐'}】${msg.hitlUserFeedback ? `，补充偏好: "${msg.hitlUserFeedback}"` : ''}。LangGraph 恢复执行 planner 节点！`,
      status: 'running',
      elapsedSeconds: (msg.thoughtElapsed || 0) + 1,
    }
  ]
  scrollToBottom()

  try {
    const confirmPayload = {
      thread_id: msg.hitlCandidateData.thread_id,
      selected_attractions: selectedAttractions,
      selected_hotel: msg.hitlSelectedHotel || undefined,
      user_feedback: msg.hitlUserFeedback || undefined,
      start_date: msg.hitlStartDate || undefined,
      end_date: msg.hitlEndDate || undefined,
    }

    const res = await confirmTripPlan(confirmPayload)

    if (res.success && res.data) {
      const plan = res.data
      currentPlan.value = plan
      msg.planData = plan
      msg.loading = false
      msg.hitlSubmitting = false
      msg.content = `🎉 太棒了！已根据您挑选的 ${selectedAttractions.length} 处景点与住宿安排，生成了量身定制的【${plan.city}】${plan.days.length}天深度游行程！`

      // 标记推演所有节点完成
      markLastRunningStepDone(msg)
      msg.thoughtSteps = [
        ...(msg.thoughtSteps || []),
        {
          id: 'step_hitl_complete_' + Date.now(),
          title: '🛡️ 质量闭环校验与行程输出',
          stage: '规划闭环成功',
          detail: '每日游玩动线、餐饮接驳与整体预算已全部测算完成，校验指标 100% 合格！',
          status: 'completed',
          elapsedSeconds: (msg.thoughtElapsed || 0) + 3,
        }
      ]

      currentAgentNodes.value.forEach(n => {
        n.status = 'completed'
      })
      streamProgress.value = 100
      currentLiveStepText.value = '人机协同规划已就绪！'

      // 持久化与看板展开
      const session = sessions.value.find(s => s.id === currentSessionId.value)
      if (session) {
        session.title = `${plan.city} ${plan.days.length}日游 (协同版)`
        session.city = plan.city
        session.tripPlan = plan
        session.messages = messages.value
        saveSessionsToStorage()
      }
      sessionStorage.setItem('tripPlan', JSON.stringify(plan))

      showCanvas.value = true
      nextTick(() => {
        initWorkspaceMap()
      })
      message.success('人机协同行程定制完成！')
    } else {
      msg.loading = false
      msg.hitlSubmitting = false
      msg.content = res.message || '生成旅行计划失败'
      message.error(res.message || '生成失败')
    }
  } catch (err: any) {
    msg.loading = false
    msg.hitlSubmitting = false
    msg.content = `恢复规划执行失败: ${err.message || err}`
    message.error(err.message || '恢复规划失败')
  } finally {
    msg.hitlSubmitting = false
    isLoading.value = false
    scrollToBottom()
  }
}

// 场景三：利用 LangGraph chat_modify 子图对话式调整行程
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

// 酒店到最近候选景点的距离显示计算（带精确经纬度 Haversine 兜底）
const getHotelDistanceDisplay = (hotel: POIInfo, candidateAttractions?: POIInfo[]): string => {
  if (hotel.distance && hotel.distance !== '距离景点2公里' && hotel.distance !== '位置距离') {
    return hotel.distance
  }
  if (!hotel.location || !candidateAttractions || candidateAttractions.length === 0) {
    return hotel.distance || ''
  }

  const hLng = Number(hotel.location.longitude)
  const hLat = Number(hotel.location.latitude)
  if (!Number.isFinite(hLng) || !Number.isFinite(hLat) || (hLng === 0 && hLat === 0)) {
    return hotel.distance || ''
  }

  let minDist = Infinity
  let nearestName = ''

  for (const att of candidateAttractions) {
    if (!att.location) continue
    const aLng = Number(att.location.longitude)
    const aLat = Number(att.location.latitude)
    if (!Number.isFinite(aLng) || !Number.isFinite(aLat) || (aLng === 0 && aLat === 0)) continue

    const radLat1 = (hLat * Math.PI) / 180
    const radLat2 = (aLat * Math.PI) / 180
    const dLat = ((aLat - hLat) * Math.PI) / 180
    const dLng = ((aLng - hLng) * Math.PI) / 180
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(radLat1) * Math.cos(radLat2) * Math.sin(dLng / 2) * Math.sin(dLng / 2)
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
    const dist = 6371 * c
    if (dist < minDist) {
      minDist = dist
      nearestName = att.name
    }
  }

  if (!nearestName || minDist === Infinity) {
    return hotel.distance || ''
  }

  const shortName = nearestName.split('-')[0].split('·')[0].split('(')[0].split('（')[0].trim()
  if (minDist < 1.0) {
    const meters = Math.max(50, Math.round(minDist * 100) * 10)
    return `近${shortName}(${meters}m)`
  }
  return `距${shortName} ${minDist.toFixed(1)}km`
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
      ${plan.knowledge_highlights && plan.knowledge_highlights.length > 0 ? `
        <div style="margin-top:8px; font-size:11px; color:#166534; background:#f0fdf4; border:1px solid #bbf7d0; padding:8px 12px; border-radius:6px; line-height:1.5;">
          🏛️ <strong>官方知识库攻略速记:</strong>
          <div style="margin-top:4px;">${plan.knowledge_highlights.map(h => `<div style="margin-bottom:3px;">• ${escapeHtml(h)}</div>`).join('')}</div>
        </div>
      ` : ''}
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
            ${day.hotel.distance ? ` · 📍 ${escapeHtml(day.hotel.distance)}` : ''}
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
      md += ` (${d.hotel.name}，${d.hotel.price_range}，${d.hotel.distance ? d.hotel.distance + '，' : ''}地址: ${d.hotel.address})`
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
  padding: 24px 32px 260px;
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

/* ======================== In-Chat HITL 人机协同卡片 ======================== */
.in-chat-hitl-card {
  margin-top: 14px;
  background: linear-gradient(145deg, #1e293b, #0f172a);
  border: 1px solid rgba(99, 102, 241, 0.35);
  border-radius: 16px;
  padding: 16px 18px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.25), 0 0 15px rgba(99, 102, 241, 0.08);
  color: #f1f5f9;
  transition: all 0.3s ease;
}

.in-chat-hitl-card.is-confirmed {
  border-color: rgba(16, 185, 129, 0.3);
  box-shadow: 0 6px 20px rgba(15, 23, 42, 0.15);
  background: linear-gradient(145deg, #1e293b, #131d2e);
}

.hitl-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
}

.hitl-header-main {
  display: flex;
  align-items: center;
  gap: 10px;
}

.hitl-badge-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.35);
  flex-shrink: 0;
}

.hitl-title-box {
  display: flex;
  flex-direction: column;
}

.hitl-title {
  font-size: 14px;
  font-weight: 700;
  color: #f8fafc;
  letter-spacing: 0.3px;
}

.hitl-subtitle {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 1px;
}

.hitl-status-pill {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.4);
  color: #fbbf24;
  white-space: nowrap;
}

.hitl-status-pill.confirmed {
  background: rgba(16, 185, 129, 0.15);
  border-color: rgba(16, 185, 129, 0.4);
  color: #34d399;
}

/* 出行周期确认条 */
.hitl-date-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(30, 41, 59, 0.6);
  border-radius: 10px;
  border: 1px solid rgba(99, 102, 241, 0.25);
}

.date-bar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.date-bar-icon {
  font-size: 15px;
}

.date-bar-label {
  font-size: 12px;
  font-weight: 600;
  color: #cbd5e1;
}

.date-inputs-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}

.hitl-date-input {
  background: #0f172a;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 6px;
  color: #f1f5f9;
  font-size: 12px;
  padding: 3px 8px;
  font-family: inherit;
  color-scheme: dark;
  cursor: pointer;
  transition: all 0.2s ease;
}

.hitl-date-input:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
}

.date-separator {
  font-size: 12px;
  color: #94a3b8;
}

.date-days-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  background: rgba(99, 102, 241, 0.2);
  border: 1px solid rgba(99, 102, 241, 0.35);
  color: #a5b4fc;
  border-radius: 12px;
}

.date-confirmed-val {
  font-size: 12px;
  font-weight: 500;
  color: #34d399;
}

.date-tip-sub {
  font-size: 11px;
  color: #94a3b8;
}

/* 天气胶囊横条 */
.hitl-weather-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(51, 65, 85, 0.35);
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.1);
  overflow-x: auto;
  scrollbar-width: none;
}

.hitl-weather-bar::-webkit-scrollbar {
  display: none;
}

.weather-bar-title {
  font-size: 11px;
  color: #cbd5e1;
  white-space: nowrap;
  font-weight: 600;
}

.weather-bar-tags {
  display: flex;
  align-items: center;
  gap: 8px;
}

.weather-mini-tag {
  font-size: 11px;
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.25);
  border-radius: 6px;
  padding: 2px 8px;
  white-space: nowrap;
}

/* 前置行程参数确认胶囊 */
.pre-trip-param-card {
  margin-top: 14px;
  background: linear-gradient(145deg, #1e293b, #0f172a);
  border: 1px solid rgba(99, 102, 241, 0.4);
  border-radius: 16px;
  padding: 16px 18px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.3), 0 0 16px rgba(99, 102, 241, 0.12);
  color: #f1f5f9;
}

.param-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
}

.param-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.param-badge-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.param-title-box {
  display: flex;
  flex-direction: column;
}

.param-card-title {
  font-size: 14px;
  font-weight: 700;
  color: #f8fafc;
}

.param-card-subtitle {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}

.param-status-tag {
  padding: 3px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.35);
  color: #fbbf24;
}

.param-form-grid {
  display: grid;
  grid-template-columns: 1fr 1.6fr;
  gap: 14px;
  margin-top: 14px;
}

.param-grid-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.param-grid-item.full-width {
  grid-column: span 2;
}

.param-label {
  font-size: 12px;
  font-weight: 600;
  color: #cbd5e1;
}

.param-input {
  background: #0f172a;
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 8px;
  color: #f8fafc;
  font-size: 13px;
  padding: 6px 10px;
  outline: none;
  transition: all 0.2s;
}

.param-input:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
}

.param-date-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.param-input.date-input {
  color-scheme: dark;
  cursor: pointer;
  flex: 1;
}

.date-sep {
  font-size: 12px;
  color: #94a3b8;
}

.param-days-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  background: rgba(99, 102, 241, 0.2);
  border: 1px solid rgba(99, 102, 241, 0.35);
  color: #a5b4fc;
  border-radius: 12px;
  white-space: nowrap;
}

.param-pref-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pref-choice-pill {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  background: rgba(51, 65, 85, 0.4);
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: #cbd5e1;
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}

.pref-choice-pill:hover {
  border-color: #6366f1;
  color: #f8fafc;
}

.pref-choice-pill.active {
  background: rgba(99, 102, 241, 0.25);
  border-color: #6366f1;
  color: #c7d2fe;
  font-weight: 600;
}

.param-card-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 16px;
}

.param-confirm-btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.param-confirm-btn.primary {
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.param-confirm-btn.primary:hover {
  background: linear-gradient(135deg, #4f46e5, #4338ca);
  transform: translateY(-1px);
}

.param-confirm-btn.secondary {
  background: rgba(51, 65, 85, 0.5);
  border: 1px solid rgba(148, 163, 184, 0.25);
  color: #94a3b8;
}

.param-confirm-btn.secondary:hover {
  background: rgba(51, 65, 85, 0.8);
  color: #f1f5f9;
}

/* HITL 天数/时效失配预警条 */
.hitl-stale-warning {
  margin-top: 10px;
  padding: 10px 14px;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.35);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  animation: fadeIn 0.3s ease;
}

.stale-warning-content {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.stale-warning-icon {
  font-size: 16px;
  margin-top: 1px;
}

.stale-warning-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stale-title {
  font-size: 12px;
  font-weight: 700;
  color: #fbbf24;
}

.stale-desc {
  font-size: 11px;
  color: #cbd5e1;
}

.hitl-refresh-btn {
  background: linear-gradient(135deg, #f59e0b, #d97706);
  color: #ffffff;
  border: none;
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(245, 158, 11, 0.25);
  transition: all 0.2s;
}

.hitl-refresh-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #d97706, #b45309);
  transform: translateY(-1px);
}

.hitl-refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 各区块 */
.hitl-section {
  margin-top: 14px;
}

.hitl-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.section-title {
  font-size: 13px;
  font-weight: 700;
  color: #e2e8f0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.count-tag {
  font-size: 11px;
  color: #94a3b8;
  font-weight: normal;
}

.count-tag strong {
  color: #818cf8;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mini-text-btn {
  background: none;
  border: none;
  padding: 2px 6px;
  color: #818cf8;
  font-size: 11px;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.mini-text-btn:hover {
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
}

.divider {
  color: #475569;
  font-size: 10px;
}

/* 景点网格 */
.hitl-attractions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
  max-height: 260px;
  overflow-y: auto;
  padding-right: 4px;
}

.hitl-attractions-grid::-webkit-scrollbar {
  width: 4px;
}
.hitl-attractions-grid::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.25);
  border-radius: 2px;
}

.hitl-poi-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 9px 12px;
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  user-select: none;
}

.hitl-poi-card:hover:not(.is-disabled) {
  border-color: rgba(99, 102, 241, 0.5);
  background: rgba(49, 46, 129, 0.25);
  transform: translateY(-1px);
}

.hitl-poi-card.is-selected {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.25), rgba(124, 58, 237, 0.15));
  border-color: #6366f1;
  box-shadow: 0 0 10px rgba(99, 102, 241, 0.2);
}

.hitl-poi-card.is-disabled {
  cursor: default;
  opacity: 0.85;
}

.poi-checkbox {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  border: 1px solid #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
  flex-shrink: 0;
  transition: all 0.2s;
  background: rgba(15, 23, 42, 0.5);
}

.hitl-poi-card.is-selected .poi-checkbox {
  background: #6366f1;
  border-color: #6366f1;
}

.check-icon {
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
}

.poi-details {
  flex: 1;
  min-width: 0;
}

.poi-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.poi-name {
  font-size: 12px;
  font-weight: 600;
  color: #f1f5f9;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.poi-rating {
  font-size: 10px;
  color: #fbbf24;
  white-space: nowrap;
  font-weight: 600;
}

.poi-mid-row {
  display: flex;
  gap: 4px;
  margin-top: 2px;
}

.poi-type {
  font-size: 10px;
  color: #94a3b8;
  background: rgba(148, 163, 184, 0.1);
  padding: 1px 4px;
  border-radius: 3px;
}

.poi-address {
  font-size: 10px;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 3px;
}

/* 酒店单选卡片网格 */
.hitl-hotels-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
}

.hitl-hotel-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 9px 12px;
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  user-select: none;
}

.hitl-hotel-card:hover:not(.is-disabled) {
  border-color: rgba(168, 85, 247, 0.5);
  background: rgba(88, 28, 135, 0.2);
  transform: translateY(-1px);
}

.hitl-hotel-card.is-selected {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.22), rgba(99, 102, 241, 0.15));
  border-color: #a855f7;
  box-shadow: 0 0 10px rgba(168, 85, 247, 0.2);
}

.hitl-hotel-card.is-disabled {
  cursor: default;
  opacity: 0.85;
}

.hotel-radio {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
  flex-shrink: 0;
  transition: all 0.2s;
  background: rgba(15, 23, 42, 0.5);
}

.hitl-hotel-card.is-selected .hotel-radio {
  border-color: #a855f7;
}

.radio-core {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #a855f7;
  box-shadow: 0 0 6px #a855f7;
}

.hotel-details {
  flex: 1;
  min-width: 0;
}

.hotel-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.hotel-name {
  font-size: 12px;
  font-weight: 600;
  color: #f1f5f9;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hotel-price {
  font-size: 10px;
  color: #f43f5e;
  font-weight: 600;
  white-space: nowrap;
}

.hotel-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
}

.hotel-rating {
  font-size: 10px;
  color: #fbbf24;
  font-weight: 600;
}

.hotel-tag {
  font-size: 10px;
  color: #c084fc;
  background: rgba(192, 132, 252, 0.12);
  padding: 1px 4px;
  border-radius: 3px;
}

.hotel-distance {
  font-size: 10px;
  color: #38bdf8;
  background: rgba(56, 189, 248, 0.14);
  border: 1px solid rgba(56, 189, 248, 0.28);
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 140px;
  font-weight: 500;
}

.hitl-hotel-card.is-selected .hotel-distance {
  color: #67e8f9;
  background: rgba(6, 182, 212, 0.22);
  border-color: rgba(6, 182, 212, 0.45);
}

.hotel-dist-tag {
  font-size: 11px;
  color: #0284c7;
  font-weight: 600;
  margin-left: 2px;
}

.d-hotel-distance-tag {
  font-size: 11px;
  color: #0369a1;
  font-weight: 600;
  margin-left: 2px;
}

.hotel-address {
  font-size: 10px;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 3px;
}

/* 反馈微调框 */
.hitl-feedback-box {
  margin-top: 14px;
  padding: 10px 12px;
  background: rgba(51, 65, 85, 0.35);
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.15);
}

.feedback-title {
  font-size: 11px;
  color: #cbd5e1;
  font-weight: 600;
  margin-bottom: 6px;
}

.hitl-feedback-input {
  background: rgba(15, 23, 42, 0.6) !important;
  border: 1px solid rgba(148, 163, 184, 0.25) !important;
  color: #f8fafc !important;
  border-radius: 8px !important;
  font-size: 12px !important;
}

.hitl-feedback-input:focus {
  border-color: #6366f1 !important;
  box-shadow: 0 0 8px rgba(99, 102, 241, 0.3) !important;
}

.hitl-feedback-display {
  margin-top: 12px;
  padding: 6px 12px;
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.25);
  border-radius: 8px;
  font-size: 11px;
}

.fb-tag {
  color: #a5b4fc;
  font-weight: 600;
}

.fb-content {
  color: #e2e8f0;
}

/* 卡片底部操作栏 */
.hitl-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.15);
  gap: 12px;
}

.hitl-footer-summary {
  font-size: 12px;
  color: #94a3b8;
}

.hitl-footer-summary strong {
  color: #f1f5f9;
}

.hitl-footer-btns {
  display: flex;
  align-items: center;
  gap: 10px;
}

.hitl-btn-skip {
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.3);
  color: #cbd5e1;
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.hitl-btn-skip:hover:not(:disabled) {
  background: rgba(148, 163, 184, 0.2);
  color: #f8fafc;
  border-color: #94a3b8;
}

.hitl-btn-confirm {
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  border: none;
  color: #ffffff;
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: 6px;
}

.hitl-btn-confirm:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(99, 102, 241, 0.5);
  background: linear-gradient(135deg, #4338ca, #6d28d9);
}

.hitl-btn-confirm:active:not(:disabled) {
  transform: scale(0.98);
}

.hitl-btn-confirm.confirmed {
  background: rgba(16, 185, 129, 0.2);
  border: 1px solid rgba(16, 185, 129, 0.4);
  color: #34d399;
  box-shadow: none;
  cursor: default;
}

.hitl-btn-confirm:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

/* 行程概要预览卡片 (全新现代卡片化排版) */
.plan-summary-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  padding: 20px 22px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0, 0, 0, 0.02);
  margin-top: 14px;
}

.plan-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #f1f5f9;
  padding-bottom: 14px;
  margin-bottom: 16px;
  gap: 16px;
}

.plan-card-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.plan-header-icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.12);
  flex-shrink: 0;
}

.plan-header-titles {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.plan-main-title {
  font-size: 16px;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: 0.2px;
}

.plan-sub-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.date-badge {
  font-size: 11px;
  font-weight: 500;
  color: #64748b;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 2px 8px;
  border-radius: 6px;
}

.days-count-badge {
  font-size: 11px;
  font-weight: 600;
  color: #2563eb;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  padding: 2px 8px;
  border-radius: 6px;
}

.budget-badge-premium {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  background: linear-gradient(135deg, #fff7ed, #ffedd5);
  border: 1px solid #fed7aa;
  padding: 6px 14px;
  border-radius: 10px;
  box-shadow: 0 2px 6px rgba(234, 88, 12, 0.08);
}

.budget-label {
  font-size: 10px;
  font-weight: 600;
  color: #ea580c;
  text-transform: uppercase;
}

.budget-amount {
  font-size: 16px;
  font-weight: 800;
  color: #c2410c;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

/* 每日规划卡片流水线 */
.days-preview-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 18px;
}

.day-preview-item {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: all 0.2s ease;
}

.day-preview-item:hover {
  background: #ffffff;
  border-color: #cbd5e1;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
}

/* 每日顶栏 */
.day-item-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.day-item-title-box {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.day-badge {
  background: linear-gradient(135deg, #2563eb, #3b82f6);
  color: #ffffff;
  font-weight: 700;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25);
  flex-shrink: 0;
}

.day-date-tag {
  font-size: 11px;
  color: #64748b;
  font-weight: 500;
  flex-shrink: 0;
}

.day-desc-text {
  font-size: 12px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.day-traffic-tag {
  font-size: 11px;
  color: #475569;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  padding: 2px 8px;
  border-radius: 6px;
  white-space: nowrap;
  flex-shrink: 0;
}

/* 游览景点动线 */
.day-spots-route-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #ffffff;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  padding: 8px 12px;
}

.spots-route-label {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  white-space: nowrap;
  flex-shrink: 0;
}

.spots-route-list {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.spot-route-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 12px;
  transition: all 0.15s;
}

.spot-route-chip:hover {
  background: #eff6ff;
  border-color: #93c5fd;
}

.spot-order-num {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #3b82f6;
  color: #ffffff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.spot-chip-name {
  font-weight: 600;
  color: #1e293b;
}

.spot-chip-duration {
  font-size: 10px;
  color: #64748b;
  background: rgba(100, 116, 139, 0.1);
  padding: 0 4px;
  border-radius: 3px;
}

.spot-chip-price {
  font-size: 10px;
  color: #e11d48;
  font-weight: 600;
}

.route-arrow-icon {
  font-size: 11px;
  color: #94a3b8;
  font-weight: bold;
}

/* 餐饮精简条 */
.day-meals-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  padding: 0 4px;
}

.meals-label {
  color: #64748b;
  font-weight: 600;
  white-space: nowrap;
}

.meals-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.meal-tag {
  color: #475569;
  background: #f1f5f9;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
}

.meal-type {
  color: #ea580c;
  margin-right: 2px;
}

/* 住宿推荐卡片横栏 */
.day-hotel-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: linear-gradient(135deg, #eff6ff, #f0fdf4);
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  padding: 7px 12px;
  font-size: 12px;
}

.hotel-card-left {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}

.hotel-lead-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.hotel-lead-text {
  font-weight: 700;
  color: #1e40af;
  flex-shrink: 0;
}

.hotel-title-text {
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hotel-price-pill {
  font-size: 11px;
  color: #dc2626;
  font-weight: 600;
  background: #fee2e2;
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.hotel-rating-pill {
  font-size: 10px;
  color: #d97706;
  font-weight: 600;
  flex-shrink: 0;
}

.hotel-card-right {
  flex-shrink: 0;
}

.hotel-distance-pill {
  font-size: 11px;
  color: #0369a1;
  background: #e0f2fe;
  border: 1px solid #bae6fd;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
  white-space: nowrap;
}

/* 底部操作与提示 */
.plan-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding-top: 14px;
  border-top: 1px solid #f1f5f9;
}

.footer-tip {
  font-size: 12px;
  color: #64748b;
  flex: 1;
}

.canvas-open-btn {
  border-radius: 8px !important;
  font-weight: 600 !important;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25) !important;
  flex-shrink: 0;
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

.bar-left-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.hitl-toggle-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  border-radius: 14px;
  font-size: 11px;
  font-weight: 600;
  color: #475569;
  cursor: pointer;
  transition: all 0.25s ease;
  user-select: none;
}

.hitl-toggle-pill:hover {
  background: #e2e8f0;
  color: #1e293b;
  border-color: #94a3b8;
}

.hitl-toggle-pill.active {
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  border-color: #6366f1;
  color: #ffffff;
  box-shadow: 0 2px 10px rgba(99, 102, 241, 0.3);
}

.hitl-pill-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #94a3b8;
  transition: all 0.25s ease;
}

.hitl-toggle-pill.active .hitl-pill-dot {
  background: #4ade80;
  box-shadow: 0 0 6px #4ade80;
}

.hitl-pill-tag {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.06);
}

.hitl-toggle-pill.active .hitl-pill-tag {
  background: rgba(255, 255, 255, 0.22);
  color: #ffffff;
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

/* RAG 知识库增强相关样式 */
.hitl-knowledge-bar {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 10px;
  padding: 8px 12px;
  margin-bottom: 12px;
}

.knowledge-bar-title {
  font-size: 11px;
  font-weight: 700;
  color: #166534;
  display: block;
  margin-bottom: 6px;
}

.knowledge-bar-tags {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.knowledge-mini-tag {
  font-size: 11px;
  line-height: 1.4;
  color: #15803d;
}

.plan-knowledge-highlights-strip {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 10px;
  padding: 8px 12px;
  margin-bottom: 12px;
}

.kh-strip-title {
  font-size: 11px;
  font-weight: 700;
  color: #166534;
  display: block;
  margin-bottom: 6px;
}

.kh-strip-tags {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kh-tag-pill {
  font-size: 11px;
  color: #15803d;
  line-height: 1.4;
}

.spot-chip-rag-dot {
  font-size: 10px;
  cursor: help;
}
</style>
