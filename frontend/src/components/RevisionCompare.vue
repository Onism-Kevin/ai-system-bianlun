<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createRevision, listRevisions, updateRevision } from '../api/review'
import { describeApiError, isUnauthorized } from '../api/errors'
import type { RevisionListItem, RevisionStatus } from '../api/types'

// S2-F7 第一步：观点版本对比组件（revisions S2-11，api.md:50-53）。
// 职责：列表 / 选中查看 / 新建 / 编辑保存 / diff 渲染。
// E-25 双语义（必须按数据来源区分，不靠猜）：
//  - 列表项的 diff_vs_prev（GET 来的）→ "版本间"（v{prev} vs v{curr}）
//  - PATCH 返回的 diff_vs_prev → "同 revision 修改前 vs 修改后"
// 新建/保存成功后局部刷新列表，不重拉全量（列表本身已含 diff_vs_prev）。
const props = defineProps<{ sessionId: number }>()
const emit = defineEmits<{ (e: 'unauthorized'): void }>()

const revisions = ref<RevisionListItem[]>([])
const selectedId = ref<number | null>(null)
const draftContent = ref('')
const draftStatus = ref<RevisionStatus>('draft')
const saving = ref(false)
const error = ref<string | null>(null)
/** PATCH 后返回的"修改前后"diff（E-25） */
const patchDiff = ref<string | null>(null)

onMounted(load)

async function load() {
  error.value = null
  try {
    revisions.value = await listRevisions(props.sessionId)
  } catch (err) {
    if (isUnauthorized(err)) {
      emit('unauthorized')
      return
    }
    error.value = describeApiError(err)
  }
}

function selectRevision(rev: RevisionListItem) {
  selectedId.value = rev.id
  draftContent.value = rev.content
  draftStatus.value = rev.status === 'final' ? 'final' : 'draft'
  patchDiff.value = null
  error.value = null
}

function newDraft() {
  selectedId.value = null
  draftContent.value = ''
  draftStatus.value = 'draft'
  patchDiff.value = null
  error.value = null
}

async function save() {
  const text = draftContent.value.trim()
  if (!text) {
    ElMessage.warning('请填写观点内容')
    return
  }
  saving.value = true
  error.value = null
  try {
    if (selectedId.value !== null) {
      // PATCH：更新已有 revision（E-25：返回修改前后 diff）
      const res = await updateRevision(selectedId.value, {
        content: text,
        status: draftStatus.value,
      })
      patchDiff.value = res.diff_vs_prev
      // 局部更新列表项（content/status 可能变化）
      const idx = revisions.value.findIndex((r) => r.id === selectedId.value)
      if (idx >= 0) {
        revisions.value[idx] = {
          ...revisions.value[idx],
          content: res.revision.content,
          status: res.revision.status,
        }
      }
      ElMessage.success(`版本 v${res.revision.version} 已保存`)
    } else {
      // POST：新建版本（初稿 version=1 起自增）
      await createRevision({
        session_id: props.sessionId,
        content: text,
        status: draftStatus.value,
      })
      ElMessage.success('新观点版本已创建')
      await load()
    }
  } catch (err) {
    if (isUnauthorized(err)) {
      emit('unauthorized')
      return
    }
    error.value = describeApiError(err)
  } finally {
    saving.value = false
  }
}

const selected = computed(
  () => revisions.value.find((r) => r.id === selectedId.value) ?? null,
)

/** 选中项的 GET diff（版本间）；首版 null。 */
const selectedDiff = computed(() => selected.value?.diff_vs_prev ?? null)

/** 当前展示 diff：PATCH 修改前后优先，否则版本间。 */
const currentDiff = computed(() => patchDiff.value ?? selectedDiff.value)

const diffLabel = computed(() => {
  if (patchDiff.value !== null) return '本次修改：修改前 → 修改后（同 revision，E-25）'
  if (selectedDiff.value !== null) return '版本间对比（GET diff_vs_prev，E-25）'
  if (selected.value) return '首版（无上一版，diff 为 null）'
  return '尚未选择版本'
})

interface DiffLine {
  text: string
  type: 'add' | 'del' | 'context' | 'header'
}

/** unified diff 逐行着色（手写，零依赖；格式由后端 difflib 稳定产出）。 */
const diffLines = computed<DiffLine[]>(() => {
  if (!currentDiff.value) return []
  return currentDiff.value.split('\n').map((line) => {
    if (line.startsWith('---') || line.startsWith('+++')) return { text: line, type: 'header' as const }
    if (line.startsWith('@@')) return { text: line, type: 'context' as const }
    if (line.startsWith('+')) return { text: line, type: 'add' as const }
    if (line.startsWith('-')) return { text: line, type: 'del' as const }
    return { text: line, type: 'context' as const }
  })
})

function statusTagType(status: string): 'success' | 'info' {
  return status === 'final' ? 'success' : 'info'
}
</script>

<template>
  <el-card>
    <template #header>
      观点版本对比（revisions，api.md:50-53）
      <el-button size="small" type="primary" link @click="newDraft">+ 新建版本</el-button>
    </template>

    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      closable
      class="banner"
      @close="error = null"
    />

    <div class="split">
      <!-- 左：版本列表 -->
      <div class="col">
        <el-empty v-if="revisions.length === 0" description="尚无观点版本，点「新建版本」开始" />
        <div v-else class="rev-list">
          <div
            v-for="rev in revisions"
            :key="rev.id"
            class="rev-item"
            :class="{ active: rev.id === selectedId }"
            @click="selectRevision(rev)"
          >
            <div class="rev-head">
              <b>v{{ rev.version }}</b>
              <el-tag size="small" :type="statusTagType(rev.status)">{{ rev.status }}</el-tag>
              <span class="muted">{{ rev.created_at }}</span>
            </div>
            <div class="rev-content">{{ rev.content }}</div>
          </div>
        </div>
      </div>

      <!-- 右：编辑 + diff -->
      <div class="col">
        <el-input
          v-model="draftContent"
          type="textarea"
          :rows="8"
          :disabled="saving"
          placeholder="输入/编辑观点内容……"
        />
        <div class="row">
          <el-radio-group v-model="draftStatus" size="small">
            <el-radio-button value="draft">草稿</el-radio-button>
            <el-radio-button value="final">定稿</el-radio-button>
          </el-radio-group>
          <el-button type="primary" :loading="saving" @click="save">
            {{ selectedId !== null ? '保存修改' : '创建版本' }}
          </el-button>
        </div>

        <div class="diff-block">
          <div class="diff-label">{{ diffLabel }}</div>
          <pre v-if="diffLines.length" class="diff"><span
              v-for="(line, i) in diffLines"
              :key="i"
              :class="'diff-' + line.type"
            >{{ line.text }}
</span></pre>
          <p v-else class="muted">选择左侧版本查看对比；新建版本无 diff（首版 null）。</p>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.banner {
  margin-bottom: 12px;
}
.split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
@media (max-width: 860px) {
  .split {
    grid-template-columns: 1fr;
  }
}
.col {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rev-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rev-item {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 8px 10px;
  cursor: pointer;
}
.rev-item.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.rev-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.rev-content {
  font-size: 12.5px;
  color: var(--el-text-color-regular);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.diff-block {
  margin-top: 8px;
}
.diff-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.diff {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.6;
  overflow: auto;
  max-height: 320px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
.diff-add {
  color: var(--el-color-success);
}
.diff-del {
  color: var(--el-color-danger);
}
.diff-header {
  color: var(--el-text-color-secondary);
  font-weight: 600;
}
.diff-context {
  color: var(--el-text-color-regular);
}
</style>
