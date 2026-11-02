<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AxiosError } from 'axios'
import { ElMessage } from 'element-plus'
import { createReport, getLatestReport, normalizePostReport, normalizeStoredReport } from '../api/review'
import { describeApiError, isUnauthorized } from '../api/errors'
import type { NormalizedReport, ReportSection } from '../api/types'

// S2-F7 第二步：报告面板（reports S2-10，api.md:47-49 + errata E-24/E-27/E-28）。
// 双渲染路径（设计 §8.3 + D2 裁定 A）：
//  - POST 刚返回 → NormalizedReport 带 sections[]（结构化渲染，E-27：sections 是 POST 专属）
//  - GET 刷新/已有 → NormalizedReport 带 summary_text（markdown 渲染）
// ⚠️ summary（POST，模型总结一两句）与 summary_text（GET，sections+亮点+建议拼接全文）
//    不是同一个东西——见 api/types.ts NormalizedReport 注释。
// ⚠️ errata E-28：后端无 report_progress/ready SSE，POST 同步阻塞（中位 30.8s）——
//    本组件用骨架屏 +「约 30 秒」提示替代进度推送。
const props = defineProps<{ sessionId: number; sessionStatus: string }>()
const emit = defineEmits<{ (e: 'unauthorized'): void }>()

// rubric v1.0 四维度（与 backend/app/rubric/rubric.json 逐字对应；前端无 rubric 端点，F6）。
const DIMENSIONS = [
  { id: 'argument_structure', name: '论证结构', weight: 0.30 },
  { id: 'evidence_quality', name: '证据质量', weight: 0.25 },
  { id: 'rebuttal_response', name: '反驳与回应', weight: 0.25 },
  { id: 'revision_reflection', name: '观点修订与反思', weight: 0.20 },
] as const

const report = ref<NormalizedReport | null>(null)
const loaded = ref(false)
const generating = ref(false)
const error = ref<string | null>(null)

/**
 * 会话未达终态（waiting/generating/paused）时不允许生成报告——先完成训练。
 * finished / failed 是终态：failed 也可复盘"哪里出了问题"（报告可能 502，
 * 页面内已有错误处理）。
 */
const canGenerate = computed(
  () => props.sessionStatus === 'finished' || props.sessionStatus === 'failed',
)

onMounted(loadLatest)

async function loadLatest() {
  error.value = null
  loaded.value = false
  try {
    const row = await getLatestReport(props.sessionId)
    report.value = normalizeStoredReport(row)
  } catch (err) {
    if (isUnauthorized(err)) {
      emit('unauthorized')
      return
    }
    if (err instanceof AxiosError && err.response?.status === 404) {
      // api.md:48：无报告 → 404（不是错误，是"尚未生成"）
      report.value = null
    } else {
      error.value = describeApiError(err)
    }
  } finally {
    loaded.value = true
  }
}

/**
 * 报告生成的错误文案（Q3 裁定 B：页面内只描述"本次请求"，不重复全局横幅的服务状态）。
 * - 502/504 → "报告生成失败，请稍后重试"——不重复"模型服务不可用"，全局
 *   ModelGatewayBanner 已显示服务状态；
 * - 403/404/网络 → describeApiError（403 透传后端 detail「仅会话所有者可生成报告」，
 *   404 「资源不存在或无权访问」）；
 * - 401 → 由 isUnauthorized 拦截跳 /login（不进本函数）。
 */
function describeReportError(err: unknown): string {
  if (err instanceof AxiosError) {
    const status = err.response?.status
    if (status === 502 || status === 504) {
      return '报告生成失败，请稍后重试'
    }
  }
  return describeApiError(err)
}

async function generate() {
  generating.value = true
  error.value = null
  try {
    const rr = await createReport(props.sessionId)
    // POST 成功后不重拉 GET（D2 约束）：直接用 POST 返回的结构化数据渲染
    report.value = normalizePostReport(rr)
    ElMessage.success('报告已生成')
  } catch (err) {
    if (isUnauthorized(err)) {
      emit('unauthorized')
      return
    }
    error.value = describeReportError(err)
  } finally {
    generating.value = false
  }
}

