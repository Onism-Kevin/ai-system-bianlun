<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getSession } from '../api/sessions'
import { describeApiError, isUnauthorized } from '../api/errors'
import type { SessionOut } from '../api/types'

// S2-F4 训练页骨架（参考 docs/prototypes/training.html）：
// - 会话信息真实拉取（GET /api/sessions/{id}，S2-3 已交付，api.md:29 平铺七字段）
// - 消息流/输入/训练控制为占位：SSE 接入 S2-F5、控制端点 S2-6
// - 进入方式：dashboard 历史行点击 / 创建会话成功跳转，均带 ?id=
const route = useRoute()
const router = useRouter()

const session = ref<SessionOut | null>(null)

onMounted(async () => {
  const rawId = route.query.id
  const id = Number(rawId)
  if (!rawId || !Number.isInteger(id) || id <= 0) {
    ElMessage.error('缺少会话 id')
    router.push('/dashboard')
    return
  }
  try {
    session.value = await getSession(id)
  } catch (err) {
    if (isUnauthorized(err)) {
      router.push('/login')
      return
    }
    ElMessage.error(describeApiError(err))
    router.push('/dashboard')
  }
})

function statusTagType(status: string): 'success' | 'info' | 'warning' | 'danger' | 'primary' {
  if (status === 'generating') return 'warning'
  if (status === 'paused') return 'primary'
  if (status === 'finished') return 'success'
  if (status === 'failed') return 'danger'
  return 'info' // waiting
}
</script>

<template>
  <div class="page">
    <div class="hdr">
      <div>
        <h1>训练页 · 人机论证训练</h1>
        <span class="sub">会话信息真实拉取；消息流与训练控制将在后续任务接入</span>
      </div>
      <el-button link type="primary" @click="router.push('/dashboard')">← 工作台</el-button>
    </div>

    <el-card>
      <template #header>会话信息（GET /api/sessions/{id}，api.md:29）</template>
      <div v-if="session" class="kv">
        <span><b>会话</b> #{{ session.id }}</span>
        <span><b>议题</b> {{ session.topic }}</span>
        <span><b>visibility</b> {{ session.visibility }}</span>
        <span v-if="session.task_id !== null"><b>task_id</b> {{ session.task_id }}</span>
        <span>
          <b>状态</b>
          <el-tag :type="statusTagType(session.status)" size="small">{{ session.status }}</el-tag>
        </span>
      </div>
      <p v-else class="muted">加载中……</p>
      <p class="muted">mode/max_turns 为运行参数不落库（api.md 脚注 1），创建时指定。</p>
    </el-card>

    <el-card>
      <template #header>辩论对话</template>
      <el-empty description="消息流将在 SSE 接入（S2-F5）后显示" />
    </el-card>

    <el-card>
      <template #header>消息输入</template>
      <el-input
        type="textarea"
        :rows="4"
        disabled
        placeholder="消息输入将在 SSE 接入（S2-F5）后开放"
      />
      <el-button type="primary" disabled>发送</el-button>
      <p class="muted">
        用户消息本地渲染、不走 SSE 回显（用户 2026-10-13 裁定，sse_events.md §4 补注）。
      </p>
    </el-card>

    <el-card>
      <template #header>训练控制</template>
      <div class="controls">
        <el-button disabled>暂停（pause）</el-button>
        <el-button disabled>续写（resume）</el-button>
        <el-button disabled>重开（restart）</el-button>
        <el-button disabled>加速（quick）</el-button>
      </div>
      <p class="muted">
        pause/quick 仅 generating；resume 仅 paused；restart 于 generating 中 409（先暂停）。
        状态机规则见 api.md:31-35，接入 S2-6。
      </p>
    </el-card>
  </div>
</template>

<style scoped>
.page {
  max-width: 1060px;
  margin: 0 auto;
  padding: 0 16px 48px;
}
.hdr {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 20px 0 12px;
}
.hdr h1 {
  font-size: 20px;
  margin: 0 0 4px;
}
.sub {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.kv {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 13px;
}
.kv b {
  color: var(--el-text-color-secondary);
  font-weight: 600;
  margin-right: 4px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
.controls {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
