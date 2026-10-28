<template>
  <el-aside width="220px" class="app-sidebar">
    <el-menu
      :default-active="route.path"
      class="sidebar-menu"
      router
      background-color="#ffffff"
      text-color="#475569"
      active-text-color="#2563eb"
    >

      <el-menu-item index="/ai-results">
        <el-icon><Aim /></el-icon>
        <span>AI 识别台账</span>
      </el-menu-item>
      <el-menu-item index="/library">
        <el-icon><VideoCamera /></el-icon>
        <span>视频归档库</span>
      </el-menu-item>

      <el-menu-item index="/basic-data">
        <el-icon><DataBoard /></el-icon>
        <span>基础数据</span>
      </el-menu-item>

      <el-menu-item index="/monitor">
        <el-icon><Monitor /></el-icon>
        <span>实时监控</span>
      </el-menu-item>
    </el-menu>
  </el-aside>
</template>

<script setup>
import { useRoute } from 'vue-router'
// 引入 Aim 图标作为靶向/识别的隐喻，替代之前的 Cpu 图标
import { Odometer, DataBoard, Tickets, Monitor, VideoCamera, Aim } from '@element-plus/icons-vue'

const route = useRoute()
</script>

<style scoped>
.app-sidebar {
  background-color: #ffffff;
  height: 100%;
  border-right: 1px solid #e2e8f0;
  transition: width 0.3s;
}
.sidebar-menu {
  border-right: none;
  padding-top: 10px;
}
</style>