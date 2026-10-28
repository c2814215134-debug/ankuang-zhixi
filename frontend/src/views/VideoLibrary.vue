<template>
  <el-container class="app-layout">
    <el-header class="app-header">
      <div class="header-left">
        <el-icon class="logo-icon" :size="28" color="#2563eb"
          ><VideoCameraFilled
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

      <el-main class="app-main" v-loading="loading">
        <div class="archive-container">
          <div class="directory-sidebar">
            <div class="tree-header">
              <div
                style="
                  font-weight: 600;
                  color: #1e293b;
                  font-size: 15px;
                  margin-bottom: 12px;
                "
              >
                <el-icon style="margin-right: 6px; vertical-align: -2px"
                  ><FolderOpened
                /></el-icon>
                视频归档目录
              </div>
              <el-input
                v-model="treeSearchQuery"
                placeholder="筛选目录名称..."
                prefix-icon="Search"
                clearable
              />
            </div>
            <div class="tree-content">
              <el-tree
                ref="folderTreeRef"
                :data="directoryTree"
                :props="defaultProps"
                :filter-node-method="filterNode"
                @node-click="handleNodeClick"
                highlight-current
                :current-node-key="currentFolder"
                node-key="name"
                default-expand-all
              >
                <template #default="{ node, data }">
                  <div
                    class="custom-tree-node"
                    :class="{ 'is-active': currentFolder === data.name }"
                  >
                    <el-icon color="#2563eb" v-if="data.name === '.'"
                      ><Menu
                    /></el-icon>
                    <el-icon color="#64748b" v-else><Folder /></el-icon>
                    <span class="node-label" :title="node.label">{{
                      node.label
                    }}</span>
                    <el-tag
                      v-if="data.count !== undefined"
                      size="small"
                      :type="data.count > 0 ? 'primary' : 'info'"
                      round
                      class="node-count"
                    >
                      {{ data.count }}
                    </el-tag>
                  </div>
                </template>
              </el-tree>
            </div>
          </div>

          <div class="content-area">
            <div class="content-header">
              <el-breadcrumb separator="/">
                <el-breadcrumb-item>视频归档库</el-breadcrumb-item>
                <el-breadcrumb-item style="font-weight: bold">
                  {{ currentFolder === "." ? "全部视频" : currentFolder }}
                </el-breadcrumb-item>
              </el-breadcrumb>

              <div
                class="filter-actions"
                style="display: flex; align-items: center"
              >
                <el-input
                  v-model="searchQuery"
                  placeholder="搜索当前目录下的视频..."
                  prefix-icon="Search"
                  clearable
                  style="width: 260px; margin-right: 12px"
                  @input="handleSearch"
                />
                <el-button
                  type="info"
                  plain
                  icon="RefreshRight"
                  @click="fetchFolders"
                  >刷新</el-button
                >
              </div>
            </div>

            <div class="video-grid-wrapper">
              <div v-if="paginatedVideos.length > 0" class="video-grid">
                <div
                  v-for="video in paginatedVideos"
                  :key="video.name"
                  class="video-card"
                >
                  <div class="card-cover" @click="playVideo(video)">
                    <div v-show="!video.loaded" class="cover-skeleton">
                      <el-icon class="is-loading" :size="28"
                        ><Loading
                      /></el-icon>
                    </div>

                    <video
                      v-lazy="getVideoUrl(video.path)"
                      class="video-thumb"
                      :class="{ 'is-loaded': video.loaded }"
                      preload="metadata"
                      muted
                      @loadeddata="handleVideoLoaded($event, video)"
                    ></video>

                    <div class="play-overlay">
                      <el-icon class="play-icon"><CaretRight /></el-icon>
                    </div>
                  </div>

                  <div class="card-body">
                    <div class="video-title" :title="video.name">
                      {{ video.name }}
                    </div>

                    <div class="video-tags-row">
                      <el-tag
                        size="small"
                        :color="getProcessInfo(video.name).color"
                        effect="dark"
                        class="process-tag"
                        style="border: none"
                      >
                        {{ getProcessInfo(video.name).text }}
                      </el-tag>

                      <el-tag
                        v-if="currentFolder === '.'"
                        size="small"
                        type="info"
                        effect="plain"
                        class="source-tag"
                      >
                        来自: {{ getFolderName(video.path) }}
                      </el-tag>
                    </div>

                    <div class="video-meta-row">
                      <span class="video-size">{{ video.size }}</span>
                      <el-button
                        type="primary"
                        link
                        size="small"
                        @click="playVideo(video)"
                      >
                        <el-icon style="margin-right: 4px"
                          ><VideoPlay
                        /></el-icon>
                        播放
                      </el-button>
                    </div>
                  </div>
                </div>
              </div>

              <div v-else class="empty-state">
                <el-empty
                  :description="
                    searchQuery
                      ? '未搜索到匹配的视频'
                      : currentFolder
                      ? '该目录下暂无有效视频片段'
                      : '请在左侧选择一个目录'
                  "
                />
              </div>
            </div>

            <div
              class="pagination-wrapper"
              v-if="filteredVideosList.length > 0"
            >
              <el-pagination
                background
                layout="total, sizes, prev, pager, next, jumper"
                :total="filteredVideosList.length"
                v-model:current-page="currentPage"
                v-model:page-size="pageSize"
                :page-sizes="[12, 24, 36, 48]"
                @size-change="handleSizeChange"
                @current-change="handleCurrentChange"
              />
            </div>
          </div>
        </div>

        <el-dialog
          v-model="playerVisible"
          title="视频回放检索"
          width="800px"
          destroy-on-close
          center
        >
          <div class="video-container" v-if="currentVideoUrl">
            <video
              controls
              autoplay
              width="100%"
              height="450"
              :src="currentVideoUrl"
              style="border-radius: 8px; background: #000"
            >
              您的浏览器不支持 Video 标签。
            </video>
          </div>
        </el-dialog>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { folderApi, videoApi } from '../api'
