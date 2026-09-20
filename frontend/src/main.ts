import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import ChatWorkspace from './views/ChatWorkspace.vue'
import Home from './views/Home.vue'
import Result from './views/Result.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'ChatWorkspace',
      component: ChatWorkspace
    },
    {
      path: '/form',
      name: 'Home',
      component: Home
    },
    {
      path: '/result',
      name: 'Result',
      component: Result
    }
  ]
})


const app = createApp(App)

app.use(router)
app.use(Antd)

app.mount('#app')

