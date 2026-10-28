<template>
  <el-container class="app-layout">
    <!-- 统一的顶部状态栏 -->
    <el-header class="app-header">
      <div class="header-left">
        <el-icon class="logo-icon" :size="28" color="#2563eb"
          ><DataBoard
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
      <!-- 统一的左侧侧边栏 -->
      <AppSidebar />

      <el-main class="app-main">
        <!-- <div class="page-header">
          <h2>基础数据管理</h2>
          <p>管理煤矿井下地点及监控设备信息</p>
        </div> -->

        <el-card shadow="never" class="data-card">
          <el-tabs v-model="activeTab">
            <!-- Tab 1: 地点管理 -->
            <el-tab-pane label="地点管理" name="locations">
              <div class="tab-toolbar">
                <el-button type="primary" @click="openAddLocDialog">
                  <el-icon><Plus /></el-icon> 新增地点
                </el-button>
              </div>
              <el-table :data="locations" stripe style="width: 100%">
                <el-table-column prop="code" label="地点编号" width="150" />
                <el-table-column prop="name" label="地点名称" width="200" />
                <el-table-column prop="description" label="备注" />
                <el-table-column label="操作" width="180" fixed="right">
                  <template #default="scope">
                    <el-button
                      type="primary"
                      link
                      @click="openEditLocDialog(scope.row)"
                      >修改</el-button
                    >
                    <el-button
                      type="danger"
                      link
                      @click="deleteLocation(scope.row)"
                      >删除</el-button
                    >
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- Tab 2: 摄像仪管理 -->
            <el-tab-pane label="摄像仪管理" name="cameras">
              <div class="tab-toolbar">
                <el-button type="primary" @click="openAddCamDialog">
                  <el-icon><Plus /></el-icon> 新增摄像仪
                </el-button>
              </div>
              <el-table :data="cameras" stripe style="width: 100%">
                <el-table-column prop="name" label="设备名称" width="150" />
                <el-table-column prop="code" label="设备编号" width="120" />
                <el-table-column prop="ip_address" label="IP地址" width="140" />
                <el-table-column label="所属地点" width="150">
                  <template #default="scope">
                    {{ getLocationName(scope.row.location_id) }}
                  </template>
                </el-table-column>
                <el-table-column
                  prop="rtsp_url"
                  label="RTSP地址"
                  show-overflow-tooltip
                />
                <el-table-column label="状态" width="100">
                  <template #default="scope">
                    <el-tag
                      :type="scope.row.status === 'online' ? 'success' : 'info'"
                    >
                      {{ scope.row.status === "online" ? "在线" : "离线" }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="180" fixed="right">
                  <template #default="scope">
                    <el-button
                      type="primary"
                      link
                      @click="openEditCamDialog(scope.row)"
                      >修改</el-button
                    >
                    <el-button
                      type="danger"
                      link
                      @click="deleteCamera(scope.row)"
                      >删除</el-button
                    >
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- Tab 3: 系统参数设置 -->
            <el-tab-pane label="系统参数设置" name="settings">
              <div class="settings-container">
                <el-card shadow="never" class="settings-card">
                  <template #header>
                    <div class="card-header">
                      <el-icon color="#2563eb" :size="18"><Folder /></el-icon>
                      <span style="margin-left: 8px; font-weight: 600"
                        >本地存储配置</span
                      >
                    </div>
                  </template>
                  <el-form
                    label-position="right"
                    label-width="150px"
                    style="max-width: 650px"
                  >
                    <el-form-item label="本地视频归档路径">
                      <el-input
                        v-model="sysConfig.localBasePath"
                        placeholder="例如: D:\mining_project\backend\raw_videos\processed"
                      />
                      <div class="form-tip">
                        系统剪辑完成的工序视频将自动保存在此物理路径下。
                      </div>
                    </el-form-item>
                    <el-form-item>
                      <el-button type="primary" @click="saveConfig('local')"
                        >保存本地配置</el-button
                      >
                    </el-form-item>
                  </el-form>
                </el-card>

                <el-card
                  shadow="never"
                  class="settings-card"
                  style="margin-top: 20px"
                >
                  <template #header>
                    <div class="card-header">
                      <el-icon color="#2563eb" :size="18"><Cloudy /></el-icon>
                      <span style="margin-left: 8px; font-weight: 600"
                        >云端同步配置 (OSS)</span
                      >
                    </div>
                  </template>
                  <el-form
                    label-position="right"
                    label-width="150px"
                    style="max-width: 650px"
                  >
                    <el-form-item label="开启云端双重备份">
                      <el-switch
                        v-model="sysConfig.enableCloud"
                        active-text="已开启"
                        inactive-text="已关闭"
                      />
                    </el-form-item>

                    <el-collapse-transition>
                      <div
                        v-show="sysConfig.enableCloud"
                        class="cloud-config-area"
                      >
                        <el-form-item label="云服务商">
                          <el-select
                            v-model="sysConfig.cloudProvider"
                            placeholder="请选择云服务商"
                            style="width: 100%"
                          >
                            <el-option label="阿里云 OSS" value="aliyun" />
                            <el-option label="腾讯云 COS" value="tencent" />
                            <el-option label="私有部署 MinIO" value="minio" />
                          </el-select>
                        </el-form-item>
                        <el-form-item label="存储桶 (Bucket)">
                          <el-input
                            v-model="sysConfig.bucketName"
                            placeholder="例如: mining-video-bucket"
                          />
                        </el-form-item>
                        <el-form-item label="地域节点 (Endpoint)">
                          <el-input
                            v-model="sysConfig.endpoint"
                            placeholder="例如: oss-cn-beijing.aliyuncs.com"
                          />
                        </el-form-item>
                        <el-form-item label="AccessKey ID">
                          <el-input
                            v-model="sysConfig.accessKeyId"
                            placeholder="请输入公钥 (AK)"
                          />
                        </el-form-item>
                        <el-form-item label="AccessKey Secret">
                          <el-input
                            v-model="sysConfig.accessKeySecret"
                            type="password"
                            show-password
                            placeholder="请输入私钥 (SK)"
                          />
                        </el-form-item>
                        <el-form-item label="云端归档目录">
                          <el-input
                            v-model="sysConfig.cloudBasePath"
                            placeholder="例如: /coalmine/processed_videos/"
                          />
                          <div class="form-tip">
                            剪辑好的视频将保存在云端存储桶的此路径下。
                          </div>
                        </el-form-item>

                        <el-form-item>
                          <el-button
                            type="success"
                            plain
                            @click="testCloudConnection"
                            >测试云端连接</el-button
                          >
                          <el-button type="primary" @click="saveConfig('cloud')"
                            >保存云端配置</el-button
                          >
                        </el-form-item>
                      </div>
                    </el-collapse-transition>
                  </el-form>
                </el-card>
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>

        <!-- Dialog: 新增/修改地点 -->
        <el-dialog
          :title="isEditMode ? '编辑地点' : '新增地点'"
          v-model="showLocDialog"
          width="500px"
        >
          <el-form
            :model="locForm"
            :rules="rules"
            ref="locFormRef"
            label-width="100px"
          >
            <el-form-item label="地点编码" prop="code">
              <el-input
                v-model="locForm.code"
                placeholder="例如: LOC001"
              ></el-input>
            </el-form-item>
            <el-form-item label="地点名称" prop="name">
              <el-input
                v-model="locForm.name"
                placeholder="例如: 1号钻场"
              ></el-input>
            </el-form-item>
            <el-form-item label="描述" prop="description">
              <el-input
                v-model="locForm.description"
                type="textarea"
              ></el-input>
            </el-form-item>
          </el-form>
          <template #footer>
            <span class="dialog-footer">
              <el-button @click="showLocDialog = false">取消</el-button>
              <el-button
                type="primary"
                :loading="loading"
                @click="submitLocation"
                >确定</el-button
              >
            </span>
          </template>
        </el-dialog>

        <!-- Dialog: 新增/修改摄像仪 -->
        <el-dialog
          v-model="showCamDialog"
          :title="isEditMode ? '修改摄像仪' : '新增摄像仪'"
          width="500px"
        >
          <el-form :model="camForm" label-width="100px">
            <el-form-item label="所属地点" required>
              <el-select
                v-model="camForm.location_id"
                placeholder="请选择地点"
                style="width: 100%"
              >
                <el-option
                  v-for="item in locations"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="设备名称" required>
              <el-input v-model="camForm.name" placeholder="例如: 1号摄像仪" />
            </el-form-item>
            <el-form-item label="设备编号" required>
              <el-input v-model="camForm.code" placeholder="例如: CAM-001" />
            </el-form-item>
            <el-form-item label="IP地址" required>
              <el-input
                v-model="camForm.ip_address"
                placeholder="192.168.1.x"
              />
            </el-form-item>
            <el-form-item label="端口">
              <el-input-number
                v-model="camForm.port"
                :min="1"
                :max="65535"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="状态">
              <el-radio-group v-model="camForm.status">
                <el-radio value="online">在线</el-radio>
                <el-radio value="offline">离线</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="camForm.username" placeholder="RTSP用户名" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="camForm.password"
                type="password"
                placeholder="RTSP密码"
                show-password
              />
            </el-form-item>
            <el-form-item label="RTSP地址">
              <el-input
                v-model="camForm.rtsp_url"
                placeholder="例如: rtsp://127.0.0.1:8554/cam01"
              />
              <div class="form-tip">
                留空则根据IP端口自动拼接(海康格式)，手动填写则优先使用填写值。
              </div>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="showCamDialog = false">取消</el-button>
            <el-button type="primary" @click="submitCamera">确定</el-button>
          </template>
        </el-dialog>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { locationApi, cameraApi, configApi } from '../api'
import { useVideoStore } from '../store'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, DataBoard, Location, VideoCamera, Folder, Cloudy } from '@element-plus/icons-vue'
import AppSidebar from '../components/AppSidebar.vue'

