import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'

// const Home = () => import('../views/Home.vue')
const VideoLibrary = () => import('../views/VideoLibrary.vue')
const Login = () => import('../views/Login.vue')
const BasicData = () => import('../views/BasicData.vue')
const RealTimeMonitor = () => import('../views/RealTimeMonitor.vue')
// const DrillManagement = () => import('../views/DrillManagement.vue')

// 🌟 AI识别结果展示台账
const AIResults = () => import('../views/AIResults.vue')

const routes = [
  {
    path: '/',
    redirect: '/ai-results'
  },
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { title: '系统登录' }
  },
  {
    path: '/ai-results',
    name: 'AIResults',
    component: AIResults,
    meta: { title: 'AI 识别结果台账' }
  },
  //   {
  //   path: '/ai-results',
  //   name: 'AIResults',
  //   component: AIResults,
  //   meta: { title: 'AI 识别结果台账' }
  // },
  {
    path: '/library',
    name: 'VideoLibrary',
    component: VideoLibrary,
    meta: { title: '视频归档库' }
  },
  // {
  //   path: '/drills',
  //   name: 'DrillManagement',
  //   component: DrillManagement,
  //   meta: { title: '钻孔业务管理' }
  // },
  {
    path: '/basic-data',
    name: 'BasicData',
    component: BasicData,
    meta: { title: '基础数据管理' }
  },
  {
    path: '/monitor',
    name: 'RealTimeMonitor',
    component: RealTimeMonitor,
    meta: { title: '实时视频监控' }
  },
  // 🌟 核心替换：抛弃原有的在线/本地分析，换成这个纯展示看板

]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const isLoggedIn = localStorage.getItem('isLoggedIn') === 'true'
  if (to.path !== '/login' && !isLoggedIn) {
    ElMessage.warning('请先登录系统')
    next('/login')
  } else {
    document.title = to.meta.title ? `${to.meta.title} - 煤矿钻场视频智能系统` : '煤矿钻场视频智能系统'
    next()
  }
})

export default router