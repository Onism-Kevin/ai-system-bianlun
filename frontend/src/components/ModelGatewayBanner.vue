<script setup lang="ts">
import { computed } from 'vue'
import { useHealth, type GatewayState } from '../composables/useHealth'

// S2-F9：全局健康横幅 + health 徽标（api.md:74）。
// - 模型网关 down/degraded → 警告条（顶部，自动随轮询更新）；
// - 页脚 health 徽标：model_gateway + mysql 实时状态（匿名可读，降级也 200）。
// 集成到 TrainingView / DashboardView / ReviewView；单例 useHealth 保证三页共享
// 同一份状态与同一条轮询（不重复拉 /api/health）。
const { status, loading, unreachable, gatewayState, gatewayAlert, healthBadge, reload, start } =
  useHealth()

start()

const alertType = computed<'error' | 'warning'>(() =>
  gatewayState.value === 'down' ? 'error' : 'warning',
)
const alertTitle = computed(() =>
  gatewayState.value === 'down' ? '模型服务不可用' : '模型服务降级',
)
const alertDesc = computed(() =>
  gatewayState.value === 'down'
    ? '模型网关当前不可达，生成类操作可能失败，请稍后重试。'
    : '模型网关响应缓慢（超时），生成可能变慢，请耐心等待。',
)

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
  <!-- 模型网关告警横幅（S2-F9）：down/degraded 时显示，随 15s 轮询自动更新 -->
  <el-alert
    v-if="gatewayAlert"
    :title="alertTitle"
    :description="alertDesc"
    :type="alertType"
    show-icon
    class="health-banner"
  />

  <!-- health 徽标：model_gateway + mysql 状态（页脚） -->
  <div class="health-badge">
    <span class="badge-label">健康</span>
    <el-tag size="small" :type="gatewayTagType(healthBadge.gatewayState)" effect="plain">
      网关 {{ healthBadge.gateway }}
    </el-tag>
    <el-tag size="small" :type="mysqlTagType(healthBadge.mysql)" effect="plain">
      MySQL {{ healthBadge.mysql }}
    </el-tag>
    <span v-if="unreachable && !status" class="badge-unreachable">健康检查不可达</span>
    <el-button link size="small" :loading="loading" @click="reload">刷新</el-button>
  </div>
</template>

<style scoped>
.health-banner {
  margin-bottom: 12px;
}
.health-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding-top: 8px;
  margin-top: 8px;
}
.badge-label {
  font-weight: 600;
}
.badge-unreachable {
  color: var(--el-color-danger);
}
</style>
