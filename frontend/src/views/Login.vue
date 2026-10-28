<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-header">
        <el-icon class="logo-icon" :size="40" color="#2563eb"
          ><Monitor
        /></el-icon>
        <h2 class="title">煤矿钻场视频智能剪辑与数据管理平台</h2>
        <p class="subtitle">
          {{ isRegisterMode ? "用户注册" : "用户登录" }}
        </p>
      </div>

      <el-form
        ref="authFormRef"
        :model="authForm"
        :rules="rules"
        class="login-form"
        @keyup.enter="handleSubmit"
      >
        <!-- 用户名输入框 -->
        <el-form-item prop="username">
          <el-input
            v-model="authForm.username"
            :placeholder="
              isRegisterMode
                ? '请输入用户名 (需包含字母和数字)'
                : '请输入用户名'
            "
            size="large"
            :prefix-icon="User"
            clearable
          />
        </el-form-item>

        <!-- 密码输入框 -->
        <el-form-item prop="password">
          <el-input
            v-model="authForm.password"
            type="password"
            :placeholder="
              isRegisterMode ? '请输入密码 (>6位, 字母+数字)' : '请输入密码'
            "
            size="large"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>

        <!-- 提交按钮 -->
        <el-button
          type="primary"
          class="submit-btn"
          size="large"
          :loading="loading"
          @click="handleSubmit"
        >
          {{ isRegisterMode ? "立即注册" : "立即登录" }}
        </el-button>

        <!-- 切换登录/注册模式的文字按钮 -->
        <div class="toggle-text" @click="toggleMode">
          {{ isRegisterMode ? "已有账号？去登录" : "没有账号？去注册" }}
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { Monitor, User, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useVideoStore } from '../store'
import { authApi } from '../api'

const router = useRouter()
const videoStore = useVideoStore()

const isRegisterMode = ref(false)
const loading = ref(false)
const authFormRef = ref(null)

const authForm = reactive({
  username: '',
  password: ''
})

// 表单校验规则
const validateUsername = (rule, value, callback) => {
  if (!value) {
    callback(new Error('请输入用户名'))
    return
  }
  // 只有在注册模式下，才进行严格的正则校验
  if (isRegisterMode.value) {
    const pattern = /^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]+$/
    if (!pattern.test(value)) {
      callback(new Error('用户名必须是字母和数字的组合'))
      return
    }
  }
  callback()
}

const validatePassword = (rule, value, callback) => {
  if (!value) {
    callback(new Error('请输入密码'))
    return
  }
  // 只有在注册模式下，才进行严格的长度和正则校验
  if (isRegisterMode.value) {
    const pattern = /^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]+$/
    if (value.length <= 6) {
      callback(new Error('密码必须多于6位'))
      return
    }
    if (!pattern.test(value)) {
      callback(new Error('密码必须是字母和数字的组合'))
      return
    }
  }
  callback()
}

const rules = {
  username: [{ validator: validateUsername, trigger: 'blur' }],
  password: [{ validator: validatePassword, trigger: 'blur' }]
}

// 🌟 核心优化：切换模式时清空输入框及红色校验提示
const toggleMode = () => {
  isRegisterMode.value = !isRegisterMode.value
  authForm.username = ''
  authForm.password = ''
  if (authFormRef.value) {
    authFormRef.value.clearValidate()
  }
}

const handleSubmit = () => {
  if (!authFormRef.value) return
  authFormRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true
      if (isRegisterMode.value) {
        try {
          const res = await authApi.register({ username: authForm.username, password: authForm.password })
          if (res.success) {
            ElMessage.success('注册成功，请登录')
            toggleMode() // 注册成功后，自动帮你切回登录界面并清空表单
          }
        } catch (error) {
          const errMsg = error.response?.data?.message || '注册失败，服务器异常'
          ElMessage.error(errMsg)
        } finally {
          loading.value = false
        }
      } else {
        const result = await videoStore.login(authForm.username, authForm.password)
        loading.value = false
        if (result.success) {
          ElMessage.success('登录成功，欢迎回来！')
          router.push('/')
        } else {
          ElMessage.error(result.message)
        }
      }
    }
  })
}
</script>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #f1f5f9;
  background-image: radial-gradient(#cbd5e1 1px, transparent 1px);
  background-size: 20px 20px;
}

.login-box {
  width: 400px;
  padding: 40px;
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1),
    0 10px 10px -5px rgba(0, 0, 0, 0.04);
  text-align: center;
}
.login-header {
  margin-bottom: 30px;
}
.title {
  font-size: 20px;
  color: #1e293b;
  margin: 10px 0 5px 0;
}
.subtitle {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}
.submit-btn {
  width: 100%;
  margin-top: 10px;
}
.toggle-text {
  margin-top: 16px;
  font-size: 14px;
  color: #2563eb;
  cursor: pointer;
  user-select: none;
}
.toggle-text:hover {
  text-decoration: underline;
}
</style>