const router = useRouter()
const videoStore = useVideoStore()
const username = ref(videoStore.username || 'Admin')

const activeTab = ref('locations')
const loading = ref(false)

const locations = ref([])
const cameras = ref([])

// 弹窗显示控制
const showLocDialog = ref(false)
const showCamDialog = ref(false)
const isEditMode = ref(false)
const locFormRef = ref(null)

const locForm = reactive({ id: null, code: '', name: '', description: '' })
const camForm = reactive({
  id: null, name: '', code: '', ip_address: '', port: 554,
  username: '', password: '', location_id: null, status: 'offline', rtsp_url: ''
})

const rules = {
  code: [{ required: true, message: '必填项', trigger: 'blur' }],
  name: [{ required: true, message: '必填项', trigger: 'blur' }],
  location_id: [{ required: true, message: '请选择地点', trigger: 'change' }]
}

onMounted(() => {
  fetchLocations()
  fetchCameras()
  fetchSysConfig()
})

const handleLogout = () => {
  videoStore.logout()
  router.push('/login')
}

const fetchLocations = async () => {
  loading.value = true
  try {
    const res = await locationApi.getAll()
    if (res.success) locations.value = res.data
  } catch (error) {
    ElMessage.error('获取地点失败')
  } finally {
    loading.value = false
  }
}

