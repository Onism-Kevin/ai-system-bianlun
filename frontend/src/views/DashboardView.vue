<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { createSession } from '../api/sessions'
import {
  demoError403,
  demoError410,
  fetchHistory,
  fetchStudentCourses,
  fetchTeacherCourses,
  joinCourse,
  joinTask,
} from '../api/dashboard'
import type { CourseItem, SessionHistoryItem } from '../api/dashboard'
import { describeApiError, isUnauthorized } from '../api/errors'

// S2-F3 dashboard：参考 S1-10 原型 docs/prototypes/dashboard.html。
// - 双角色徽标 + 双角色视角切换（roles 来自 /auth/me，真实数据）
// - 历史列表 / 加入课程 / 加入任务：假数据走通（端点属 S2-12/S3，api/dashboard.ts）
// - 创建训练会话：真打 POST /api/sessions（S2-3 已交付），成功跳 /training?id=
// - 错误码演示：403/410 经真 AxiosError 构造，走同一条 describeApiError 路径
const auth = useAuthStore()
const router = useRouter()

const history = ref<SessionHistoryItem[]>([])
const studentCourses = ref<CourseItem[]>([])
const teacherCourses = ref<CourseItem[]>([])
// 双角色视角：仅双角色用户显示切换器；单角色默认自身视角
const activeView = ref<'student' | 'teacher'>('student')

const joinCourseForm = reactive({ code: '' })
const joinTaskForm = reactive({ code: '', expired: false })
const createForm = reactive({ topic: '高校应不应该禁止 AI 代写论文', visibility: 'private', taskId: '' })

const loading = ref(false)

onMounted(async () => {
  if (auth.user) {
    syncView()
    await loadFakeData()
    return
  }
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
  syncView()
  await loadFakeData()
})

function syncView() {
  const roles = auth.roles
  activeView.value = roles.includes('teacher') && !roles.includes('student') ? 'teacher' : 'student'
}

const isDualRole = () => auth.roles.includes('student') && auth.roles.includes('teacher')

async function loadFakeData() {
  history.value = await fetchHistory()
  if (auth.roles.includes('student')) studentCourses.value = await fetchStudentCourses()
  if (auth.roles.includes('teacher')) teacherCourses.value = await fetchTeacherCourses()
}

function onHistoryRowClick(row: SessionHistoryItem) {
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
      <div v-if="isDualRole()" class="view-switch">
        <span class="muted">视角：</span>
        <el-radio-group v-model="activeView" size="small">
          <el-radio-button value="student">学生</el-radio-button>
          <el-radio-button value="teacher">教师</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 学生视角 -->
    <template v-if="activeView === 'student' && auth.roles.includes('student')">
      <div class="grid">
        <el-card>
          <template #header>我的训练（假数据 · GET /api/history 属 S2-12）</template>
          <el-table :data="history" style="width: 100%" @row-click="onHistoryRowClick">
            <el-table-column prop="id" label="id" width="70" />
            <el-table-column prop="topic" label="议题" />
            <el-table-column prop="status" label="状态" width="110" />
            <el-table-column prop="updated_at" label="更新时间" width="170" />
          </el-table>
          <p class="muted">点击行进入训练页（S2-F4 起补真实消息流）。</p>
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
          <template #header>我的课程（假数据 · 学生视角，GET /api/courses 属 S3-2）</template>
          <el-table :data="studentCourses" style="width: 100%">
            <el-table-column prop="id" label="id" width="70" />
            <el-table-column prop="name" label="课程" />
            <el-table-column prop="term" label="学期" width="110" />
          </el-table>
        </el-card>
      </div>
    </template>

    <!-- 教师视角 -->
    <template v-if="activeView === 'teacher' && auth.roles.includes('teacher')">
      <div class="grid">
        <el-card>
          <template #header>我的课程（假数据 · 教师视角，GET /api/courses 属 S3-2）</template>
          <el-table :data="teacherCourses" style="width: 100%">
            <el-table-column prop="id" label="id" width="70" />
            <el-table-column prop="name" label="课程" />
            <el-table-column prop="invite_code" label="invite_code" width="130" />
          </el-table>
          <p class="muted">invite_code 仅教师响应保留（api.md:56）。</p>
        </el-card>

        <el-card>
          <template #header>创建课程（假数据 · POST /api/courses 属 S3-2）</template>
          <el-input placeholder="课程名（S3-2 端点落地后接真调用）" />
          <el-button disabled>创建课程</el-button>
          <p class="muted">201 {id, name, invite_code, …}；invite_code 服务端生成。</p>
        </el-card>

        <el-card>
          <template #header>快捷入口</template>
          <p class="muted">任务管理 / 班级汇总属 S3（教师任务页 S3-F3）。</p>
        </el-card>
      </div>
    </template>

    <!-- 错误码演示（两个角色都可见） -->
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
