<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import {
  createSession,
  getSession,
  listMessages,
  submitMessage,
  pauseSession,
  resumeSession,
  restartSession,
  quickSession,
} from '../../api/sessions'
import { describeApiError, isUnauthorized } from '../../api/errors'
import { useSSE } from '../../composables/useSSE'
import type { UseSseResult } from '../../composables/useSSE'
import ModelGatewayBanner from '../../components/ModelGatewayBanner.vue'
import MessageStream from '../../components/MessageStream.vue'
import { useLoadError } from '../../composables/useLoadError'
import type { SessionOut } from '../../api/types'

// S3-F4 commit C：教学情境演练页（S3-6 drill 模式）。
// AI 扮"持正方立场的学生"，教师练引导（追问/拉回证据/总结分歧）。
// 与 TrainingView 同构的 SSE 状态层（messageMap/upsert/maxSeq/loadHistory/
// connectSse）——**内联复制**，S4/S5 若出现第三个 SSE 页面再抽 useChatSession
// （记入 s3_open_items.md）。
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const { loadError, goLogin, handleLoadError, errorTitle, errorDesc } = useLoadError({
  forbiddenTitle: '无权访问演练',
  forbiddenDesc: '你不是教师，无法进入情境演练',
  notFoundTitle: '演练不存在',
  notFoundDesc: '演练会话不存在或已删除',
})

const session = ref<SessionOut | null>(null)
const sessionId = ref<number>(0)

interface ChatMessage {
  seq: number
  role: 'user' | 'assistant' | 'system'
  agent_role: 'pro' | 'con' | 'judge' | 'coach' | null
  content: string
  status: 'streaming' | 'complete' | 'paused_truncated'
  streaming: boolean
  local: boolean
}
const messageMap = ref<Map<number, ChatMessage>>(new Map())
const messages = computed(() => [...messageMap.value.values()].sort((a, b) => a.seq - b.seq))

// 议题输入（创建新演练，MVP 不做"选择已有演练"——已有在 /history）
const createForm = reactive({ topic: '', maxTurns: 8 })
const isCreating = ref(false)

const inputText = ref('')
const sending = ref(false)
const errorBanner = ref<string | null>(null)
const connectionBanner = ref<string | null>(null)

let sse: UseSseResult | null = null
const sseStatus = ref('idle')

const controlLoading = ref({ pause: false, resume: false, restart: false, quick: false })

onMounted(async () => {
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch (err) {
      if (isUnauthorized(err)) {
        goLogin()
        return
      }
      ElMessage.error(describeApiError(err))
      return
    }
  }
  const rawId = route.query.id
  if (!rawId) return // 无 id = 新建演练页（显示议题输入）
  const id = Number(rawId)
  if (!Number.isInteger(id) || id <= 0) {
    ElMessage.error('缺少会话 id')
    router.push('/teacher')
    return
  }
  sessionId.value = id
  loadError.value = null
  try {
    session.value = await getSession(id)
    await loadHistory(id)
    connectSse(id)
  } catch (err) {
    if (handleLoadError(err)) return
  }
})

async function loadHistory(id: number) {
  const res = await listMessages(id, 0, 200)
  for (const row of res.messages) {
    messageMap.value.set(row.seq, {
      seq: row.seq,
      role: row.role,
      agent_role: row.agent_role,
      content: row.content,
      status: row.status,
      streaming: row.status === 'streaming',
      local: false,
    })
  }
  messageMap.value = new Map(messageMap.value)
}

function upsert(seq: number, patch: Partial<ChatMessage> & Pick<ChatMessage, 'role'>) {
  const prev = messageMap.value.get(seq)
  const next: ChatMessage = {
    seq,
    role: patch.role,
    agent_role: patch.agent_role ?? prev?.agent_role ?? null,
    content: patch.content ?? prev?.content ?? '',
    status: patch.status ?? prev?.status ?? 'streaming',
    streaming: patch.streaming ?? prev?.streaming ?? false,
    local: patch.local ?? prev?.local ?? false,
  }
  messageMap.value.set(seq, next)
  messageMap.value = new Map(messageMap.value)
}

function maxSeq(): number {
  let max = 0
  for (const key of messageMap.value.keys()) if (key > max) max = key
  return max
}