/** 维度分数卡（scores 是英文 id 键，按 DIMENSIONS 顺序展示）。 */
const scoreCards = computed(() =>
  DIMENSIONS.map((d) => ({
    id: d.id,
    name: d.name,
    weight: d.weight,
    score: report.value?.scores?.[d.id] ?? 0,
  })),
)

const overallScore = computed(() => report.value?.overall_score ?? 0)

/** 结构化 sections（POST 路径）。 */
const structuredSections = computed<ReportSection[]>(() => report.value?.sections ?? [])

/** markdown 分块（GET 路径，summary_text）。 */
const markdownBlocks = computed(() =>
  report.value?.summary_text ? parseSummaryText(report.value.summary_text) : [],
)

/** 亮点 / 改进建议（POST 路径的 strengths/weaknesses；GET 路径从 markdown 解析）。 */
const highlights = computed<string[]>(() => {
  if (report.value?.strengths?.length) return report.value.strengths
  const lit = markdownBlocks.value.find((b) => b.type === 'list' && b.title?.includes('亮点'))
  return lit?.items ?? []
})

const improvements = computed<string[]>(() => {
  if (report.value?.weaknesses?.length) return report.value.weaknesses
  const imp = markdownBlocks.value.find((b) => b.type === 'list' && b.title?.includes('改进'))
  return imp?.items ?? []
})

// ---- 手写 markdown 解析（D3 裁定 A：零依赖；格式由后端 _build_summary_text 控制）----

interface MdBlock {
  type: 'section' | 'list'
  heading?: string
  title?: string
  body?: string
  items?: string[]
}

/**
 * 解析 summary_text：
 *  - `## 标题\n正文` → section
 *  - `**亮点：**\n1. x` / `**改进建议：**\n1. y` → list
 *  - 其余非空块 → section（heading 空）
 */
function parseSummaryText(text: string): MdBlock[] {
  const rawBlocks = text.split(/\n\s*\n/)
  const blocks: MdBlock[] = []
  for (const raw of rawBlocks) {
    const lines = raw.split('\n').map((l) => l.replace(/\s+$/, ''))
    const first = lines[0] ?? ''
    if (first.startsWith('## ')) {
      blocks.push({
        type: 'section',
        heading: first.slice(3).trim(),
        body: lines.slice(1).join('\n').trim(),
      })
    } else if (first.startsWith('**亮点：**') || first.startsWith('**改进建议：**')) {
      const title = first.replace(/^\*\*/, '').replace(/\*\*$/, '').trim()
      const items = lines
        .slice(1)
        .map((l) => l.replace(/^\d+\.\s*/, '').trim())
        .filter(Boolean)
      blocks.push({ type: 'list', title, items })
    } else if (lines.some((l) => /^\d+\.\s/.test(l))) {
      const items = lines
        .map((l) => l.replace(/^\d+\.\s*/, '').trim())
        .filter(Boolean)
      blocks.push({ type: 'list', title: '列表', items })
    } else if (first.trim()) {
      blocks.push({ type: 'section', heading: '', body: raw.trim() })
    }
  }
  return blocks
}

function scoreTagType(score: number): 'success' | 'warning' | 'danger' | 'info' {
  if (score >= 75) return 'success'
  if (score >= 60) return 'warning'
  return 'danger'
}
</script>

