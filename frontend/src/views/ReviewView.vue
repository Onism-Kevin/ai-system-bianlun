<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ModelGatewayBanner from '../components/ModelGatewayBanner.vue'
import RevisionCompare from '../components/RevisionCompare.vue'
import ReflectionForm from '../components/ReflectionForm.vue'
import ReportPanel from '../components/ReportPanel.vue'
import { getSession } from '../api/sessions'
import { describeApiError, isUnauthorized } from '../api/errors'
import type { SessionOut } from '../api/types'

// S2-F7 复盘页容器（S2-F7 两步均已完成：RevisionCompare + ReflectionForm + ReportPanel）。
// 布局顺序（设计 §1，输入→输出）：
//   ① 观点版本对比 → ② 个人反思 → ③ 报告区（ReportPanel） → ④ 提交按钮
// 反思在报告生成按钮上方，满足 S1-9b「报告生成前填写反思」。
const route = useRoute()
const router = useRouter()

const session = ref<SessionOut | null>(null)
const loading = ref(false)

onMounted(async () => {
  const rawId = route.query.id
  const id = Number(rawId)
  if (!rawId || !Number.isInteger(id) || id <= 0) {
    ElMessage.error('缺少会话 id')
    router.push('/dashboard')
    return
  }
  loading.value = true
  try {
    session.value = await getSession(id)
  } catch (err) {
    if (isUnauthorized(err)) {
      router.push('/login')
      return
    }
    ElMessage.error(describeApiError(err))
    router.push('/dashboard')
  } finally {
    loading.value = false
  }
})

function onUnauthorized() {
  router.push('/login')
}

// S3-4 未实现：提交按钮禁用 + 区分 private / task（D6 裁定 A）。
const submitHint = () => {
  if (!session.value) return ''
  return session.value.task_id === null
    ? '本会话未关联课程任务，无法提交'
    : '提交给课程任务（待 S3-4）'
}
</script>

<template>
  <div class="page">
    <div class="hdr">
      <div>
        <h1>复盘 · 观点修订与报告</h1>
        <span class="sub">S2-F7 复盘页（版本对比 / 反思 / 报告生成与渲染）</span>
      </div>
      <div class="hdr-actions">
        <el-button link type="primary" @click="router.push('/history')">← 历史</el-button>
        <el-button link type="primary" @click="router.push('/dashboard')">工作台</el-button>
      </div>
    </div>

    <ModelGatewayBanner />

    <div v-if="loading" class="loading">
      <el-skeleton :rows="6" animated />
    </div>

    <template v-else-if="session">
      <el-card class="session-card">
        <template #header>会话信息（GET /api/sessions/{id}，api.md:29）</template>
        <div class="kv">
          <span><b>会话</b> #{{ session.id }}</span>
          <span><b>议题</b> {{ session.topic }}</span>
          <span><b>visibility</b> {{ session.visibility }}</span>
          <span v-if="session.task_id !== null"><b>task_id</b> {{ session.task_id }}</span>
          <span>
            <b>状态</b>
            <el-tag size="small">{{ session.status }}</el-tag>
          </span>
        </div>
      </el-card>

      <RevisionCompare class="block" :session-id="session.id" @unauthorized="onUnauthorized" />

      <ReflectionForm class="block" :session-id="session.id" @unauthorized="onUnauthorized" />

      <!-- 报告区（ReportPanel：双渲染 + 502 错误 + 生成按钮） -->
      <ReportPanel class="block" :session-id="session.id" @unauthorized="onUnauthorized" />

      <el-card>
        <template #header>提交给课程任务</template>
        <el-button type="primary" disabled>
          {{ submitHint() }}
        </el-button>
        <p class="muted">
          submissions 端点属 S3-4（api.md:65，未实现）——按钮禁用 + 提示，不隐藏。
          本会话若未关联任务（task_id 为 null）则提示无法提交。
        </p>
      </el-card>
    </template>

    <div v-else class="loading">
      <el-empty description="加载中……" />
    </div>
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
.hdr-actions {
  display: flex;
  gap: 4px;
}
.session-card {
  margin-bottom: 12px;
}
.block {
  margin: 12px 0;
}
.loading {
  margin-top: 12px;
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
  margin: 8px 0 0;
}
</style>