function connectSse(id: number) {
  sse = useSSE(`/api/sessions/${id}/events`, {
    onOpen() { sseStatus.value = 'open'; connectionBanner.value = null },
    onStart(frame) {
      upsert(frame.seq, { role: 'assistant', agent_role: frame.agent_role, status: 'streaming', streaming: true })
      if (session.value && session.value.status === 'waiting') {
        session.value = { ...session.value, status: 'generating' }
      }
    },
    onDelta(frame) {
      const prev = messageMap.value.get(frame.seq)
      upsert(frame.seq, { role: 'assistant', content: (prev?.content ?? '') + frame.delta })
    },
    onEnd(frame) {
      const prev = messageMap.value.get(frame.seq)
      upsert(frame.seq, { role: 'assistant', status: frame.status, streaming: false, content: prev?.content ?? '' })
      if (session.value) {
        session.value = { ...session.value, status: frame.status === 'paused_truncated' ? 'paused' : 'waiting' }
      }
    },
    onSnapshot(frame) {
      upsert(frame.seq, {
        role: 'assistant', agent_role: frame.agent_role, content: frame.content,
        status: frame.status, streaming: frame.status === 'streaming',
      })
    },
    onError(frame) {
      errorBanner.value = `[${frame.code}] ${frame.message}${frame.retryable ? '（可重试）' : ''}`
    },
    onFatal() {
      errorBanner.value = '本轮生成失败（详见上方错误），连接已关闭。可重新发送引导再试。'
      if (session.value) session.value = { ...session.value, status: 'failed' }
    },
    onFinished() {
      if (session.value) session.value = { ...session.value, status: 'finished' }
    },
    onGiveUp() {
      sseStatus.value = 'given-up'
      connectionBanner.value = '连接已断开（多次重连失败）。点击「重新连接」手动恢复。'
    },
  }, { afterSeq: maxSeq() })
}

async function onSend() {
  const content = inputText.value.trim()
  if (!content) { ElMessage.warning('请输入引导内容'); return }
  sending.value = true
  errorBanner.value = null
  try {
    const res = await submitMessage(sessionId.value, content)
    messageMap.value.set(res.seq, {
      seq: res.seq, role: 'user', agent_role: null, content,
      status: 'complete', streaming: false, local: true,
    })
    messageMap.value = new Map(messageMap.value)
    inputText.value = ''
    if (session.value) session.value = { ...session.value, status: 'generating' }
  } catch (err) {
    if (isUnauthorized(err)) { goLogin(); return }
    errorBanner.value = describeApiError(err)
  } finally {
    sending.value = false
  }
}

async function onCreateDrill() {
  if (!createForm.topic.trim()) { ElMessage.warning('请填写演练议题'); return }
  isCreating.value = true
  try {
    const created = await createSession({
      topic: createForm.topic.trim(),
      mode: 'drill',
      max_turns: createForm.maxTurns,
      visibility: 'private',
      task_id: null,
    })
    ElMessage.success(`演练已创建（id=${created.id}，最多 ${createForm.maxTurns} 轮）`)
    router.push(`/teacher/drill?id=${created.id}`)
  } catch (err) {
    if (isUnauthorized(err)) { goLogin(); return }
    ElMessage.error(describeApiError(err))
  } finally {
    isCreating.value = false
  }
}

// 训练控制四按钮（pause/resume/restart/quick）——复用 TrainingView 的端点与状态机
async function onPause() {
  controlLoading.value.pause = true
  try { await pauseSession(sessionId.value) }
  catch (err) { if (isUnauthorized(err)) { goLogin(); return } errorBanner.value = describeApiError(err) }
  finally { controlLoading.value.pause = false }
}
async function onResume() {
  controlLoading.value.resume = true
  try { await resumeSession(sessionId.value) }
  catch (err) { if (isUnauthorized(err)) { goLogin(); return } errorBanner.value = describeApiError(err) }
  finally { controlLoading.value.resume = false }
}
async function onRestart() {
  controlLoading.value.restart = true
  try { await restartSession(sessionId.value) }
  catch (err) { if (isUnauthorized(err)) { goLogin(); return } errorBanner.value = describeApiError(err) }
  finally { controlLoading.value.restart = false }
}
async function onQuick() {
  controlLoading.value.quick = true
  try { await quickSession(sessionId.value) }
  catch (err) { if (isUnauthorized(err)) { goLogin(); return } errorBanner.value = describeApiError(err) }
  finally { controlLoading.value.quick = false }
}

// 控制按钮可用性（与 TrainingView 同款）
const canPause = computed(() => session.value?.status === 'generating')
const canResume = computed(() => session.value?.status === 'paused')
const canRestart = computed(() => session.value?.status !== 'generating')
const canQuick = computed(() => session.value?.status === 'generating')

function statusTagType(s: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  if (s === 'generating') return 'warning'
  if (s === 'paused') return 'info'
  if (s === 'finished') return 'success'
  if (s === 'failed') return 'danger'
  return 'info' // waiting
}
</script>

