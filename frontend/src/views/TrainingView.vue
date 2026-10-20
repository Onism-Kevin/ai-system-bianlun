<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getSession, listMessages, submitMessage } from '../api/sessions'
import { describeApiError, isUnauthorized } from '../api/errors'
import { useSSE } from '../composables/useSSE'
import type { UseSseResult } from '../composables/useSSE'
import type { SessionOut } from '../api/types'

// S2-F5 训练页 SSE 客户端（设计：docs/design/s2_f5_sse_client_design.md）：
// - 消息流：GET messages 历史 + SSE /events 实时流（after_seq 消缝，sse §7.2）
// - 事件语义：start 创建块不清内容（§5.1）/ delta 追加（§5.2）/ end 定稿（§5.3）/
//   snapshot 整体替换（§5.4 断线补齐唯一基准）
// - 用户消息本地渲染，不走 SSE 回显（用户 2026-10-13 裁定，sse §4 补注）
// - 重连策略（退避/放弃/手动重连）在 useSSE.ts（sse §8）
// - 错误横幅：流内 error 帧（§5.7）+ REST 错误 + 连接放弃态
// - 训练控制四按钮：S2-F5 只做禁用态，点击全链路属 S2-F6
const route = useRoute()
const router = useRouter()

const session = ref<SessionOut | null>(null)
const sessionId = ref<number>(0)

// 本地消息表：Map<seq, ChatMessage> 按 seq upsert（sse §7.4 at-least-once 幂等）。
// Map 而非数组的理由：snapshot/回放/断线补齐都按 seq upsert，数组 splice 在
// 100+ 条消息时 O(n) 且易错位。
interface ChatMessage {
  seq: number
  role: 'user' | 'assistant' | 'system'
  agent_role: 'pro' | 'con' | 'judge' | 'coach' | null
  content: string
  status: 'streaming' | 'complete' | 'paused_truncated'
  /** 渲染辅助：是否显示「生成中」光标（speech_start 至 speech_end 之间）。 */
  streaming: boolean
  /** true=前端本地渲染的用户消息（发送即渲染，不走 SSE 回显）。 */
  local: boolean
}
const messageMap = ref<Map<number, ChatMessage>>(new Map())
const messages = computed(() => [...messageMap.value.values()].sort((a, b) => a.seq - b.seq))

// 输入与错误横幅
const inputText = ref('')
const sending = ref(false)
const errorBanner = ref<string | null>(null)
const connectionBanner = ref<string | null>(null)

let sse: UseSseResult | null = null

// 连接状态展示（useSSE.status 的镜像；模板直接读 sse.status 亦可，此 ref 供
// v-if 之外的徽标类场景复用，避免 let 变量在模板里的响应式盲区）。
const sseStatus = ref('idle')

onMounted(async () => {
  const rawId = route.query.id
  const id = Number(rawId)
  if (!rawId || !Number.isInteger(id) || id <= 0) {
    ElMessage.error('缺少会话 id')
    router.push('/dashboard')
    return
  }
  sessionId.value = id
  try {
    session.value = await getSession(id)
    await loadHistory(id)
    connectSse(id)
  } catch (err) {
    if (isUnauthorized(err)) {
      router.push('/login')
      return
    }
    ElMessage.error(describeApiError(err))
    router.push('/dashboard')
  }
})

// sse §7.2：先 REST 拉历史记 maxSeq，再 ?after_seq=maxSeq 建流，直接进实时态
// （裸连 after_seq=0 等价全量回放，但会先「逐字重放」历史，观感差）。
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
  // 触发 computed 更新（Map 原地 set 不触发响应式深比较）
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
  for (const key of messageMap.value.keys()) {
    if (key > max) max = key
  }
  return max
}

