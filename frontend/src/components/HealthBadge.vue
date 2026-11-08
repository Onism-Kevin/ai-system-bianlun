<script setup lang="ts">
import { useHealth, type GatewayState } from '../composables/useHealth'

// S3-F1：health 徽标独立组件（从 ModelGatewayBanner 拆出）。
// 原 ModelGatewayBanner 同时含告警横幅 + 徽标；导航栏要复用健康状态，
// 故把徽标抽为独立组件，由 AppHeader 在导航栏内渲染。
//
// 本组件挂在全局 AppHeader 中（始终挂载），故负责 start() 启动轮询——
// 即使当前页面没有渲染 ModelGatewayBanner，健康状态仍持续轮询
// （useHealth 是模块级单例 + 引用计数，多处挂载共享同一条轮询）。
const { unreachable, loading, healthBadge, reload, start } = useHealth()

start()

function gatewayTagType(
  s: GatewayState,
): 'success' | 'warning' | 'danger' | 'info' {
  if (s === 'ok') return 'success'
  if (s === 'degraded') return 'warning'
  if (s === 'down') return 'danger'
  return 'info'
}

function mysqlTagType(m: string): 'success' | 'danger' | 'info' {
  if (m === 'ok') return 'success'
  if (m === 'down') return 'danger'
  return 'info'
}
</script>

<template>
  <div class="health-badge">
    <span class="badge-label">健康</span>
    <el-tag size="small" :type="gatewayTagType(healthBadge.gatewayState)" effect="plain">
      网关 {{ healthBadge.gateway }}
    </el-tag>
    <el-tag size="small" :type="mysqlTagType(healthBadge.mysql)" effect="plain">
      MySQL {{ healthBadge.mysql }}
    </el-tag>
    <span v-if="unreachable" class="badge-unreachable">健康检查不可达</span>
    <el-button link size="small" :loading="loading" @click="reload">刷新</el-button>
  </div>
</template>

<style scoped>
.health-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.badge-label {
  font-weight: 600;
}
.badge-unreachable {
  color: var(--el-color-danger);
}
</style>
