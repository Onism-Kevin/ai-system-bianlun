<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
// S3-F1 commit A：全局顶部导航栏（裁定 5 纳入 S3-F1）。
// 登录页不显示导航栏（尚未登录，无角色可分流）。
import AppHeader from './components/AppHeader.vue'

const route = useRoute()
const showHeader = computed(() => route.path !== '/login')
</script>

<template>
  <AppHeader v-if="showHeader" />
  <router-view />
</template>