const fetchCameras = async () => {
  try {
    const res = await cameraApi.getAll()
    if (res.success) cameras.value = res.data
  } catch (error) {
    ElMessage.error('获取设备失败')
  }
}

// --- 地点操作 ---
const openAddLocDialog = () => {
  isEditMode.value = false
  Object.assign(locForm, { id: null, code: '', name: '', description: '' })
  showLocDialog.value = true
  setTimeout(() => { if (locFormRef.value) locFormRef.value.clearValidate() }, 0)
}

const openEditLocDialog = (row) => {
  isEditMode.value = true
  Object.assign(locForm, row)
  showLocDialog.value = true
  setTimeout(() => { if (locFormRef.value) locFormRef.value.clearValidate() }, 0)
}

const submitLocation = async () => {
  if (!locFormRef.value) return
  await locFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        const apiCall = isEditMode.value ? locationApi.update(locForm.id, locForm) : locationApi.create(locForm)
        const res = await apiCall
        if (res.success) {
          ElMessage.success(isEditMode.value ? '保存成功' : '创建成功')
          showLocDialog.value = false
          fetchLocations()
        }
      } catch (e) { ElMessage.error('操作失败') }
    }
  })
}

const deleteLocation = (row) => {
  ElMessageBox.confirm(`确定要删除地点 "${row.name}" 吗？`, '警告', { type: 'warning' })
    .then(async () => {
      try {
        const res = await locationApi.delete(row.id)
        if (res.success) { ElMessage.success('删除成功'); fetchLocations() }
      } catch (error) { ElMessage.error('删除失败') }
    }).catch(() => { })
}

// --- 摄像仪操作 ---
const openAddCamDialog = () => {
  isEditMode.value = false
  Object.assign(camForm, {
    id: null, name: '', code: '', ip_address: '', port: 554,
    username: '', password: '', location_id: null, status: 'offline', rtsp_url: ''
  })
  showCamDialog.value = true
}

const openEditCamDialog = (row) => {
  isEditMode.value = true
  let ip = '', port = 554, user = '', pass = ''
  if (row.rtsp_url) {
    const match = row.rtsp_url.match(/rtsp:\/\/(?:(\w+):(\w+)@)?([\d\.]+)(?::(\d+))?/)
    if (match) {
      user = match[1] || ''
      pass = match[2] || ''
      ip = match[3] || ''
      port = match[4] || 554
    }
  }

  Object.assign(camForm, {
    id: row.id,
    name: row.name,
    code: row.code,
    location_id: row.location_id,
    status: row.status === 1 || row.status === 'online' ? 'online' : 'offline',
    ip_address: row.ip_address || ip,
    port: row.port || port,
    username: row.username || user,
    password: row.password || pass,
    rtsp_url: row.rtsp_url || '' // 🌟 回显
  })
  showCamDialog.value = true
}

