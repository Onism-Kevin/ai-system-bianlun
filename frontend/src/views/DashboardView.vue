<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { createSession } from '../api/sessions'
import {
  demoError403,
  demoError410,
  fetchStudentCourses,
  joinCourse,
  joinTask,
} from '../api/dashboard'
import type { CourseItem } from '../api/dashboard'
import { listHistory } from '../api/history'
import type { HistoryItem } from '../api/types'
import { describeApiError, isUnauthorized } from '../api/errors'
import ModelGatewayBanner from '../components/ModelGatewayBanner.vue'

// S2-F3 dashboard（学生视角）：参考 S1-10 原型 docs/prototypes/dashboard.html。
// S3-F1 起 DashboardView 为**学生专用**：教师工作区拆到 TeacherDashboardView，
// 导航栏"工作台"按角色分流（教师 → /teacher）。
// - 历史列表：真实 GET /api/history（S2-12 已交付，#7 T-6 修复）；
// - 我的课程：真实 GET /api/courses（S3-2 已交付，studentCourses）；
// - 加入课程：真实 POST /api/courses/join（S3-2）；加入任务仍假数据（api/tasks.ts 属 S3-F1 commit C）；
// - 创建训练会话：真打 POST /api/sessions（S2-3 已交付），成功跳 /training?id=
// - 错误码演示：403/410 经真 AxiosError 构造，走同一条 describeApiError 路径
const auth = useAuthStore()
const router = useRouter()

const history = ref<HistoryItem[]>([])
const studentCourses = ref<CourseItem[]>([])

const joinCourseForm = reactive({ code: '' })
const joinTaskForm = reactive({ code: '', expired: false })
const createForm = reactive({ topic: '高校应不应该禁止 AI 代写论文', visibility: 'private', taskId: '' })

const loading = ref(false)

onMounted(async () => {
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch (err) {
      if (isUnauthorized(err)) {
        router.push('/login')
        return
      }
      ElMessage.error(describeApiError(err))
      return
    }
  }
  await loadFakeData()
})

async function loadFakeData() {
  // 历史列表接真实 GET /api/history（S2-12 已交付，T-6 修复）；
  // 我的课程接真实 GET /api/courses（S3-2 已交付）。
  history.value = await listHistory()
  if (auth.roles.includes('student')) studentCourses.value = await fetchStudentCourses()
}

function onHistoryRowClick(row: HistoryItem) {
  router.push(`/training?id=${row.id}`)
}

async function withLoading(action: () => Promise<void>) {
  loading.value = true
  try {
    await action()
  } catch (err) {
    ElMessage.error(describeApiError(err))
  } finally {
    loading.value = false
  }
}

function onJoinCourse() {
  withLoading(async () => {
    const res = await joinCourse(joinCourseForm.code)
    ElMessage.success(`已加入课程（course_id=${res.course_id}）`)
  })
}

function onJoinTask() {
  withLoading(async () => {
    const res = await joinTask(joinTaskForm.code, joinTaskForm.expired)
    ElMessage.success(`已加入任务（task_id=${res.task_id}）`)
  })
}

function onCreateSession() {
  if (!createForm.topic.trim()) {
    ElMessage.warning('请填写议题（topic）')
    return
  }
  if (createForm.visibility === 'task' && !createForm.taskId.trim()) {
    ElMessage.warning('visibility=task 时必须填写 task_id（E-2）')
    return
  }
  withLoading(async () => {
    const res = await createSession({
      topic: createForm.topic.trim(),
      visibility: createForm.visibility as 'private' | 'task',
      task_id: createForm.visibility === 'task' ? Number(createForm.taskId) : null,
    })
    ElMessage.success(`会话已创建（id=${res.id}，status=${res.status}）`)
    router.push(`/training?id=${res.id}`)
  })
}

function onDemo403() {
  withLoading(async () => {
    await demoError403()
  })
}

function onDemo410() {
  withLoading(async () => {
    await demoError410()
  })
}

function roleTagType(role: string): 'primary' | 'warning' | 'info' {
  return role === 'teacher' ? 'warning' : 'primary'
}
</script>

