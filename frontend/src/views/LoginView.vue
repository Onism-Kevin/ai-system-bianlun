<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { register as registerApi } from '../api/auth'
import { describeApiError } from '../api/errors'

// S2-F2：登录页正式化——element-plus 表单 + api.md §3 错误分类提示。
// 登录态走 S2-1 set_cookie（httpOnly Cookie，axios withCredentials 自动
// 携带，同源零配置——permissions §6.3 / sse_events §9 方案 A）。
// 注册（api.md:25）不签发 Cookie：注册成功后停留在本页提示登录。
const auth = useAuthStore()
const router = useRouter()

const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '' })
const loading = ref(false)
const message = ref<{ text: string; type: 'error' | 'success' } | null>(null)

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

function showMessage(text: string, type: 'error' | 'success') {
  message.value = { text, type }
}

/** 表单校验通过后执行 action；失败按 api.md §3 分类提示，loading 收尾。 */
function withValidatedForm(action: () => Promise<void>) {
  message.value = null
  if (!formRef.value) return
  formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      await action()
    } catch (err) {
      showMessage(describeApiError(err), 'error')
    } finally {
      loading.value = false
    }
  })
}

function onSubmit() {
  withValidatedForm(async () => {
    await auth.login(form.username, form.password)
    router.push('/dashboard') // 登录成功进 dashboard（S2-F3 起补路由守卫）
  })
}

function onRegister() {
  withValidatedForm(async () => {
    await registerApi(form.username, form.password)
    showMessage('注册成功，请登录', 'success')
  })
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <h1 class="login-title">思辨工坊</h1>
      <el-alert
        v-if="message"
        :title="message.text"
        :type="message.type"
        show-icon
        :closable="false"
        class="login-alert"
      />
      <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="用户名" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            autocomplete="current-password"
            show-password
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="onSubmit">登录</el-button>
          <el-button :loading="loading" @click="onRegister">注册</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-card {
  width: 360px;
}
.login-title {
  text-align: center;
  margin: 0 0 16px;
}
.login-alert {
  margin-bottom: 16px;
}
</style>
