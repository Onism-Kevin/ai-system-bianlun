<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { AxiosError } from 'axios'
import { useAuthStore } from '../../stores/auth'
import { getCourse } from '../../api/courses'
import { listCourseTasks, createTask } from '../../api/tasks'
import { getCourseSummary } from '../../api/submissions'
import type { CourseOut, CourseSummaryOut, TaskOut } from '../../api/types'
import { describeApiError, isUnauthorized } from '../../api/errors'
import ModelGatewayBanner from '../../components/ModelGatewayBanner.vue'
import { useLoadError } from '../../composables/useLoadError'
import { formatDeadline } from '../../utils/format'

// S3-F1 commit C + S3-F2 commit A：课程详情 + 任务列表 + 新建任务表单。
// 数据源：GET /api/courses/:id + GET /api/courses/:id/tasks + POST /api/courses/:id/tasks。
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const courseId = Number(route.params.id)
const course = ref<CourseOut | null>(null)
const tasks = ref<TaskOut[]>([])
const loading = ref(false)
// S3-F3：错误处理模式抽到 useLoadError（CourseTasksView 与 TaskDetailView 共用）。
const { loadError, goLogin, handleLoadError, errorTitle, errorDesc } = useLoadError({
  forbiddenTitle: '无权访问该课程',
  forbiddenDesc: '你不是该课程教师，无权管理任务',
  notFoundTitle: '课程不存在',
  notFoundDesc: '课程不存在或已删除',
})
// S3-F2 commit A：表单默认收起，点"新建任务"展开；提交成功后收起。
const showCreateForm = ref(false)
const createForm = reactive({
  title: '',
  material: '',
  // datetime-local 字符串（YYYY-MM-DDTHH:mm:ss）；空=不限时
  deadline: '',
  needJoinCode: false,
})

// S3-F2 commit A：422 逐字段提示（loc 末位=字段名 → formErrors[field]）。
const fieldLabels: Record<string, string> = {
  title: '任务标题',
  material: '课程材料',
  deadline: '截止时间',
  need_join_code: '需要加入码',
}
const formErrors = reactive<Record<string, string>>({})

function clearErrors() {
  Object.keys(formErrors).forEach((k) => delete formErrors[k])
}

function applyValidationErrors(err: unknown) {
  if (!(err instanceof AxiosError)) return
  const data = err.response?.data as { detail?: unknown } | undefined
  const detail = data?.detail
  if (!Array.isArray(detail)) return
  detail.forEach((item) => {
    const record = item as { loc?: unknown[]; msg?: unknown }
    if (!Array.isArray(record.loc)) return
    const field = String(record.loc[record.loc.length - 1])
    const msg = typeof record.msg === 'string' ? record.msg : ''
    const label = fieldLabels[field] ?? field
    if (field === 'title') {
      if (/at least 1/i.test(msg)) formErrors[field] = '标题不能为空'
      else if (/at most 120/i.test(msg)) formErrors[field] = '标题不能超过 120 字符'
      else formErrors[field] = `标题${msg}`
    } else {
      formErrors[field] = `${label}: ${msg}`
    }
  })
}

/** S3-F3：课程汇总（GET /api/courses/:id/summary）。 */
const summary = ref<CourseSummaryOut | null>(null)
const summaryError = ref<string | null>(null)

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
  loading.value = true
  loadError.value = null
  try {
    // S3-F2 commit C：**顺序加载**（先课程，再任务列表），不用 Promise.all——
    // getCourse 403 + listCourseTasks 200 的组合下，Promise.all 会因首个
    // reject 整体失败，丢掉"课程可读但非教师"这个真实语义。
    try {
      course.value = await getCourse(courseId)
    } catch (err) {
      if (handleLoadError(err)) return
    }
    try {
      tasks.value = await listCourseTasks(courseId)
    } catch (err) {
      if (handleLoadError(err)) return
    }
  } finally {
    loading.value = false
  }
  // S3-F3：课程汇总是次级区块——失败不阻塞任务列表（401 除外，跳登录）。
  await loadSummary()
}

/** S3-F3：加载课程汇总；失败仅在汇总卡片内联提示，不影响任务列表。 */
async function loadSummary() {
  summaryError.value = null
  try {
    summary.value = await getCourseSummary(courseId)
  } catch (err) {
    if (isUnauthorized(err)) {
      goLogin()
      return
    }
    summaryError.value = describeApiError(err)
  }
}

async function onCreateTask() {
  clearErrors()
  loading.value = true
  try {
    const created = await createTask(courseId, {
      title: createForm.title.trim(),
      material: createForm.material.trim() || null,
      deadline: createForm.deadline || null,
      need_join_code: createForm.needJoinCode,
    })
    ElMessage.success(`任务已创建（id=${created.id}，join_code=${created.join_code ?? '—'}）`)
    // S3-F2：表单收起 + 清空
    createForm.title = ''
    createForm.material = ''
    createForm.deadline = ''
    createForm.needJoinCode = false
    showCreateForm.value = false
    await loadData()
  } catch (err) {
    if (isUnauthorized(err)) {
      goLogin()
      return
    }
    // S3-F2 commit A：422 逐字段提示（字段级，不用 toast 兜底）
    if (err instanceof AxiosError && err.response?.status === 422) {
      applyValidationErrors(err)
      return
    }
    // S3-F2 commit C：403/404/网络 → loadError 空状态（不用 toast 当唯一反馈）
    handleLoadError(err)
  } finally {
    loading.value = false
  }
}

