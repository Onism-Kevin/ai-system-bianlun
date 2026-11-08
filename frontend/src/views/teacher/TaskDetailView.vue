<script setup lang="ts">
// S3-F1 commit A 占位：提交查看页（S3-F3 实现）
// 路由先建好避免死链；真实提交列表（GET /api/tasks/:id/submissions）在 S3-F3 接入。
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="page">
    <el-card>
      <template #header>提交查看（S3-F3 实现）</template>
      <p class="muted">
        任务 id = {{ route.params.tid }}，课程 id = {{ route.params.id }}。
        本页将展示学生提交列表（GET /api/tasks/:id/submissions）。S3-F3 实现。
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