<template>
  <div class="page">
    <div class="hdr">
      <div>
        <h1>首页工作台</h1>
        <span class="sub">
          <el-tag
            v-for="role in auth.roles"
            :key="role"
            :type="roleTagType(role)"
            size="small"
            class="role-tag"
          >{{ role === 'teacher' ? '教师' : role === 'student' ? '学生' : role }}</el-tag>
          <span v-if="auth.user">{{ auth.user.display_name || auth.user.username }}</span>
        </span>
      </div>
    </div>

    <!-- S2-F9：全局健康横幅 + health 徽标 -->
    <ModelGatewayBanner />

    <!-- 学生视角（DashboardView 自 S3-F1 起为学生专用） -->
    <template v-if="auth.roles.includes('student')">
      <div class="grid">
        <el-card>
          <template #header>
            我的训练（真实 · GET /api/history）
            <el-button link type="primary" size="small" @click="router.push('/history')">
              查看全部历史 →
            </el-button>
          </template>
          <el-table :data="history" style="width: 100%" @row-click="onHistoryRowClick">
            <el-table-column prop="id" label="id" width="70" />
            <el-table-column prop="topic" label="议题" />
            <el-table-column prop="status" label="状态" width="110" />
            <el-table-column prop="updated_at" label="更新时间" width="170" />
          </el-table>
          <p class="muted">
            点击行进入训练页（继续这个会话）；表头「查看全部历史」看所有历史（S2-F8）。
          </p>
        </el-card>

        <el-card>
          <template #header>加入课程（假数据 · POST /api/courses/join 属 S3-2）</template>
          <el-input v-model="joinCourseForm.code" placeholder="invite_code（正确码 DEMO01）" />
          <el-button type="primary" :loading="loading" @click="onJoinCourse">加入</el-button>
          <p class="muted">错码 → 403（E-12 对称化，detail「加入码无效」）；正确码 → 幂等 200。</p>
        </el-card>

        <el-card>
          <template #header>加入任务（假数据 · POST /api/tasks/{id}/join 属 S3-3）</template>
          <el-input v-model="joinTaskForm.code" placeholder="join_code（正确码 XK7M2QP）" />
          <el-checkbox v-model="joinTaskForm.expired">演示已过期（410）</el-checkbox>
          <el-button type="primary" :loading="loading" @click="onJoinTask">加入</el-button>
          <p class="muted">错码 → 403（E-12）；勾选过期 → 410 已过 deadline（api.md:64）。</p>
        </el-card>

        <el-card>
          <template #header>创建训练会话（真实 · POST /api/sessions，S2-3）</template>
          <el-input v-model="createForm.topic" placeholder="议题 topic" />
          <el-radio-group v-model="createForm.visibility" size="small">
            <el-radio-button value="private">private</el-radio-button>
            <el-radio-button value="task">task</el-radio-button>
          </el-radio-group>
          <el-input
            v-if="createForm.visibility === 'task'"
            v-model="createForm.taskId"
            placeholder="task_id（visibility=task 时必填，E-2）"
          />
          <el-button type="primary" :loading="loading" @click="onCreateSession">创建并进入训练</el-button>
          <p class="muted">201 {id, status:"waiting"} → 跳 /training?id=（api.md:28 + 脚注 3）。</p>
        </el-card>

        <el-card>
          <template #header>我的课程（真实 · GET /api/courses 学生视角）</template>
          <el-table :data="studentCourses" style="width: 100%">
            <el-table-column prop="id" label="id" width="70" />
            <el-table-column prop="name" label="课程" />
            <el-table-column prop="term" label="学期" width="110" />
          </el-table>
        </el-card>
      </div>
    </template>

    <!-- 教师视角已拆出：见 TeacherDashboardView（/teacher）；导航栏"工作台"按角色分流 -->

    <!-- 错误码演示（学生工作台） -->
    <el-card class="error-demo">
      <template #header>错误码演示（假数据 · 经真 AxiosError 走同一条 describeApiError 路径）</template>
      <el-button :loading="loading" @click="onDemo403">触发 403（加入码错误）</el-button>
      <el-button :loading="loading" @click="onDemo410">触发 410（任务已过期）</el-button>
      <p class="muted">
        映射：403 → 透传 detail「加入码无效」（E-12）；410 → 「任务已过截止时间，无法加入」（api.md:64）。
        与真实后端错误同路径——不是演示专用分支。
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
.role-tag {
  margin-right: 4px;
}
.view-switch {
  display: flex;
  align-items: center;
  gap: 8px;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media (max-width: 860px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
.error-demo {
  margin-top: 14px;
}
</style>