function openTask(task: TaskOut) {
  router.push(`/teacher/courses/${courseId}/tasks/${task.id}`)
}

/** S3-F2 commit B：复制加入码。优先 clipboard API，失败降级为 execCommand。 */
async function copyJoinCode(code: string) {
  try {
    await navigator.clipboard.writeText(code)
    ElMessage.success('加入码已复制')
    return
  } catch {
    // 降级：临时 textarea + execCommand（部分环境 clipboard API 不可用）
    const ta = document.createElement('textarea')
    ta.value = code
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand('copy')
      ElMessage.success('加入码已复制')
    } catch {
      ElMessage.warning(`复制失败，请手动复制：${code}`)
    }
    document.body.removeChild(ta)
  }
}
</script>

<template>
  <div class="page">
    <div class="hdr">
      <div>
        <h1>{{ course ? course.name : '课程' }}（id={{ courseId }}）</h1>
        <span class="sub">
          <template v-if="loadError">{{ errorTitle }}</template>
          <template v-else-if="course">
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

    <!-- S3-F3：课程汇总（次级区块；loadError=null 时显示，失败不阻塞任务列表） -->
    <el-card v-if="loadError === null" class="summary-card">
      <template #header>
        课程汇总
        <el-button link type="primary" size="small" @click="loadSummary">刷新</el-button>
      </template>
      <el-descriptions v-if="summary" :column="3" border>
        <el-descriptions-item label="全部任务提交数">
          {{ summary.submitted_count }}
        </el-descriptions-item>
        <el-descriptions-item label="学生总数">
          {{ summary.total_students }}
        </el-descriptions-item>
        <el-descriptions-item label="待核实 Top5">
          {{
            summary.top_pending_verification.length
              ? summary.top_pending_verification.length + ' 项'
              : '暂无（E-29）'
          }}
        </el-descriptions-item>
      </el-descriptions>
      <p v-if="summaryError" class="muted summary-error">{{ summaryError }}</p>
      <p v-else-if="!summary" class="muted">汇总加载中…</p>
      <p v-else class="muted">
        课程级汇总：全部任务的提交总数（非单任务）；待核实项为空（errata E-29：MVP
        不实现，S5 报告生成时提取）。
      </p>
    </el-card>

    <!-- S3-F2 commit C：错误空状态（loadError 驱动，不用 toast 当唯一反馈） -->
    <el-card v-if="loadError" class="error-state">
      <el-result
        :icon="loadError === 'network' ? 'warning' : 'error'"
        :title="errorTitle"
        :sub-title="errorDesc"
      >
        <template #extra>
          <el-button @click="router.push('/teacher')">返回课程列表</el-button>
          <el-button
            v-if="loadError === 'network'"
            type="primary"
            :loading="loading"
            @click="loadData"
          >
            重试
          </el-button>
        </template>
      </el-result>
    </el-card>

    <div v-else class="grid">
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
          <!-- S3-F2 commit B：加入码列（教师视角才有；后端按权限分支序列化） -->
          <el-table-column label="加入码" width="210">
            <template #default="{ row }">
              <template v-if="row.join_code">
                <span class="join-code">{{ row.join_code }}</span>
                <el-button
                  link
                  type="primary"
                  size="small"
                  @click="copyJoinCode(row.join_code as string)"
                >
                  复制
                </el-button>
              </template>
              <span v-else class="muted">—</span>
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
        <el-button v-if="!showCreateForm" type="primary" plain @click="showCreateForm = true">
          + 新建任务
        </el-button>
        <el-form v-else label-position="top" @submit.prevent="onCreateTask">
          <el-form-item label="任务标题" :error="formErrors.title">
            <el-input v-model="createForm.title" placeholder="如：AI 伦理辩论" />
          </el-form-item>
          <el-form-item label="课程材料（文本粘贴）" :error="formErrors.material">
            <el-input
              v-model="createForm.material"
              type="textarea"
              :rows="4"
              placeholder="粘贴任务材料"
            />
            <div class="muted hint">文件上传留 S5（schema_v2 表 1：material 为 TEXT）</div>
          </el-form-item>
          <el-form-item label="截止时间（可选）" :error="formErrors.deadline">
            <el-date-picker
              v-model="createForm.deadline"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ss"
              placeholder="选择截止时间（空=不限时）"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="需要加入码" :error="formErrors.need_join_code">
            <el-switch v-model="createForm.needJoinCode" />
            <span class="muted hint">开启后服务端生成 8 位加入码</span>
          </el-form-item>
          <div class="form-actions">
            <el-button type="primary" :loading="loading" @click="onCreateTask">创建任务</el-button>
            <el-button @click="showCreateForm = false">取消</el-button>
          </div>
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
.form-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
.hint {
  margin-top: 4px;
  line-height: 1.4;
}
.join-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  letter-spacing: 0.5px;
  color: var(--el-text-color-primary);
}
.error-state {
  margin-top: 16px;
}
.summary-card {
  margin-bottom: 16px;
}
.summary-error {
  color: var(--el-color-danger);
}
</style>