function connectSse(id: number) {
  sse = useSSE(`/api/sessions/${id}/events`, {
    onOpen() {
      sseStatus.value = 'open'
      connectionBanner.value = null
    },
    onStart(frame) {
      // §5.1：start 永不清本地内容。pause→resume 服务端重发同 seq start，
      // 已截断部分必须保留继续追加——只有空 content 才从零起。
      upsert(frame.seq, {
        role: 'assistant',
        agent_role: frame.agent_role,
        status: 'streaming',
        streaming: true,
      })
    },
    onDelta(frame) {
      // §5.2 增量追加
      const prev = messageMap.value.get(frame.seq)
      upsert(frame.seq, {
        role: 'assistant',
        content: (prev?.content ?? '') + frame.delta,
      })
    },
    onEnd(frame) {
      // §5.3：status∈complete/paused_truncated；paused 非终态、流不关
      const prev = messageMap.value.get(frame.seq)
      upsert(frame.seq, {
        role: 'assistant',
        status: frame.status,
        streaming: false,
        content: prev?.content ?? '',
      })
    },
    onSnapshot(frame) {
      // §5.4：content 整体替换（断线补齐唯一基准+幂等来源）
      upsert(frame.seq, {
        role: 'assistant',
        agent_role: frame.agent_role,
        content: frame.content,
        status: frame.status,
        streaming: frame.status === 'streaming',
      })
    },
    onError(frame) {
      // §5.7：只展示，不动消息表、不自动重试生成
      errorBanner.value = `[${frame.code}] ${frame.message}${frame.retryable ? '（可重试）' : ''}`
    },
    onFatal() {
      errorBanner.value = '本轮生成失败（详见上方错误），连接已关闭。可重新发送消息再试。'
    },
    onFinished() {
      // quick 轮尽路径服务端已落库 finished，本地同步徽章
      if (session.value) session.value = { ...session.value, status: 'finished' }
    },
    onGiveUp() {
      sseStatus.value = 'given-up'
      connectionBanner.value = '连接已断开（多次重连失败）。点击「重新连接」手动恢复。'
    },
  }, { afterSeq: maxSeq() })
}

