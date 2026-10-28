import axios from 'axios'

// 🔗 后端地址：确保端口是 2800
const API_BASE_URL = 'http://localhost:2800' 

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 0,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 响应拦截器
api.interceptors.response.use(
  response => response.data,
  error => {
    console.error('API Error:', error)
    // 拦截到我们后端的错误信息并向上抛出
    return Promise.reject(error)
  }
)

// === 1. 视频与文件夹 ===
export const folderApi = {
  getFolders() {
    return api.get('/api/folders')
  },
  getFolderVideos(folderName) {
    return api.get(`/api/folder/${folderName}`)
  }
}

export const videoApi = {
  searchVideos(keyword) {
    return api.get(`/api/search?q=${keyword}`)
  },
  getVideoUrl(videoPath) {
    return `${API_BASE_URL}/api/video/${videoPath}`
  }
}

// === 2. 基础数据管理 ===
export const locationApi = {
  getAll() {
    return api.get('/api/locations')
  },
  create(data) {
    return api.post('/api/locations', data)
  },
  update(id, data) {
    return api.put(`/api/locations/${id}`, data)
  },
  delete(id) {
    return api.delete(`/api/locations/${id}`)
  }
}

export const cameraApi = {
  getAll() {
    return api.get('/api/cameras')
  },
  create(data) {
    return api.post('/api/cameras', data)
  },
  update(id, data) {
    return api.put(`/api/cameras/${id}`, data)
  },
  delete(id) {
    return api.delete(`/api/cameras/${id}`)
  }
}

// === 3. 核心业务管理 ===
export const drillApi = {
  getAll() {
    return api.get('/api/drills')
  },
  create(data) {
    return api.post('/api/drills', data)
  },
  update(id, data) {
    return api.put(`/api/drills/${id}`, data)
  },
  delete(id) {
    return api.delete(`/api/drills/${id}`)
  }
}

export const dashboardApi = {
  getStats() {
    return api.get('/api/dashboard/stats')
  }
}

// === 4. 工序智能分析 ===
export const analysisApi = {
  getRawFiles() {
    return api.get('/api/analysis/files')
  },
  start(filename, frame_skip) {
    return api.post('/api/analysis/start', { filename, frame_skip })
  },
  stop(taskId) {
    return api.post(`/api/analysis/stop/${taskId}`)
  },
  getStatus(taskId) {
    return api.get(`/api/analysis/status/${taskId}`)
  },
  // 处理本地视频上传、重命名并自动启动的接口
  uploadAndStart(formData) {
    // 必须告诉后端我们传的是 multipart/form-data 文件流
    return api.post('/api/analysis/upload_and_start', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  }
}

// === 5. 认证 API ===
export const authApi = {
  login(data) {
    return api.post('/api/auth/login', data)
  },
  register(data) {
    return api.post('/api/auth/register', data)
  }
}

// === 6. 系统配置管理 ===
export const configApi = {
  getConfig() {
    return api.get('/api/system/config')
  },
  saveConfig(data) {
    return api.post('/api/system/config', data)
  }
}

// === 7. 🌟 AI 识别台账 (收发室) ===
export const detectionApi = {
  // 拉取所有识别记录列表
  getLogs() {
    return api.get('/api/detection/logs')
  },
  // 删除指定的测试记录
  deleteLog(id) {
    return api.delete(`/api/detection/logs/${id}`)
  },
  // 前端手动发数据测试用（通常由测试服务器调用此后端接口）
  receiveLog(data) {
    return api.post('/api/detection/receive', data)
  }
}