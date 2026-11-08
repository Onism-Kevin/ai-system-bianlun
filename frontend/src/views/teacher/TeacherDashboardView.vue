<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { listCourses, createCourse } from '../../api/courses'
import type { CourseOut } from '../../api/types'
import { describeApiError, isUnauthorized } from '../../api/errors'
import ModelGatewayBanner from '../../components/ModelGatewayBanner.vue'

// S3-F1 commit B：教师工作区（我的课程 + 建课 + 快捷入口）。
// 数据源：GET /api/courses（教师视角 = teacher_id=本人）+ POST /api/courses。
const auth = useAuthStore()
const router = useRouter()

const courses = ref<CourseOut[]>([])
const loading = ref(false)
const createForm = reactive({ name: '', description: '', term: '' })

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
  await loadCourses()
})

async function loadCourses() {
  loading.value = true
  try {
    courses.value = await listCourses()
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

async function onCreateCourse() {
  if (!createForm.name.trim()) {
    ElMessage.warning('请填写课程名')
    return
  }
  loading.value = true
  try {
    const created = await createCourse({
      name: createForm.name.trim(),
      description: createForm.description.trim() || null,
      term: createForm.term.trim() || null,
    })
    ElMessage.success(`课程已创建（id=${created.id}，invite_code=${created.invite_code ?? '—'}）`)
    createForm.name = ''
    createForm.description = ''
    createForm.term = ''
    await loadCourses()
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

function openCourse(course: CourseOut) {
  router.push(`/teacher/courses/${course.id}`)
}
</script>

<template>
  <div class="page">
    <div class="hdr">
      <h1>教师工作区</h1>
      <span class="sub">我的课程 + 建课 + 快捷入口（S3-F1）</span>
    </div>

    <ModelGatewayBanner />

    <div class="grid">
      <el-card>
        <template #header>
          我的课程
          <el-button link type="primary" size="small" :loading="loading" @click="loadCourses">
            刷新
          </el-button>
        </template>
        <el-table :data="courses" style="width: 100%">
          <el-table-column prop="id" label="id" width="70" />
          <el-table-column prop="name" label="课程" />
          <el-table-column prop="term" label="学期" width="110" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_archived ? 'info' : 'success'" effect="plain">
                {{ row.is_archived ? '已归档' : '活跃' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openCourse(row)">
                查看任务
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <p v-if="courses.length === 0" class="muted">
          暂无课程。用右侧表单创建第一门课。
        </p>
      </el-card>

      <div class="side">
        <el-card>
          <template #header>新建课程（POST /api/courses）</template>
          <el-form label-position="top" @submit.prevent="onCreateCourse">
            <el-form-item label="课程名">
              <el-input v-model="createForm.name" placeholder="如：2026 秋·论证与探究" />
            </el-form-item>
            <el-form-item label="学期（可选）">
              <el-input v-model="createForm.term" placeholder="如：2026-秋" />
            </el-form-item>
            <el-form-item label="简介（可选）">
              <el-input
                v-model="createForm.description"
                type="textarea"
                :rows="3"
                placeholder="课程简介"
              />
            </el-form-item>
            <el-button type="primary" :loading="loading" @click="onCreateCourse">创建课程</el-button>
          </el-form>
          <p class="muted">
            201 {id, name, invite_code}；invite_code 服务端生成（api.md:54）。
          </p>
        </el-card>

        <el-card>
          <template #header>快捷入口</template>
          <el-button @click="router.push('/teacher/courses/0')">建任务（选课程后）</el-button>
          <el-button @click="router.push('/teacher/courses/0')">查看汇总（S3-F3 实现）</el-button>
          <el-button @click="router.push('/dashboard')">学生工作台</el-button>
          <p class="muted">
            任务管理/班级汇总在课程详情页；提交查看页属 S3-F3。
          </p>
        </el-card>
      </div>
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
.side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
</style>
