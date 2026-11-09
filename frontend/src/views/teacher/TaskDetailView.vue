<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { AxiosError } from 'axios'
import { useAuthStore } from '../../stores/auth'
import { getTask } from '../../api/tasks'
import { listSubmissions, getMySubmission } from '../../api/submissions'
import type { SubmissionListItem, TaskOut } from '../../api/types'
import { describeApiError, isUnauthorized } from '../../api/errors'
import ModelGatewayBanner from '../../components/ModelGatewayBanner.vue'
import { useLoadError } from '../../composables/useLoadError'
import { formatDeadline } from '../../utils/format'

// S3-F3：任务详情（提交查看）。
// 数据源：GET /api/tasks/:id + GET /api/tasks/:id/submissions（教师）/
//         GET /api/tasks/:id/submissions/me（学生自己的提交）。
// 后端已按权限过滤：教师列表仅已提交行；学生 me 仅本人。前端不重复判权。
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const courseId = Number(route.params.id)
const taskId = Number(route.params.tid)
const task = ref<TaskOut | null>(null)
const submissions = ref<SubmissionListItem[]>([])
// 学生未提交（me 端点 404）→ 专属空状态，不用 loadError（那是"不可读"）。
const notSubmitted = ref(false)

const { loadError, goLogin, handleLoadError, errorTitle, errorDesc } = useLoadError({
  forbiddenTitle: '无权访问该任务',
  forbiddenDesc: '你不是该任务所属课程的教师',
  notFoundTitle: '任务不存在',
  notFoundDesc: '任务不存在或已删除',
})

const isTeacher = computed(() => auth.roles.includes('teacher'))

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
  await loadData()
})

async function loadData() {
  loadError.value = null
  notSubmitted.value = false
  submissions.value = []
  try {
    // 先取任务：不可读 → 404；非课程教师 → 403（但 getTask 学生成员可读）
    try {
      task.value = await getTask(taskId)
    } catch (err) {
      if (handleLoadError(err)) return
    }
    await loadSubmissions()
  } catch (err) {
    handleLoadError(err)
  }
}

/**
 * 取提交：
 * - 教师 → listSubmissions（全部已提交行；非课程教师 403 → forbidden）
 * - 学生 → getMySubmission（仅本人；未提交 404 → 专属空状态）
 */
async function loadSubmissions() {
  if (isTeacher.value) {
    try {
      submissions.value = await listSubmissions(taskId)
    } catch (err) {
      handleLoadError(err)
    }
    return
  }
  try {
    const mine = await getMySubmission(taskId)
    submissions.value = [
      {
        student_id: mine.student_id,
        session_id: mine.session_id,
        submitted_at: mine.submitted_at,
      },
    ]
  } catch (err) {
    if (err instanceof AxiosError && err.response?.status === 404) {
      // 学生本人未提交 → 空状态（不是"任务不存在"）
      notSubmitted.value = true
      return
    }
    handleLoadError(err)
  }
}

function openSession(sessionId: number) {
  // 学生从"提交记录"点进去 → 复盘页（看自己的报告）；教师 → 训练页（继续/管理）
  router.push(isTeacher.value ? `/training?id=${sessionId}` : `/review?id=${sessionId}`)
}

function formatSubmittedAt(d: string): string {
  return d.replace('T', ' ').slice(0, 19)
}
</script>

<template>
  <div class="page">
    <div class="hdr">
      <div>
        <h1>{{ task ? task.title : '任务' }}（id={{ taskId }}）</h1>
        <span class="sub">
          <template v-if="loadError">{{ errorTitle }}</template>
          <template v-else-if="task">
            截止 {{ formatDeadline(task.deadline) }} ·
            <el-tag size="small" :type="task.is_archived ? 'info' : 'success'" effect="plain">
              {{ task.is_archived ? '已归档' : '活跃' }}
            </el-tag>
          </template>
          <template v-else>加载中…</template>
        </span>
      </div>
      <el-button @click="router.push('/teacher/courses/' + courseId)">← 返回课程</el-button>
    </div>

    <ModelGatewayBanner />

    <!-- S3-F2 commit C / S3-F3：错误空状态（复用 useLoadError 模式） -->
    <el-card v-if="loadError" class="error-state">
      <el-result
        :icon="loadError === 'network' ? 'warning' : 'error'"
        :title="errorTitle"
        :sub-title="errorDesc"
      >
        <template #extra>
          <el-button @click="router.push('/teacher')">返回课程列表</el-button>
          <el-button v-if="loadError === 'network'" type="primary" @click="loadData">重试</el-button>
        </template>
      </el-result>
    </el-card>

    <template v-else>
      <!-- 任务基本信息 -->
      <el-card class="task-card">
        <template #header>任务信息</template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="标题">{{ task?.title ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="截止时间">
            {{ formatDeadline(task?.deadline ?? null) }}
          </el-descriptions-item>
          <el-descriptions-item label="加入码" :span="2">
            <span v-if="task?.join_code" class="join-code">{{ task.join_code }}</span>
            <span v-else class="muted">无需加入码</span>
          </el-descriptions-item>
          <el-descriptions-item label="材料" :span="2">
            <pre v-if="task?.material" class="material">{{ task.material }}</pre>
            <span v-else class="muted">无</span>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 提交列表 -->
      <el-card class="submissions-card">
        <template #header>
          提交列表
          <el-button link type="primary" size="small" @click="loadData">刷新</el-button>
        </template>

        <!-- 教师：无提交 → 空状态 -->
        <el-empty
          v-if="isTeacher && submissions.length === 0 && !notSubmitted"
          description="暂无学生提交"
        />

        <!-- 学生：未提交 → 专属空状态 -->
        <el-empty v-else-if="!isTeacher && notSubmitted" description="你还没有提交该任务" />

        <el-table v-else :data="submissions" style="width: 100%">
          <el-table-column prop="student_id" label="学生 id" width="110" />
          <el-table-column label="提交时间" width="180">
            <template #default="{ row }">{{ formatSubmittedAt(row.submitted_at) }}</template>
          </el-table-column>
          <el-table-column label="会话" width="200">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openSession(row.session_id)">
                查看会话
              </el-button>
              <span class="muted">#{{ row.session_id }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 16px 48px;
}
.hdr {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
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
.task-card,
.submissions-card {
  margin-bottom: 16px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
.join-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 14px;
  letter-spacing: 0.5px;
  color: var(--el-text-color-primary);
}
.material {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
}
.error-state {
  margin-top: 16px;
}
</style>
