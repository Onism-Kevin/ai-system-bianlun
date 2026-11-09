/**
 * S3-F4：消息角色标签映射。
 *
 * 从 TrainingView 的 roleLabel 内联逻辑抽出，供 MessageStream 组件按 mode
 * 选择默认标签。接口窄：只做"角色 → 显示文案"的映射。
 */

export interface RoleLabels {
  /** role='user' 的标签 */
  user: string
  /** assistant 无 agent_role 时的兜底标签 */
  assistant: string
  /** agent_role → 标签（可选，drill 的 pro → 正方学生） */
  byAgent?: Record<string, string>
}

/** 按 mode 取默认标签：drill（教师引导）与 training（学生训练）语义不同。 */
export function labelsForMode(mode: string): RoleLabels {
  if (mode === 'drill') {
    return {
      user: '教师',
      // drill 只应出现 pro；出现其他角色说明后端行为有偏差，用调试文案暴露
      assistant: '未知角色（应为 pro）',
      byAgent: { pro: '正方学生' },
    }
  }
  // training：与 TrainingView 既有 roleLabel 逐字一致（重构不改变渲染）
  return {
    user: '学生',
    assistant: 'AI 教练',
    byAgent: { pro: '正方', con: '反方', judge: '裁判' },
  }
}

/** 单条消息的角色标签：user → labels.user；assistant + agent_role → byAgent 或 assistant。 */
export function roleLabel(
  role: string,
  agentRole: string | null | undefined,
  labels: RoleLabels,
): string {
  if (role === 'user') return labels.user
  if (agentRole && labels.byAgent && labels.byAgent[agentRole]) {
    return labels.byAgent[agentRole]
  }
  return labels.assistant
}
