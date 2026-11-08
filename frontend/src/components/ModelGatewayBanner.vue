<script setup lang="ts">
import { computed } from 'vue'
import { useHealth } from '../composables/useHealth'

// S2-F9：模型网关告警横幅（api.md:74）。
// S3-F1 拆分：health 徽标已抽为 HealthBadge.vue，由 AppHeader 在导航栏渲染；
// 本组件只保留"模型网关 down/degraded 时显示的告警条"。
// 单例 useHealth 保证所有挂载点共享同一份状态与同一条轮询。
// （刷新按钮随徽标移到 HealthBadge，本组件不再需要 loading/reload）
const { gatewayState, gatewayAlert, start } = useHealth()

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
</script>

<template>
  <!-- 模型网关告警横幅：down/degraded 时显示，随 15s 轮询自动更新 -->
  <el-alert
    v-if="gatewayAlert"
    :title="alertTitle"
    :description="alertDesc"
    :type="alertType"
    show-icon
    class="health-banner"
  />
</template>

<style scoped>
.health-banner {
  margin-bottom: 12px;
}
</style>
