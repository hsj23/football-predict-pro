import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'

// 路由配置
const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('./views/Home.vue')
  },
  {
    path: '/matches',
    name: 'MatchList',
    component: () => import('./views/MatchList.vue')
  },
  {
    path: '/prediction/:id',
    name: 'PredictionDetail',
    component: () => import('./views/PredictionDetail.vue')
  },
  {
    path: '/odds/:id',
    name: 'OddsAnalysis',
    component: () => import('./views/OddsAnalysis.vue')
  },
  {
    path: '/statistics',
    name: 'Statistics',
    component: () => import('./views/Statistics.vue')
  },
  {
    path: '/team/:name',
    name: 'TeamHistory',
    component: () => import('./views/TeamHistory.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

const app = createApp(App)
app.use(router)
app.use(ElementPlus)
app.mount('#app')
