<script setup lang="ts">
// S3-F1 commit A 占位：教师工作区（我的课程 + 快捷入口）
// 真实数据（GET /api/courses 教师视角 + 建课表单）在 commit B 接入。
</script>

<template>
  <div class="page">
    <el-card>
      <template #header>教师工作区（S3-F1 commit B 接数据）</template>
      <p class="muted">
        本页将展示"我的课程"列表（GET /api/courses 教师视角）+ 建课表单
        （POST /api/courses）+ 快捷入口。commit B 实现。
      </p>
      <el-button @click="$router.push('/dashboard')">← 返回工作台</el-button>
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