const submitCamera = async () => {
  if (!camForm.location_id) return ElMessage.warning('请选择所属地点')
  if (!camForm.name) return ElMessage.warning('请输入设备名称')
  if (!camForm.code) return ElMessage.warning('请输入设备编号')
  if (!camForm.ip_address) return ElMessage.warning('请输入IP地址')

  // 🌟 如果用户手动填了 RTSP 地址，直接用用户的！否则才去拼接海康格式兜底。
  let finalRtspUrl = camForm.rtsp_url
  if (!finalRtspUrl) {
    if (camForm.username && camForm.password) {
      finalRtspUrl = `rtsp://${camForm.username}:${camForm.password}@${camForm.ip_address}:${camForm.port}/h264/ch1/main/av_stream`
    } else {
      finalRtspUrl = `rtsp://${camForm.ip_address}:${camForm.port}/h264/ch1/main/av_stream`
    }
  }

  const payload = {
    id: camForm.id,
    location_id: camForm.location_id,
    name: camForm.name,
    code: camForm.code,
    ip_address: camForm.ip_address,
    port: camForm.port,
    username: camForm.username,
    password: camForm.password,
    rtsp_url: finalRtspUrl, // 🌟 使用计算好的最终 URL
    status: camForm.status
  }

  try {
    const apiCall = isEditMode.value ? cameraApi.update(payload.id, payload) : cameraApi.create(payload)
    const res = await apiCall
    if (res.success) {
      ElMessage.success(isEditMode.value ? '保存成功' : '创建成功')
      showCamDialog.value = false
      fetchCameras()
    }
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.response?.data?.message || e.message))
  }
}

const deleteCamera = (row) => {
  ElMessageBox.confirm(`确定要删除设备 "${row.code}" 吗？`, '警告', { type: 'warning' })
    .then(async () => {
      try {
        const res = await cameraApi.delete(row.id)
        if (res.success) { ElMessage.success('删除成功'); fetchCameras() }
      } catch (error) { ElMessage.error('删除失败') }
    }).catch(() => { })
}

const getLocationName = (id) => {
  const loc = locations.value.find(l => l.id === id)
  return loc ? loc.name : '未知地点'
}
const sysConfig = ref({
  localBasePath: '',
  enableCloud: false,
  cloudProvider: 'aliyun',
  bucketName: '',
  endpoint: '',
  accessKeyId: '',
  accessKeySecret: '',
  cloudBasePath: '/coalmine/processed_videos/'
})

// 3. 增加占位的交互方法 
const saveConfig = async (type) => {
  try {
    const res = await configApi.saveConfig(sysConfig.value)
    if (res.success) {
      ElMessage.success(type === 'local' ? '本地存储配置已成功保存到数据库！' : '云端同步配置已成功保存到数据库！')
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (error) {
    ElMessage.error('保存失败，请检查服务器网络')
  }
}
const fetchSysConfig = async () => {
  try {
    const res = await configApi.getConfig()
    if (res.success && res.data) {
      // 把后端返回的真实数据覆盖到前端的表单模型中
      Object.assign(sysConfig.value, res.data)
    }
  } catch (error) {
    console.error("获取系统配置失败", error)
  }
}

const testCloudConnection = () => {
  if (!sysConfig.value.accessKeyId || !sysConfig.value.accessKeySecret) {
    ElMessage.warning('请先填写完整的密钥信息！')
    return
  }
  ElMessage.info('正在尝试连接云端...')
  // 模拟一个请求延迟
  setTimeout(() => {
    ElMessage.success('连接云端成功！您的参数配置无误。')
  }, 1500)
}
</script>

<style scoped>
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
  padding: 24px;
  background-color: #f1f5f9;
  flex: 1;
  overflow-y: auto;
}
.page-header {
  margin-bottom: 24px;
}
.page-header h2 {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: #1e293b;
}
.page-header p {
  margin: 0;
  color: #64748b;
}
.data-card {
  background: white;
  min-height: 500px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.tab-toolbar {
  margin-bottom: 20px;
}
.settings-container {
  padding: 10px 0;
}
.settings-card {
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.card-header {
  display: flex;
  align-items: center;
}
.form-tip {
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.5;
  margin-top: 4px;
}
.cloud-config-area {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px dashed #e2e8f0;
}
</style>