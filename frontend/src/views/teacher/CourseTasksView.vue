<script setup lang="ts">
// S3-F1 commit A 占位：课程详情 + 任务列表
// 真实数据（GET /api/courses/:id + GET /api/courses/:id/tasks）在 commit C 接入。
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="page">
    <el-card>
      <template #header>课程详情 + 任务列表（S3-F1 commit C 接数据）</template>
      <p class="muted">
        当前课程 id = {{ route.params.id }}。
        将展示课程详情头 + 任务列表（GET /api/courses/:id/tasks）。
        commit C 实现。
      </p>
      <el-button @click="$router.push('/teacher')">← 返回教师工作区</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.page {
  max-width: 1060px;
  margin: 0 auto;
  padding: 20px 16px 48px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