<template>
  <el-card>
    <template #header>
      复盘报告
      <el-button
        size="small"
        type="primary"
        :loading="generating"
        :disabled="!canGenerate"
        @click="generate"
      >
        {{ report ? '重新生成报告' : '生成报告' }}
      </el-button>
    </template>

    <!-- 会话未达终态：报告区可访问，但不允许生成（先完成训练） -->
    <el-alert
      v-if="!canGenerate"
      title="训练未完成，请先完成训练"
      :description="`当前会话状态为 ${sessionStatus}。完成训练后可生成复盘报告。`"
      type="warning"
      show-icon
      class="banner"
    />

    <!-- 页面内错误（502/504 等）——具体原因 + 重试 -->
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      closable
      class="banner"
      @close="error = null"
    />

    <!-- 生成中：骨架屏 + 约 30 秒提示（errata E-28：无 SSE 进度） -->
    <div v-if="generating" class="generating">
      <el-skeleton :rows="8" animated />
      <p class="muted">报告生成中（中位约 30 秒，请耐心等待）……</p>
    </div>

    <!-- 尚未生成 -->
    <el-empty
      v-else-if="!report && loaded && !error"
      description="尚未生成复盘报告。请先保存观点版本与反思，再点「生成报告」。"
    />

    <!-- 加载中 -->
    <el-skeleton v-else-if="!loaded" :rows="6" animated />

    <!-- 报告渲染 -->
    <template v-else-if="report">
      <div class="kv">
        <span><b>rubric_version</b> {{ report.rubric_version }}</span>
        <span><b>生成时间</b> {{ report.created_at }}</span>
        <span>
          <b>加权总分</b>
          <el-tag :type="scoreTagType(overallScore)" size="large" effect="dark">
            {{ overallScore }}
          </el-tag>
        </span>
      </div>

      <!-- 四维度分数卡 -->
      <div class="score-grid">
        <div v-for="d in scoreCards" :key="d.id" class="score-card">
          <div class="score-name">{{ d.name }}</div>
          <div class="score-value" :class="'st-' + scoreTagType(d.score)">
            {{ d.score }}
          </div>
          <el-progress
            :percentage="d.score"
            :color="scoreTagType(d.score) === 'success' ? '#67c23a' : scoreTagType(d.score) === 'warning' ? '#e6a23c' : '#f56c6c'"
            :show-text="false"
            :stroke-width="6"
          />
          <div class="score-weight">权重 {{ (d.weight * 100).toFixed(0) }}%</div>
        </div>
      </div>

      <!-- 亮点 / 改进建议 -->
      <div v-if="highlights.length || improvements.length" class="hl-grid">
        <div v-if="highlights.length" class="hl-card">
          <h4>亮点</h4>
          <ul><li v-for="(s, i) in highlights" :key="i">{{ s }}</li></ul>
        </div>
        <div v-if="improvements.length" class="hl-card">
          <h4>改进建议</h4>
          <ul><li v-for="(w, i) in improvements" :key="i">{{ w }}</li></ul>
        </div>
      </div>

      <!-- 正文：结构化 sections（POST）优先，否则 markdown（GET） -->
      <div class="body">
        <template v-if="structuredSections.length">
          <section v-for="s in structuredSections" :key="s.dimension_id" class="sec">
            <h4>{{ s.heading }}</h4>
            <p>{{ s.body }}</p>
          </section>
        </template>
        <template v-else>
          <template v-for="(b, i) in markdownBlocks" :key="i">
            <section v-if="b.type === 'section'" class="sec">
              <h4 v-if="b.heading">{{ b.heading }}</h4>
              <p>{{ b.body }}</p>
            </section>
          </template>
        </template>
      </div>
    </template>
  </el-card>
</template>

<style scoped>
.banner {
  margin-bottom: 12px;
}
.generating {
  padding: 8px 0;
}
.kv {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 13px;
  margin-bottom: 14px;
}
.kv b {
  color: var(--el-text-color-secondary);
  font-weight: 600;
  margin-right: 4px;
}
.score-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}
.score-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
}
.score-name {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.score-value {
  font-size: 24px;
  font-weight: 700;
  margin: 2px 0 6px;
}
.st-success {
  color: var(--el-color-success);
}
.st-warning {
  color: var(--el-color-warning);
}
.st-danger {
  color: var(--el-color-danger);
}
.st-info {
  color: var(--el-text-color-regular);
}
.score-weight {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.hl-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 14px;
}
@media (max-width: 860px) {
  .hl-grid {
    grid-template-columns: 1fr;
  }
}
.hl-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
}
.hl-card h4 {
  margin: 0 0 6px;
  font-size: 13px;
}
.hl-card ul {
  margin: 0;
  padding-left: 20px;
  font-size: 12.5px;
  line-height: 1.7;
}
.body {
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}
.sec {
  margin-bottom: 14px;
}
.sec h4 {
  margin: 0 0 4px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
.sec p {
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
  text-align: center;
  margin-top: 8px;
}
</style>