import { useVideoStore } from '../store'
import { ElMessage } from 'element-plus'
import {
  VideoCameraFilled, CaretRight, VideoPlay, Loading,
  FolderOpened, Folder, Menu, RefreshRight, Search
} from '@element-plus/icons-vue'
import AppSidebar from '../components/AppSidebar.vue'

const router = useRouter()
const route = useRoute()
const videoStore = useVideoStore()
const username = ref(videoStore.username || 'Admin')

const loading = ref(false)
const folders = ref([])
const videos = ref([])
const currentFolder = ref('.') // 默认指向全部

const currentPage = ref(1)
const pageSize = ref(12)

const playerVisible = ref(false)
const currentVideoUrl = ref('')

// 🌟 右侧视频搜索状态
const searchQuery = ref('')

// 🌟 左侧树搜索状态与引用
const treeSearchQuery = ref('')
const folderTreeRef = ref(null)

const defaultProps = { children: 'children', label: 'label' }

// === 动态计算树结构数据 ===
const directoryTree = computed(() => {
  const totalCount = folders.value.reduce((sum, f) => sum + (f.video_count || 0), 0)
  return [
    { label: '全部视频', name: '.', count: totalCount },
    ...folders.value.map(f => ({
      label: f.name,
      name: f.name,
      count: f.video_count
    }))
  ]
})

// === 目录树过滤逻辑 ===
watch(treeSearchQuery, (val) => {
  if (folderTreeRef.value) {
    folderTreeRef.value.filter(val)
  }
})

const filterNode = (value, data) => {
  if (!value) return true
  return data.label.toLowerCase().includes(value.toLowerCase())
}

// === 视频过滤与分页逻辑 ===
const filteredVideosList = computed(() => {
  if (!searchQuery.value) return videos.value
  const lowerQuery = searchQuery.value.toLowerCase()
  return videos.value.filter(video => video.name.toLowerCase().includes(lowerQuery))
})

const paginatedVideos = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredVideosList.value.slice(start, end)
})

const handleSearch = () => {
  currentPage.value = 1
}

const handleLogout = () => {
  videoStore.logout()
  router.push('/login')
}

// === 自定义懒加载指令 ===
const vLazy = {
  mounted: (el, binding) => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.src = binding.value
          observer.unobserve(el)
        }
      },
      { rootMargin: '100px 0px', threshold: 0.01 }
    )
    observer.observe(el)
    el._observer = observer
  },
  unmounted: (el) => {
    if (el._observer) el._observer.disconnect()
  }
}

const handleVideoLoaded = (event, video) => {
  video.loaded = true
  const target = event.target
  if (target.duration && target.duration > 1) {
    target.currentTime = 1
  }
}

onMounted(async () => {
  await fetchFolders()
})

const fetchFolders = async () => {
  try {
    const res = await folderApi.getFolders()
    if (res.success) {
      folders.value = res.folders || []
      const targetFolder = route.query.folder
      if (targetFolder && folders.value.some(f => f.name === targetFolder)) {
        await selectFolder(targetFolder)
      } else {
        await selectFolder('.')
      }
    }
  } catch (error) {
    console.error('获取目录失败', error)
  }
}

