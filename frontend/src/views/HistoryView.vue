<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getHistoryDetail, listHistory } from '../api/history'
import { describeApiError, isUnauthorized } from '../api/errors'
import type { HistoryDetailOut, HistoryItem, MessageOut } from '../api/types'

// S2-F8 历史页（S2-12 端点，api.md:40-41）：
// - 列表：GET /api/history → [{id, topic, status, created_at, updated_at}]，后端
//   已按 updated_at DESC 排序，前端原样展示；
// - 详情：点击行 → GET /api/history/{id} → {session, messages:[按 seq 升序]}，
//   完整重建消息流（含 streaming 在途消息，用 badge 标注「生成中」）；
// - 列表是 owner 视角（后端只返回 owner_id=本人的会话），越权一律 404 存在性隐藏。
// - 复盘入口：每行「复盘」按钮 → /review?id=X（S2-F7 补齐）。
const router = useRouter()

const items = ref<HistoryItem[]>([])
const loading = ref(false)
const detail = ref<HistoryDetailOut | null>(null)
const detailLoading = ref(false)
const errorBanner = ref<string | null>(null)

onMounted(loadList)

async function loadList() {
  loading.value = true
  errorBanner.value = null
  try {
    items.value = await listHistory()
  } catch (err) {
    if (isUnauthorized(err)) {
      router.push('/login')
      return
    }
    // 404 等越权在列表端不出现（owner 视角）；网络/5xx 走通用文案
    errorBanner.value = describeApiError(err)
  } finally {
    loading.value = false
  }
}

async function onRowClick(row: HistoryItem) {
  errorBanner.value = null
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await getHistoryDetail(row.id)
  } catch (err) {
    if (isUnauthorized(err)) {
      router.push('/login')
      return
    }
    errorBanner.value = describeApiError(err)
  } finally {
    detailLoading.value = false
  }
}

// S2-F7 复盘入口：历史页每行「复盘」链接 → /review?id=X（"过几天回来看复盘"路径）。
function goReview(row: HistoryItem) {
  router.push('/review?id=' + row.id)
}

function statusTagType(
  status: string,
): 'success' | 'info' | 'warning' | 'danger' | 'primary' {
  if (status === 'generating') return 'warning'
  if (status === 'paused') return 'primary'
  if (status === 'finished') return 'success'
  if (status === 'failed') return 'danger'
  return 'info' // waiting
}

function roleLabel(m: MessageOut): string {
  if (m.role === 'user') return '学生'
  if (m.agent_role === 'judge') return '裁判'
  if (m.agent_role === 'pro') return '正方'
  if (m.agent_role === 'con') return '反方'
  return 'AI 教练'
}

function agentTagType(
  role: string | null,
): 'success' | 'info' | 'warning' | 'danger' | 'primary' {
  if (role === 'pro') return 'success'
  if (role === 'con') return 'danger'
  if (role === 'judge') return 'primary'
  return 'info'
}
</script>

<template>
  <div class="page">
    <div class="hdr">
      <div>
        <h1>训练历史</h1>
        <span class="sub">GET /api/history 列表 + GET /api/history/{id} 详情回放（api.md:40-41）</span>
      </div>
      <el-button link type="primary" @click="router.push('/dashboard')">← 工作台</el-button>
    </div>

    <!-- 错误横幅：REST 错误（网络/5xx；列表 owner 视角不出现 404） -->
    <el-alert
      v-if="errorBanner"
      :title="errorBanner"
      type="error"
      show-icon
      closable
      class="banner"
      @close="errorBanner = null"
    />

    <el-card>
      <template #header>
        会话列表（owner 视角 · 按 updated_at DESC）
        <span class="count">共 {{ items.length }} 条</span>
      </template>
      <el-table
        v-loading="loading"
        :data="items"
        style="width: 100%"
        row-key="id"
        @row-click="onRowClick"
      >
        <el-table-column prop="id" label="id" width="70" />
        <el-table-column prop="topic" label="议题" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column prop="updated_at" label="更新时间" width="180" />
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <!-- @click.stop：不触发行点击（行点击是展开详情） -->
            <el-button link type="success" size="small" @click.stop="goReview(row)">
              复盘
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="muted">
        点击行加载详情（消息按 seq 升序完整重建，含在途 streaming 消息）；点「复盘」进入报告页。
      </p>
    </el-card>

    <el-card v-if="detailLoading" class="detail">
      <el-skeleton :rows="6" animated />
    </el-card>

    <el-card v-else-if="detail" class="detail">
      <template #header>
        会话详情 #{{ detail.session.id }}（GET /api/history/{id}）
        <span class="sse-status">消息 {{ detail.messages.length }} 条</span>
      </template>

      <div class="kv">
        <span><b>议题</b> {{ detail.session.topic }}</span>
        <span><b>visibility</b> {{ detail.session.visibility }}</span>
        <span v-if="detail.session.task_id !== null"><b>task_id</b> {{ detail.session.task_id }}</span>
        <span>
          <b>状态</b>
          <el-tag :type="statusTagType(detail.session.status)" size="small">
            {{ detail.session.status }}
          </el-tag>
        </span>
        <span><b>创建</b> {{ detail.session.created_at }}</span>
        <span><b>更新</b> {{ detail.session.updated_at }}</span>
      </div>

      <div v-if="detail.messages.length === 0" class="empty">
        <el-empty description="该会话暂无消息。" />
      </div>
      <div v-else class="msgs">
        <div
          v-for="m in detail.messages"
          :id="'hmsg-' + m.seq"
          :key="m.seq"
          class="msg"
          :class="[m.role === 'user' ? 'is-user' : 'is-ai', m.agent_role ? 'role-' + m.agent_role : '']"
        >
          <div class="head">
            <b>{{ roleLabel(m) }}</b>
            <el-tag v-if="m.agent_role" :type="agentTagType(m.agent_role)" size="small">
              {{ m.agent_role }}
            </el-tag>
            <span>seq {{ m.seq }}</span>
            <span v-if="m.status === 'streaming'" class="live">
              <el-tag type="warning" size="small" effect="dark">生成中</el-tag>
            </span>
            <span v-else-if="m.status === 'paused_truncated'" class="trunc">已截断</span>
          </div>
          <div class="content">{{ m.content }}</div>
        </div>
      </div>
      <p class="muted">
        历史详情完整重建消息流（含 streaming 在途消息）；会话级 status 五态与消息级
        status 三态字段名相同但枚举不同（schema history.py 注记）。
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
.banner {
  margin-bottom: 12px;
}
.detail {
  margin-top: 12px;
}
.count,
.sse-status {
  float: right;
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
}
.kv {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 13px;
  margin-bottom: 12px;
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
</style>
