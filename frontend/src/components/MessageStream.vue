<script setup lang="ts">
import { computed } from 'vue'
import { labelsForMode, roleLabel as resolveRoleLabel } from '../utils/roleLabels'

/**
 * S3-F4 commit A：消息流**纯渲染**组件。
 *
 * 接口边界（用户 2026-11-09 约束 1，必须死）：
 * - 接收 messages: RenderMessage[]（纯数据）
 * - 接收 mode: 'training' | 'drill'（决定默认标签）
 * - 接收 roleLabel?: (role, agentRole) => string（可选覆盖）
 *
 * 不做：
 * - 不管理 SSE 状态（streaming/connected 在父组件）
 * - 不处理发送逻辑（输入框在父组件）
 * - 不处理控制栏（在父组件）
 * - 不处理锚点跳转滚动（父组件监听后自己滚，或通过 id 自行处理）
 *
 * 只渲染：role / agent_role / content / status 徽标 / streaming 光标。
 */
interface RenderMessage {
  seq: number
  role: string
  agent_role?: string | null
  content: string
  status: string
  streaming?: boolean
}

const props = defineProps<{
  messages: RenderMessage[]
  mode: 'training' | 'drill'
  roleLabel?: (role: string, agentRole: string | null) => string
}>()

const labels = computed(() => labelsForMode(props.mode))

function displayLabel(m: RenderMessage): string {
  if (props.roleLabel) return props.roleLabel(m.role, m.agent_role ?? null)
  return resolveRoleLabel(m.role, m.agent_role, labels.value)
}

function agentTagType(
  m: RenderMessage,
): 'success' | 'info' | 'warning' | 'danger' | 'primary' {
  if (m.agent_role === 'pro') return 'success'
  if (m.agent_role === 'con') return 'danger'
  if (m.agent_role === 'judge') return 'primary'
  return 'info'
}
</script>

<template>
  <div v-if="messages.length === 0" class="empty">
    <el-empty :description="mode === 'drill' ? '还没有引导。教师发送第一条引导，AI 学生将回应。' : '还没有消息。发送第一条观点，AI 将开始回应。'" />
  </div>
  <div v-else class="msgs">
    <div
      v-for="m in messages"
      :id="'msg-' + m.seq"
      :key="m.seq"
      class="msg"
      :class="[m.role === 'user' ? 'is-user' : 'is-ai', m.agent_role ? 'role-' + m.agent_role : '']"
    >
      <div class="head">
        <b>{{ displayLabel(m) }}</b>
        <el-tag v-if="m.agent_role" :type="agentTagType(m)" size="small">{{ m.agent_role }}</el-tag>
        <span>seq {{ m.seq }}</span>
        <span v-if="m.status === 'paused_truncated'" class="trunc">已截断</span>
        <span v-if="m.streaming" class="live">生成中…</span>
      </div>
      <div class="content">{{ m.content }}<span v-if="m.streaming" class="cursor" /></div>
    </div>
  </div>
</template>

<style scoped>
.empty {
  padding: 12px 0;
}
.msgs {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 8px;
}
.msg {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--el-bg-color);
  /* 锚点跳转补偿：scrollIntoView 后消息不被 sticky 元素遮挡 */
  scroll-margin-top: 12px;
}
.msg.is-user {
  border-left: 3px solid var(--el-color-primary);
}
.msg.is-ai {
  border-left: 3px solid var(--el-color-success);
}
.msg.role-con {
  border-left-color: var(--el-color-danger);
}
.msg.role-judge {
  border-left-color: #8250df;
}
.head {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.trunc {
  color: var(--el-color-warning);
}
.live {
  color: var(--el-color-primary);
}
.content {
  font-size: 13.5px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.cursor {
  display: inline-block;
  width: 8px;
  height: 14px;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: var(--el-color-primary);
  animation: blink 1s step-end infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