// === 点击左侧树节点 ===
const handleNodeClick = (data) => {
  if (currentFolder.value !== data.name) {
    selectFolder(data.name)
  }
}

const selectFolder = async (folderName) => {
  currentFolder.value = folderName
  searchQuery.value = '' // 切换目录时清空视频搜索痕迹
  loading.value = true
  videos.value = []
  currentPage.value = 1

  try {
    let rawVideos = []
    if (folderName === '.') {
      const subFolders = folders.value.filter(f => f.name !== '.')
      const promises = subFolders.map(f =>
        folderApi.getFolderVideos(f.name).catch(() => ({ success: false }))
      )
      const results = await Promise.all(promises)
      results.forEach(res => {
        if (res && res.success && res.videos) {
          rawVideos.push(...res.videos)
        }
      })
    } else {
      const res = await folderApi.getFolderVideos(folderName)
      if (res.success) {
        rawVideos = res.videos || []
      }
    }

    const filteredVideos = rawVideos.filter(v => {
      if (!v.size) return false
      const sizeStr = v.size.split(' ')[0]
      const sizeNum = parseFloat(sizeStr)
      return sizeNum >= 0.5
    }).map(v => ({ ...v, loaded: false }))

    videos.value = filteredVideos

  } catch (error) {
    ElMessage.error('加载视频列表失败')
  } finally {
    loading.value = false
  }
}

const handleSizeChange = (val) => {
  pageSize.value = val
  currentPage.value = 1
}
const handleCurrentChange = (val) => {
  currentPage.value = val
}

const playVideo = (video) => {
  currentVideoUrl.value = getVideoUrl(video.path)
  playerVisible.value = true
}

const getVideoUrl = (path) => videoApi.getVideoUrl(path)
const getFolderName = (path) => path.includes('/') ? path.split('/')[0] : '未知'

const getProcessInfo = (filename) => {
  const rawName = filename.split('_')[0]
  if (rawName.includes('开孔')) return { text: '开孔工序', color: '#409EFF' }
  if (rawName.includes('验孔')) return { text: '验孔工序', color: '#F56C6C' }
  if (rawName.includes('验煤')) return { text: '验煤工序', color: '#9C27B0' }
  if (rawName.includes('止煤')) return { text: '止煤工序', color: '#E6A23C' }
  if (rawName.includes('见煤')) return { text: '见煤工序', color: '#009688' }
  if (rawName.includes('封孔')) return { text: '封孔工序', color: '#909399' }
  if (rawName.includes('终孔')) return { text: '终孔工序', color: '#67C23A' }
  return { text: rawName || '未知工序', color: '#909399' }
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
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 🌟 核心布局 */
.archive-container {
  display: flex;
  height: 100%;
  gap: 20px;
}

/* 🌟 左侧树状目录 */
.directory-sidebar {
  width: 260px;
  background: white;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}
.tree-header {
  padding: 16px;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}
.tree-content {
  flex: 1;
  padding: 10px;
  overflow-y: auto;
}
.custom-tree-node {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 8px;
  padding-right: 8px;
}
.node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}
.custom-tree-node.is-active .node-label {
  font-weight: 600;
  color: #2563eb;
}

/* 🌟 右侧内容区 */
.content-area {
  flex: 1;
  background: white;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.content-header {
  padding: 16px 24px;
  border-bottom: 1px solid #e2e8f0;
  background: #ffffff;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.video-grid-wrapper {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  background: #f8fafc;
}
.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 24px;
}
.empty-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 视频卡片样式保留 */
.video-card {
  background: white;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  height: 260px;
  transition: all 0.3s ease;
}
.video-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  border-color: #cbd5e1;
}
.card-cover {
  height: 146px;
  background: #0b0f19;
  position: relative;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
}
.cover-skeleton {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  z-index: 1;
}
.video-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transition: opacity 0.5s;
}
.video-thumb.is-loaded {
  opacity: 1;
}
.play-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.3s;
  z-index: 2;
}
.video-card:hover .play-overlay {
  opacity: 1;
}
.play-icon {
  font-size: 48px;
  color: white;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.5));
}

.card-body {
  padding: 12px;
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.video-title {
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
  margin-bottom: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.video-tags-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
  height: 24px;
  overflow: hidden;
}
.source-tag {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.video-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px dashed #e2e8f0;
  padding-top: 8px;
}
.video-size {
  font-size: 12px;
  color: #94a3b8;
  font-family: monospace;
}

.pagination-wrapper {
  padding: 16px 24px;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  background: white;
}
</style>