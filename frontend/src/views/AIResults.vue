<template>
  <el-container class="app-layout">
    <el-header class="app-header">
      <div class="header-left">
        <el-icon class="logo-icon" :size="28" color="#2563eb"><Aim /></el-icon>
        <span class="brand-text">煤矿钻场视频智能剪辑与数据管理平台</span>
      </div>
    </el-header>

    <el-container class="main-container">
      <AppSidebar />

      <el-main class="app-main">
        <div class="page-header">
          <h2>AI 识别结果台账</h2>
          <p>接收并展示本地端设备回传的钻场工序识别记录</p >
        </div>

        <el-card shadow="never" class="data-card">
          <div class="table-toolbar">
            <div class="search-area">
              <el-input
                v-model="searchQuery"
                placeholder="搜索钻孔编号或工序"
                style="width: 250px; margin-right: 12px"
                clearable
              >
                <template #prefix>
                  <el-icon><Search /></el-icon>
                </template>
              </el-input>
              <el-button @click="fetchLogs" :icon="Refresh">刷新数据</el-button>
            </div>
            <div class="action-area">
              <el-button type="primary" plain>
                <el-icon><Download /></el-icon> 导出表格
              </el-button>
            </div>
          </div>

          <el-table
            v-loading="loading"
            :data="paginatedData"
            border
            stripe
            style="width: 100%"
            height="calc(100vh - 280px)"
          >
            <el-table-column
              label="序号"
              width="60"
              align="center"
            >
              <template #default="scope">
                {{ (currentPage - 1) * pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>

            <el-table-column label="抓拍图像" width="140" align="center">
              <template #default="scope">
                <el-image
                  style="width: 100px; height: 60px; border-radius: 4px"
                  :src="getImageSrc(scope.row.screenshot_base64)"
                  :preview-src-list="[getImageSrc(scope.row.screenshot_base64)]"
                  fit="cover"
                  preview-teleported
                >
                  <template #error>
                    <div class="image-slot" style="font-size: 12px">
                      暂无截图
                    </div>
                  </template>
                </el-image>
              </template>
            </el-table-column>

            <el-table-column
              prop="detect_time"
              label="识别时间"
              width="180"
              align="center"
              sortable
            />

            <el-table-column label="位置信息" min-width="150" align="center">
              <template #default="scope">
                <div style="font-weight: bold">
                  {{ scope.row.mine_name || "-" }}
                </div>
                <div style="font-size: 12px; color: #64748b">
                  {{ scope.row.drill_location || "-" }}
                </div>
              </template>
            </el-table-column>

            <el-table-column label="钻孔编号" width="120" align="center">
              <template #default="scope">
                <el-tag type="info" effect="plain" v-if="scope.row.drill_no">
                  {{ scope.row.drill_no }}
                </el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>

            <el-table-column label="识别工序" width="120" align="center">
              <template #default="scope">
                <el-tag
                  :type="getProcessTagType(scope.row.process_name)"
                  effect="light"
                >
                  {{ scope.row.process_name || "未知工序" }}
                </el-tag>
              </template>
            </el-table-column>

            <el-table-column
              label="关联视频文件"
              min-width="160"
              align="center"
            >
              <template #default="scope">
                <el-button
                  v-if="scope.row.video_filename"
                  type="primary"
                  link
                  @click="jumpToLibrary(scope.row.video_filename)"
                >
                  <el-icon style="margin-right: 4px"><VideoCamera /></el-icon>
                  {{ scope.row.video_filename }}
                </el-button>
                <span v-else>-</span>
              </template>
            </el-table-column>

            <el-table-column
              prop="remark"
              label="备注信息"
              min-width="180"
              show-overflow-tooltip
            />

            <el-table-column
              label="操作"
              width="80"
              align="center"
              fixed="right"
            >
              <template #default="scope">
                <el-button
                  type="danger"
                  link
                  @click="handleDelete(scope.row.id)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              background
              v-model:current-page="currentPage"
              v-model:page-size="pageSize"
              layout="total, prev, pager, next, jumper"
              :total="filteredData.length"
            />
          </div>
        </el-card>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppSidebar from '../components/AppSidebar.vue'
import {
  Aim, Search, Download, FolderOpened, VideoCamera, Refresh
} from '@element-plus/icons-vue'

import { detectionApi } from '../api/index'

const router = useRouter()
const tableData = ref([])
const loading = ref(false)
const searchQuery = ref('')

// 分页相关的状态变量
const currentPage = ref(1)
const pageSize = ref(10) // 每页显示10条

// 1. 获取真实数据
const fetchLogs = async () => {
  loading.value = true
  try {
    const res = await detectionApi.getLogs()
    if (res.success) {
      tableData.value = res.data
    } else {
      ElMessage.error(res.message || '获取台账记录失败')
    }
  } catch (error) {
    ElMessage.error('网络请求失败')
  } finally {
    loading.value = false
  }
}

// 2. 本地前端过滤 (支持搜编号或工序)
const filteredData = computed(() => {
  if (!searchQuery.value) return tableData.value
  const q = searchQuery.value.toLowerCase()
  return tableData.value.filter(item =>
    (item.drill_no && item.drill_no.toLowerCase().includes(q)) ||
    (item.process_name && item.process_name.toLowerCase().includes(q))
  )
})

// 监听搜索词变化，如果发生搜索，把页码重置到第一页
watch(searchQuery, () => {
  currentPage.value = 1
})

// 计算当前页需要显示的数据
const paginatedData = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredData.value.slice(start, end)
})

// 3. 处理 Base64 图片格式
const getImageSrc = (base64Str) => {
  if (!base64Str) return ''
  if (!base64Str.startsWith('data:image')) {
    return `data:image/jpeg;base64,${base64Str}`
  }
  return base64Str
}

// 4. 根据工序文字返回不同颜色的标签
const getProcessTagType = (process) => {
  if (!process) return 'info'
  const map = {
    '开孔': 'info',
    '见煤': 'warning',
    '终孔': 'success',
    '封孔': 'danger'
  }
  for (const key in map) {
    if (process.includes(key)) return map[key]
  }
  return 'primary'
}

// 5. 跳转到视频库并传递文件/文件夹参数
const jumpToLibrary = (filename) => {
  const folderName = filename.split('.')[0]
  router.push({
    path: '/library',
    query: { folder: folderName }
  })
}

// 6. 删除测试数据
const handleDelete = (id) => {
  ElMessageBox.confirm('确定要删除这条识别记录吗？', '提示', {
    type: 'warning'
  }).then(async () => {
    try {
      const res = await detectionApi.deleteLog(id)
      if (res.success) {
        ElMessage.success('删除成功')
        fetchLogs() // 刷新表格
        
        // 如果删除后当前页空了且不是第一页，则退回上一页
        if (paginatedData.value.length === 1 && currentPage.value > 1) {
          currentPage.value--
        }
      } else {
        ElMessage.error(res.message)
      }
    } catch (error) {
      ElMessage.error('删除失败')
    }
  }).catch(() => { })
}

// 页面加载时自动获取数据
onMounted(() => {
  fetchLogs()
})
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
  align-items: center;
  padding: 0 24px;
  height: 60px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  font-size: 18px;
  color: #1e293b;
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
  border-radius: 8px;
  border: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
.table-toolbar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
}
.search-area {
  display: flex;
  align-items: center;
}

.image-slot {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  background: #f1f5f9;
  color: #94a3b8;
}

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>