<template>
  <div class="page">
    <!-- 无会话 → 议题输入（创建新演练） -->
    <template v-if="!session && !loadError">
      <div class="hdr">
        <div>
          <h1>教学情境演练</h1>
          <span class="sub">AI 扮持正方立场的学生，教师练引导</span>
        </div>
        <el-button @click="router.push('/teacher')">← 返回教师工作区</el-button>
      </div>
      <ModelGatewayBanner />
      <el-card>
        <template #header>新建演练（POST /api/sessions，mode="drill"）</template>
        <el-form label-position="top" @submit.prevent="onCreateDrill">
          <el-form-item label="演练议题">
            <el-input v-model="createForm.topic" placeholder="如：AI 是否应当限制使用" />
          </el-form-item>
          <el-form-item label="最大轮次">
            <el-input-number v-model="createForm.maxTurns" :min="1" :max="50" />
            <span class="muted hint">本次演练最多 {{ createForm.maxTurns }} 轮</span>
          </el-form-item>
          <el-button type="primary" :loading="isCreating" @click="onCreateDrill">创建演练</el-button>
        </el-form>
      </el-card>
    </template>

    <!-- 加载/加载会话 -->
    <template v-else-if="loadError">
      <div class="hdr">
        <h1>教学情境演练</h1>
      </div>
      <el-card class="error-state">
        <el-result :icon="loadError === 'network' ? 'warning' : 'error'"
                   :title="errorTitle" :sub-title="errorDesc">
          <template #extra>
            <el-button @click="router.push('/teacher')">返回教师工作区</el-button>
            <el-button v-if="loadError === 'network'" type="primary" @click="loadError = null; session = null; router.go(0)">重试</el-button>
          </template>
        </el-result>
      </el-card>
    </template>

    <!-- 已有会话 → 演练界面 -->
    <template v-else-if="session">
      <div class="hdr">
        <div>
          <h1>情境演练（id={{ sessionId }}）</h1>
          <span class="sub">
            <b>议题</b> {{ session.topic }} ·
            <b>最多</b> {{ createForm.maxTurns }} 轮 ·
            <el-tag :type="statusTagType(session.status)" size="small">{{ session.status }}</el-tag>
          </span>
        </div>
        <el-button @click="router.push('/teacher')">← 返回教师工作区</el-button>
      </div>

      <ModelGatewayBanner />

      <el-alert v-if="errorBanner" :title="errorBanner" type="error" show-icon closable class="banner"
                @close="errorBanner = null" />
      <el-alert v-if="connectionBanner" :title="connectionBanner" type="warning" show-icon class="banner">
        <template #default>
          <el-button size="small" type="warning" @click="sse?.reconnect()">重新连接</el-button>
        </template>
      </el-alert>

      <el-card>
        <template #header>
          演练对话（AI 正方学生 · 教师引导）
          <span class="sse-status">连接：{{ sseStatus }}</span>
        </template>
        <MessageStream :messages="messages" mode="drill" />
        <p class="muted">
          教师消息本地渲染、不走 SSE 回显；AI 学生回应经 SSE 实时推送。
        </p>
      </el-card>

      <el-card>
        <template #header>教师输入（POST /api/sessions/{id}/messages）</template>
        <el-input v-model="inputText" type="textarea" :rows="4" :disabled="sending"
                  placeholder="输入引导或追问……" @keydown.enter.exact.prevent="onSend" />
        <el-button type="primary" :loading="sending" :disabled="sending" @click="onSend">发送</el-button>
      </el-card>

      <el-card>
        <template #header>演练控制</template>
        <div class="controls">
          <el-button :disabled="!canPause" :loading="controlLoading.pause" @click="onPause">暂停</el-button>
          <el-button :disabled="!canResume" :loading="controlLoading.resume" @click="onResume">续写</el-button>
          <el-button :disabled="!canRestart" :loading="controlLoading.restart" @click="onRestart">重开</el-button>
          <el-button :disabled="!canQuick" :loading="controlLoading.quick" @click="onQuick">加速</el-button>
        </div>
        <p class="muted">pause/quick 仅 generating；resume 仅 paused；restart 非 generating。</p>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1060px; margin: 0 auto; padding: 0 16px 48px; }
.hdr { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; margin: 20px 0 12px; }
.hdr h1 { font-size: 20px; margin: 0 0 4px; }
.sub { color: var(--el-text-color-secondary); font-size: 13px; }
.banner { margin-bottom: 12px; }
.sse-status { float: right; font-size: 12px; font-weight: normal; color: var(--el-text-color-secondary); }
.muted { color: var(--el-text-color-secondary); font-size: 12.5px; }
.hint { margin-left: 12px; }
.controls { display: flex; gap: 8px; flex-wrap: wrap; }
.error-state { margin-top: 16px; }
</style>