function scrollToMessage(seq: number) {
  // 锚点跳转基础版（计划书:307 验收「点击引用→滚动至对应消息」）：
  // scroll-margin-top 补偿 sticky 头（见 <style>）。
  document.getElementById(`msg-${seq}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function onSend() {
  const content = inputText.value.trim()
  if (!content) {
    ElMessage.warning('请输入内容')
    return
  }
  sending.value = true
  errorBanner.value = null
  try {
    const res = await submitMessage(sessionId.value, content)
    // 本地渲染：不依赖 SSE 回显（sse §4 补注）。seq 以服务端 201 出参为准。
    messageMap.value.set(res.seq, {
      seq: res.seq,
      role: 'user',
      agent_role: null,
      content,
      status: 'complete',
      streaming: false,
      local: true,
    })
    messageMap.value = new Map(messageMap.value)
    inputText.value = ''
    // 乐观更新：messages 201 后服务端即转 generating（sessions.py BackgroundTasks）
    if (session.value) session.value = { ...session.value, status: 'generating' }
  } catch (err) {
    if (isUnauthorized(err)) {
      router.push('/login')
      return
    }
    // 409 非 waiting 等状态机错误：describeApiError 透传后端 detail（S2-F5 泛化）
    errorBanner.value = describeApiError(err)
  } finally {
    sending.value = false
  }
}

function statusTagType(status: string): 'success' | 'info' | 'warning' | 'danger' | 'primary' {
  if (status === 'generating') return 'warning'
  if (status === 'paused') return 'primary'
  if (status === 'finished') return 'success'
  if (status === 'failed') return 'danger'
  return 'info' // waiting
}

function roleLabel(m: ChatMessage): string {
  if (m.role === 'user') return '学生'
  if (m.agent_role === 'judge') return '裁判'
  if (m.agent_role === 'pro') return '正方'
  if (m.agent_role === 'con') return '反方'
  return 'AI 教练'
}

function agentTagType(m: ChatMessage): 'success' | 'info' | 'warning' | 'danger' | 'primary' {
  if (m.agent_role === 'pro') return 'success'
  if (m.agent_role === 'con') return 'danger'
  if (m.agent_role === 'judge') return 'primary'
  return 'info'
}

// 训练控制禁用态（docs/prototypes/training.html:164-167）：
// pause/quick 仅 generating；resume 仅 paused；restart 非 generating。
// 点击全链路属 S2-F6（控制端点 S2-6 已交付）。
const status = computed(() => session.value?.status ?? 'waiting')
const canPause = computed(() => status.value === 'generating')
const canQuick = computed(() => status.value === 'generating')
const canResume = computed(() => status.value === 'paused')
const canRestart = computed(() => status.value !== 'generating')
</script>

<template>
  <div class="page">
    <div class="hdr">
      <div>
        <h1>训练页 · 人机论证训练</h1>
        <span class="sub">SSE 实时消息流（sse_events.md §4-§8）</span>
      </div>
      <el-button link type="primary" @click="router.push('/dashboard')">← 工作台</el-button>
    </div>

    <!-- 错误横幅（S2-F5）：流内 error 帧（§5.7）+ REST 错误 -->
    <el-alert
      v-if="errorBanner"
      :title="errorBanner"
      type="error"
      show-icon
      closable
      class="banner"
      @close="errorBanner = null"
    />
    <!-- 连接放弃态（§8 累计 10 次）：手动重连入口 -->
    <el-alert
      v-if="connectionBanner"
      :title="connectionBanner"
      type="warning"
      show-icon
      class="banner"
    >
      <template #default>
        <el-button size="small" type="warning" @click="sse?.reconnect()">重新连接</el-button>
      </template>
    </el-alert>

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
      <template #header>
        辩论对话（GET messages 历史 + SSE /events 实时流）
        <span class="sse-status">连接：{{ sseStatus }}</span>
      </template>
      <div v-if="messages.length === 0" class="empty">
        <el-empty description="还没有消息。发送第一条观点，AI 将开始回应。" />
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
            <b>{{ roleLabel(m) }}</b>
            <el-tag v-if="m.agent_role" :type="agentTagType(m)" size="small">{{ m.agent_role }}</el-tag>
            <span>seq {{ m.seq }}</span>
            <span v-if="m.status === 'paused_truncated'" class="trunc">已截断</span>
            <span v-if="m.streaming" class="live">生成中…</span>
          </div>
          <div class="content">{{ m.content }}<span v-if="m.streaming" class="cursor" /></div>
        </div>
      </div>
      <p class="muted">
        用户消息本地渲染、不走 SSE 回显（sse_events.md §4 补注）；多标签页一致性由各标签页
        独立重连回放兜底（MVP 可接受）。
      </p>
    </el-card>

    <el-card>
      <template #header>消息输入（POST /api/sessions/{id}/messages，api.md:35）</template>
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="4"
        :disabled="sending"
        placeholder="输入你的观点或回应……"
        @keydown.enter.exact.prevent="onSend"
      />
      <el-button type="primary" :loading="sending" :disabled="sending" @click="onSend">发送</el-button>
      <p class="muted">
        201 {'{seq, created_at}'} → 本地渲染 → SSE 推送下一轮 AI 生成（BackgroundTasks 异步触发）。
      </p>
    </el-card>

    <el-card>
      <template #header>训练控制</template>
      <div class="controls">
        <!-- S2-F5 只做禁用态；pause 按钮暂挂锚点跳转演示（scrollToMessage(1)），
             S2-F6 替换为真控制调用。锚点跳转真实入口在 quote_refs 引用块（S2-9）。 -->
        <el-button :disabled="!canPause" @click="scrollToMessage(1)">暂停（pause）</el-button>
        <el-button :disabled="!canResume">续写（resume）</el-button>
        <el-button :disabled="!canRestart">重开（restart）</el-button>
        <el-button :disabled="!canQuick">加速（quick）</el-button>
      </div>
      <p class="muted">
        pause/quick 仅 generating；resume 仅 paused；restart 非 generating。
        控制端点 S2-6 已交付（pause/resume/restart/quick），按钮点击接入 S2-F6。
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
.banner {
  margin-bottom: 12px;
}
.sse-status {
  float: right;
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
}
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
  /* 锚点跳转补偿：scrollIntoView 后消息不被 sticky 元素遮挡（计划书:307 offset 断言 MVP 版） */
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
.controls {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
