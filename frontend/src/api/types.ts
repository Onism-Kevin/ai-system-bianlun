// 与 backend/app/schemas/auth.py 逐字对应（S2-1 出参形状，api.md:25-27）
export interface AuthUser {
  id: number
  username: string
  display_name: string | null
}

export interface RegisterResponse {
  id: number
  username: string
  roles: string[]
}

export interface LoginResponse {
  user: AuthUser
}

export interface MeResponse {
  user: AuthUser
  roles: string[]
}

// 与 backend/app/schemas/session.py 对应（S2-3，api.md:28）
export interface SessionCreated {
  id: number
  status: string
}

export interface SessionCreateBody {
  topic: string
  visibility?: 'private' | 'task'
  task_id?: number | null
}

// 与 backend/app/schemas/session.py SessionOut 对应（S2-3，api.md:29/30 出参）
export interface SessionOut {
  id: number
  topic: string
  visibility: string
  task_id: number | null
  status: string
  created_at: string
  updated_at: string
}

// 与 backend/app/schemas/message.py 对应（S2-4 落库，api.md:35/38）
export interface MessageCreated {
  seq: number
  created_at: string
}

export interface MessageOut {
  seq: number
  role: 'user' | 'assistant' | 'system'
  agent_role: 'pro' | 'con' | 'judge' | 'coach' | null
  content: string
  status: 'streaming' | 'complete' | 'paused_truncated'
  created_at: string
}

export interface MessageListOut {
  messages: MessageOut[]
  next_seq: number
}

// 与 docs/contracts/sse_events.md §4 事件总表逐字对应（S2-F5 useSSE 消费）。
// 注意：只有 speech_* 帧服务端写 id: 行（=seq），EventSource 原生把 id 透传到
// event.lastEventId；帧内 seq 字段冗余但前端按帧内 seq upsert（§7.4 幂等）。
export interface SseSpeechStartFrame {
  seq: number
  agent_role: 'pro' | 'con' | 'judge' | 'coach'
}

export interface SseSpeechDeltaFrame {
  seq: number
  delta: string
}

export interface SseSpeechEndFrame {
  seq: number
  status: 'complete' | 'paused_truncated'
}

export interface SseSpeechSnapshotFrame {
  seq: number
  agent_role: 'pro' | 'con' | 'judge' | 'coach'
  content: string
  status: 'streaming' | 'complete' | 'paused_truncated'
}

export interface SseErrorFrame {
  code: 'model_connection' | 'model_timeout' | 'model_server' | 'structured_validation' | 'internal' | string
  message: string
  retryable: boolean
  fatal: boolean
}

export interface SseDoneFrame {
  reason: 'finished' | 'failed' | string
}
