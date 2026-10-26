<template>
  <div class="app-shell">
    <!-- 对话工作台独占沉浸式全屏布局 -->
    <router-view v-if="isWorkspace" />

    <!-- 经典表单与全屏报表页沿用标准导航布局 -->
    <a-layout v-else class="classic-layout">
      <a-layout-header class="classic-header">
        <div class="classic-brand">
          🌍 LangGraph智能旅行助手
        </div>
      </a-layout-header>
      <a-layout-content class="classic-content">
        <router-view />
      </a-layout-content>
      <a-layout-footer class="classic-footer">
        LangGraph智能旅行助手 ©{{ new Date().getFullYear() }} 基于LangGraph框架
      </a-layout-footer>
    </a-layout>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const isWorkspace = computed(() => route.path === '/')
</script>

<style>
html, body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
}

html { overflow-x: hidden; }

#app {
  width: 100%;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial,
    'Noto Sans', sans-serif;
}

.app-shell {
  min-height: 100%;
}

.classic-layout { min-height: 100vh; }
.classic-header { background: #001529; padding: 0 50px; }
.classic-brand { color: white; font-size: 24px; font-weight: bold; }
.classic-content { padding: 24px; min-width: 0; }
.classic-footer { text-align: center; }

@media (max-width: 767px) {
  .classic-header {
    height: auto;
    line-height: 1.5;
    padding: calc(14px + env(safe-area-inset-top, 0px)) 16px 14px;
  }
  .classic-brand { font-size: 18px; }
  .classic-content { padding: 0; }
  .classic-footer {
    padding: 16px 12px calc(16px + env(safe-area-inset-bottom, 0px));
    font-size: 12px;
  }
}
</style>
