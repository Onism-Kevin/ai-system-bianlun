<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getReflection, saveReflection } from '../api/review'
import { describeApiError, isUnauthorized } from '../api/errors'

// S2-F7 第一步：个人反思表单（G2 裁定，api.md:36-37）。
// S1-9b 裁定：报告生成前填写反思——本组件在报告生成按钮上方（设计 §1 顺序②）。
// 未填写时显示 textarea（空）+「未填写反思」提示 + 保存按钮，不隐藏区块
// （反思是报告输入，必须可见可填）。
const props = defineProps<{ sessionId: number }>()
const emit = defineEmits<{ (e: 'unauthorized'): void }>()

const content = ref('')
const updatedAt = ref<string | null>(null)
const loaded = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)

onMounted(load)

async function load() {
  error.value = null
  try {
    const res = await getReflection(props.sessionId)
    // api.md:37：未填写时 content=null（不 404）
    content.value = res.content ?? ''
    updatedAt.value = res.updated_at
  } catch (err) {
    if (isUnauthorized(err)) {
      emit('unauthorized')
      return
    }
    error.value = describeApiError(err)
  } finally {
    loaded.value = true
  }
}

async function save() {
  const text = content.value.trim()
  if (!text) {
    ElMessage.warning('请填写反思内容')
    return
  }
  saving.value = true
  error.value = null
  try {
    const res = await saveReflection(props.sessionId, text)
    updatedAt.value = res.updated_at
    ElMessage.success('反思已保存')
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
</script>

<template>
  <el-card>
    <template #header>
      个人反思（报告生成前填写，S1-9b）
      <span v-if="updatedAt" class="muted">· 上次保存 {{ updatedAt }}</span>
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

    <el-input
      v-model="content"
      type="textarea"
      :rows="5"
      :disabled="saving"
      placeholder="回顾这场训练：你依据了哪些反馈？改了什么？为什么这样改？"
    />

    <div class="row">
      <el-button type="primary" :loading="saving" @click="save">保存反思</el-button>
      <span class="muted">
        未填写反思时，「观点修订与反思」维度按「反思缺失」计（rubric D4）。
      </span>
    </div>
    <p v-if="!loaded" class="muted">加载中……</p>
  </el-card>
</template>

<style scoped>
.banner {
  margin-bottom: 12px;
}
.row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
