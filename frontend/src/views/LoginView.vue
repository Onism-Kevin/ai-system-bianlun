<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth'

// S2-F1 骨架：仅打通 store → api → axios → Cookie 链路（方案 A）；
// 校验/错误提示/跳转等业务逻辑后续任务补。
const auth = useAuthStore()
const username = ref('')
const password = ref('')

async function onSubmit() {
  await auth.login(username.value, password.value)
}
</script>

<template>
  <h1>登录</h1>
  <form @submit.prevent="onSubmit">
    <input v-model="username" placeholder="用户名" />
    <input v-model="password" type="password" placeholder="密码" />
    <button type="submit">登录</button>
  </form>
</template>
