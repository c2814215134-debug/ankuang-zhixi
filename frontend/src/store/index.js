import { defineStore } from 'pinia'
import { folderApi, videoApi, dashboardApi, authApi } from '../api' 
import { ElMessage } from 'element-plus'

export const useVideoStore = defineStore('video', {
  state: () => ({
    folders: [], 
    currentFolderVideos: [], 
    serverStatus: false,
    loading: false,
    lastUpdated: null,

    isLoggedIn: localStorage.getItem('isLoggedIn') === 'true',
    username: localStorage.getItem('username') || '',

    dashboardStats: {
      total_drills: 0,
      status_counts: {},
      team_counts: {},
      recent_drills: []
    }
  }),

  actions: {
    // === 真实 API 登录 ===
    async login(username, password) {
      try {
        const res = await authApi.login({ username, password })
        if (res.success) {
          this.isLoggedIn = true
          this.username = res.data.username
          localStorage.setItem('isLoggedIn', 'true')
          localStorage.setItem('username', res.data.username)
          return { success: true }
        }
        return { success: false, message: res.message }
      } catch (error) {
        // 捕获后端的报错消息（例如密码错误、用户不存在等）
        const errMsg = error.response?.data?.message || '登录失败，请检查网络连接'
        return { success: false, message: errMsg }
      }
    },

    // 退出登录
    logout() {
      this.isLoggedIn = false
      this.username = ''
      localStorage.removeItem('isLoggedIn')
      localStorage.removeItem('username')
    },

    async checkBackend() {
      try {
        const res = await dashboardApi.getStats()
        this.serverStatus = res.success || false
      } catch (e) {
        this.serverStatus = false
      }
    },

    async fetchDashboardStats() {
      try {
        const res = await dashboardApi.getStats()
        if (res.success) {
          this.dashboardStats = res
        }
      } catch (error) {
        console.error('获取仪表盘数据失败', error)
      }
    }
  }
})