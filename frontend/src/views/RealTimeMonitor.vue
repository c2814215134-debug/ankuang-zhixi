<template>
  <el-container class="app-layout">
    <el-header class="app-header">
      <div class="header-left">
        <el-icon class="logo-icon" :size="28" color="#2563eb"
          ><Monitor
        /></el-icon>
        <span class="brand-text">煤矿钻场视频智能剪辑与数据管理平台</span>
      </div>
      <div class="header-right">
        <el-avatar
          :size="32"
          src="https://cube.elemecdn.com/3/7c/3ea6beec64369c2642b92c6726f1epng.png"
        />
        <span class="username">{{ username }}</span>
        <el-button
          type="danger"
          plain
          size="small"
          @click="handleLogout"
          style="margin-left: 16px"
        >
          退出登录
        </el-button>
      </div>
    </el-header>

    <el-container class="main-container">
      <AppSidebar />

      <el-main class="app-main">
        <div class="monitor-container">
          <div class="device-list">
            <div class="panel-title">设备列表</div>
            <el-tree
              :data="treeData"
              :props="defaultProps"
              @node-click="handleNodeClick"
              default-expand-all
              highlight-current
            >
              <template #default="{ node, data }">
                <span class="custom-tree-node">
                  <el-icon v-if="data.type === 'location'"
                    ><Location
                  /></el-icon>
                  <el-icon v-else><VideoCamera /></el-icon>
                  <span style="margin-left: 8px">{{ node.label }}</span>
                </span>
              </template>
            </el-tree>
          </div>

          <div class="monitor-content">
            <div class="player-wrapper">
              <div class="player-header">
                <div class="header-info">
                  <h3>实时视频监控</h3>
                  <el-tag
                    size="small"
                    type="success"
                    style="margin-left: 12px"
                    v-if="activeStreams.length > 0"
                  >
                    正在监控 {{ activeStreams.length }} 个设备
                  </el-tag>
                </div>
              </div>

              <div class="screen-container">
                <div
                  v-if="activeStreams.length === 0"
                  style="
                    width: 100%;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                  "
                >
                  <el-empty
                    description="请在左侧设备列表中选择摄像头 (最多4路)"
                  />
                </div>

                <div
                  v-else
                  class="video-grid"
                  :class="'grid-' + activeStreams.length"
                >
                  <div
                    v-for="(stream, index) in activeStreams"
                    :key="stream.id"
                    class="video-item"
                  >
                    <img
                      :src="`http://localhost:2800/api/video_feed/${stream.id}`"
                      class="live-stream"
                      :alt="stream.name"
                    />
                    <div class="stream-overlay">
                      <span>{{ stream.name }} [{{ stream.code }}]</span>
                      <el-button
                        type="danger"
                        icon="Close"
                        circle
                        size="small"
                        @click.stop="removeStream(index)"
                      ></el-button>
                    </div>
                  </div>
                </div>
              </div>

              <div class="control-panel">
                <div
                  v-if="activeStreams.length > 0"
                  class="info-grid"
                  :class="'info-grid-' + activeStreams.length"
                >
                  <div
                    v-for="cam in activeStreams"
                    :key="cam.id"
                    class="camera-info-card"
                  >
                    <div class="card-title">
                      <el-icon><VideoCamera /></el-icon>
                      <span class="cam-name">{{ cam.name }}</span>
                    </div>
                    <div class="info-content">
                      <div class="info-item">
                        <span class="label">设备编号：</span>
                        <span class="value">{{ cam.code }}</span>
                      </div>
                      <div class="info-item">
                        <span class="label">IP 地址：</span>
                        <span class="value">{{
                          cam.ip_address || "未知"
                        }}</span>
                      </div>
                      <div class="info-item">
                        <span class="label">流状态：</span>
                        <el-tag size="small" type="success" effect="plain"
                          >实时传输中</el-tag
                        >
                      </div>
                    </div>
                  </div>
                </div>
                <div v-else class="empty-info">
                  <span style="color: #94a3b8; font-size: 14px"
                    >等待接入设备...</span
                  >
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-main>
    </el-container>

    <el-dialog
      v-model="replaceDialogVisible"
      title="监控画面已达上限 (4个)"
      width="400px"
    >
      <p style="margin-bottom: 15px; color: #606266">
        请选择要被替换的现有摄像头画面：
      </p>
      <el-radio-group v-model="replaceIndex" class="replace-radio-group">
        <el-radio
          v-for="(stream, index) in activeStreams"
          :key="stream.id"
          :label="index"
        >
          {{ stream.name }} [{{ stream.code }}]
        </el-radio>
      </el-radio-group>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="replaceDialogVisible = false">取消</el-button>
          <el-button
            type="primary"
            @click="confirmReplace"
            :disabled="replaceIndex === null"
          >
            确认替换
          </el-button>
        </span>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useVideoStore } from '../store'
import { locationApi, cameraApi } from '../api'
import { ElMessage } from 'element-plus'
import { Location, VideoCamera, Monitor, Close } from '@element-plus/icons-vue'
import AppSidebar from '../components/AppSidebar.vue'

const router = useRouter()
const videoStore = useVideoStore()
const username = ref(videoStore.username)

const treeData = ref([])
const defaultProps = { children: 'children', label: 'label' }

// 维护多流状态
const activeStreams = ref([]) // 当前播放的视频流列表
const replaceDialogVisible = ref(false)
const pendingCamera = ref(null)
const replaceIndex = ref(null)

