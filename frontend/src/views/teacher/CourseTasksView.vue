<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { getCourse } from '../../api/courses'
import { listCourseTasks, createTask } from '../../api/tasks'
import type { CourseOut, TaskOut } from '../../api/types'
import { describeApiError, isUnauthorized } from '../../api/errors'
import ModelGatewayBanner from '../../components/ModelGatewayBanner.vue'

// S3-F1 commit C：课程详情 + 任务列表。
// 数据源：GET /api/courses/:id + GET /api/courses/:id/tasks + POST /api/courses/:id/tasks。
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const courseId = Number(route.params.id)
const course = ref<CourseOut | null>(null)
const tasks = ref<TaskOut[]>([])
const loading = ref(false)
const createForm = reactive({ title: '', material: '', deadline: '', needJoinCode: false })

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
  await loadData()
})

async function loadData() {
  loading.value = true
  try {
    const [c, t] = await Promise.all([getCourse(courseId), listCourseTasks(courseId)])
    course.value = c
    tasks.value = t
  } catch (err) {
    if (isUnauthorized(err)) {
      router.push('/login')
      return
    }
    ElMessage.error(describeApiError(err))
  } finally {
    loading.value = false
  }
}

async function onCreateTask() {
  if (!createForm.title.trim()) {
    ElMessage.warning('请填写任务标题')
    return
  }
  loading.value = true
  try {
    const created = await createTask(courseId, {
      title: createForm.title.trim(),
      material: createForm.material.trim() || null,
      deadline: createForm.deadline ? new Date(createForm.deadline).toISOString() : null,
      need_join_code: createForm.needJoinCode,
    })
    ElMessage.success(`任务已创建（id=${created.id}，join_code=${created.join_code ?? '—'}）`)
    createForm.title = ''
    createForm.material = ''
    createForm.deadline = ''
    createForm.needJoinCode = false
    await loadData()
  } catch (err) {
    if (isUnauthorized(err)) {
      router.push('/login')
      return
    }
    ElMessage.error(describeApiError(err))
  } finally {
    loading.value = false
  }
}

function openTask(task: TaskOut) {
  router.push(`/teacher/courses/${courseId}/tasks/${task.id}`)
}

function formatDeadline(d: string | null): string {
  if (!d) return '—'
  return d.replace('T', ' ').slice(0, 16)
}
</script>

<template>
  <div class="page">
    <div class="hdr">
      <div>
        <h1>{{ course ? course.name : '课程' }}（id={{ courseId }}）</h1>
        <span class="sub">
          <template v-if="course">
            学期 {{ course.term || '—' }} ·
            <el-tag size="small" :type="course.is_archived ? 'info' : 'success'" effect="plain">
              {{ course.is_archived ? '已归档' : '活跃' }}
            </el-tag>
          </template>
          <template v-else>加载中…</template>
        </span>
      </div>
      <el-button @click="router.push('/teacher')">← 返回教师工作区</el-button>
    </div>

    <ModelGatewayBanner />

    <div class="grid">
      <el-card>
        <template #header>
          任务列表
          <el-button link type="primary" size="small" :loading="loading" @click="loadData">
            刷新
          </el-button>
        </template>
        <el-table :data="tasks" style="width: 100%">
          <el-table-column prop="id" label="id" width="70" />
          <el-table-column prop="title" label="任务" />
          <el-table-column label="截止" width="150">
            <template #default="{ row }">{{ formatDeadline(row.deadline) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_archived ? 'info' : 'success'" effect="plain">
                {{ row.is_archived ? '已归档' : '活跃' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openTask(row)">查看提交</el-button>
            </template>
          </el-table-column>
        </el-table>
        <p v-if="tasks.length === 0" class="muted">暂无任务。用右侧表单创建第一个任务。</p>
      </el-card>

      <el-card>
        <template #header>新建任务（POST /api/courses/:id/tasks）</template>
        <el-form label-position="top" @submit.prevent="onCreateTask">
          <el-form-item label="任务标题">
            <el-input v-model="createForm.title" placeholder="如：AI 伦理辩论" />
          </el-form-item>
          <el-form-item label="材料（可选）">
            <el-input v-model="createForm.material" type="textarea" :rows="3" placeholder="任务材料" />
          </el-form-item>
          <el-form-item label="截止时间（可选）">
            <el-date-picker
              v-model="createForm.deadline"
              type="datetime"
              placeholder="选择截止时间"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="需要加入码">
            <el-switch v-model="createForm.needJoinCode" />
          </el-form-item>
          <el-button type="primary" :loading="loading" @click="onCreateTask">创建任务</el-button>
        </el-form>
        <p class="muted">
          201 {id, title, join_code}；need_join_code=true 时服务端生成加入码（api.md:60）。
        </p>
      </el-card>
    </div>
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
.grid {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 16px;
  align-items: start;
}
@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
</style>