const handleLogout = () => {
  videoStore.logout()
  router.push('/login')
}

// 获取树结构数据
const fetchLocationsAndCameras = async () => {
  try {
    const [locRes, camRes] = await Promise.all([
      locationApi.getAll(),
      cameraApi.getAll()
    ])

    if (locRes.success && camRes.success) {
      const locations = locRes.data
      const cameras = camRes.data

      treeData.value = locations.map((loc) => {
        const locCameras = cameras.filter(cam => cam.location_id === loc.id)
        return {
          id: loc.id,
          label: loc.name,
          type: 'location',
          children: locCameras.map((cam) => ({
            ...cam,
            label: cam.name,
            type: 'camera'
          }))
        }
      })
    }
  } catch (error) {
    console.error("加载设备树报错:", error)
    ElMessage.error('获取设备列表失败，请检查网络连接')
  }
}

const handleNodeClick = (data) => {
  if (data.type !== 'camera') return

  if (activeStreams.value.some(stream => stream.id === data.id)) {
    ElMessage.warning(`摄像头 [${data.name}] 已在监控画面中`)
    return
  }

  if (activeStreams.value.length < 4) {
    activeStreams.value.push(data)
    ElMessage.success(`已添加 [${data.name}] 到监控画面`)
  } else {
    pendingCamera.value = data
    replaceIndex.value = null
    replaceDialogVisible.value = true
  }
}

const removeStream = (index) => {
  activeStreams.value.splice(index, 1)
}

const confirmReplace = () => {
  if (replaceIndex.value !== null && pendingCamera.value) {
    activeStreams.value.splice(replaceIndex.value, 1, pendingCamera.value)
    replaceDialogVisible.value = false
    pendingCamera.value = null
    ElMessage.success('摄像头画面已替换')
  }
}

onMounted(() => {
  fetchLocationsAndCameras()
})
</script>

<style scoped>
/* =========== 保持不变的整体布局样式 =========== */
.app-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
}
.app-header {
  background: white;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 60px;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  font-size: 18px;
  color: #1e293b;
}
.header-right {
  display: flex;
  align-items: center;
}
.username {
  margin-left: 12px;
  font-weight: 600;
  color: #475569;
}
.main-container {
  display: flex;
  flex: 1;
  overflow: hidden;
}
.app-main {
  background-color: #f1f5f9;
  flex: 1;
  padding: 24px;
  overflow-y: hidden;
}

.monitor-container {
  display: flex;
  gap: 24px;
  height: 100%;
}
.device-list {
  width: 280px;
  background: white;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.panel-title {
  padding: 16px;
  font-weight: 600;
  color: #1e293b;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
  border-radius: 8px 8px 0 0;
}
.el-tree {
  padding: 12px;
  flex: 1;
  overflow-y: auto;
}
.custom-tree-node {
  display: flex;
  align-items: center;
  font-size: 14px;
}

.monitor-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: white;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  padding: 24px;
  overflow-y: auto;
}

.player-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.player-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-shrink: 0;
}
.header-info {
  display: flex;
  align-items: center;
}
.header-info h3 {
  margin: 0;
  font-size: 18px;
  color: #303133;
}

/* =========== 屏幕容器与网格样式 =========== */
.screen-container {
  flex: 1;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
  position: relative;
  min-height: 480px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  display: flex;
}

.video-grid {
  display: grid;
  width: 100%;
  height: 100%;
  gap: 2px;
  background: #333;
}
.grid-1 {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}
.grid-2 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr;
}
.grid-3 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}
.grid-4 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}

.video-item {
  position: relative;
  background: #000;
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}
.live-stream {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.stream-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 8px 12px;
  background: linear-gradient(to bottom, rgba(0, 0, 0, 0.7), transparent);
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: white;
  font-size: 13px;
  opacity: 0;
  transition: opacity 0.3s;
}
.video-item:hover .stream-overlay {
  opacity: 1;
}

.replace-radio-group {
  display: flex;
  flex-direction: column;
  align-items: flex-start; /* 确保所有的圆圈强制靠左对齐 */
  gap: 12px;
  padding-left: 40px;
}
.replace-radio-group .el-radio {
  margin-left: 0 !important;
  margin-right: 0 !important;
}

/* =========== 🌟 底板控制台样式重构 =========== */
.control-panel {
  margin-top: 24px;
  padding: 20px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  flex-shrink: 0;
}

.empty-info {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 60px;
}

/* 根据设备数量自动调整网格列数 */
.info-grid {
  display: grid;
  gap: 16px;
}
.info-grid-1 {
  grid-template-columns: 1fr;
}
.info-grid-2 {
  grid-template-columns: repeat(2, 1fr);
}
.info-grid-3 {
  grid-template-columns: repeat(3, 1fr);
}
.info-grid-4 {
  grid-template-columns: repeat(4, 1fr);
}

/* 单个设备信息卡片 */
.camera-info-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #1e293b;
  font-size: 15px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px dashed #cbd5e1;
}
.card-title .el-icon {
  color: #2563eb;
  font-size: 18px;
}
.cam-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.info-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-item {
  display: flex;
  align-items: center;
  justify-content: space-between; /* 键值对左右对齐 */
}
.info-item .label {
  color: #64748b;
  font-size: 13px;
}
.info-item .value {
  color: #334155;
  font-weight: 500;
  font-size: 13px;
  font-family: monospace; /* IP和编号使用等宽字体更美观 */
}
</style>