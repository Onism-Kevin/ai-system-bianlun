import { onScopeDispose, ref } from 'vue'
import type { Ref } from 'vue'
import type {
  SseDoneFrame,
  SseErrorFrame,
  SseSpeechDeltaFrame,
  SseSpeechEndFrame,
  SseSpeechSnapshotFrame,
  SseSpeechStartFrame,
} from '../api/types'

// S2-F5：SSE 客户端封装（sse_events.md §8 前端重连策略的落地实现）。
//
// 为什么用 EventSource 而不是 fetch 流式解析：
// - EventSource 重连时原生携带 Last-Event-ID 头（服务端 _resolve_after_seq
//   优先解析该头，sse §7.1），fetch 手写要把这个行为重造；
// - 服务端建流即发 `retry: 5000`（sse §2），EventSource 原生消费该指令；
// - 按事件名 addEventListener 分发，与 §4 事件总表一一对应。
// 代价：EventSource 只支持 GET——发送消息走 REST POST（既定架构，sse §9）。
//
// 契约边界（§8 原文 → 实现）：
// - onerror 且 15s 窗口内 ≥3 次（窗口内无任何消息）→ close() 转手动退避；
// - 退避档位 1s→2s→4s→8s→16s→30s 封顶，累计 10 次仍未连上→放弃；
// - 每次成功收到任意事件→重置窗口计数与退避档位；
// - done（finished/failed）→ close 不重连（§5.10 唯一终态信号）；
// - after_seq 仅首连；重连一律经本封装，Last-Event-ID 由浏览器自动携带。

export interface SseHandlers {
  onStart?: (frame: SseSpeechStartFrame) => void
  onDelta?: (frame: SseSpeechDeltaFrame) => void
  onEnd?: (frame: SseSpeechEndFrame) => void
  onSnapshot?: (frame: SseSpeechSnapshotFrame) => void
  /** 流内 error 事件（§5.7）。只展示 UI，客户端不得因此自动重试生成。 */
  onError?: (frame: SseErrorFrame) => void
  /** 成功建流（reset 退避档位的时机之一）。 */
  onOpen?: () => void
  /** done(reason='failed')：终态，不重连。 */
  onFatal?: (reason: string) => void
  /** done(reason='finished')：正常终态，不重连。 */
  onFinished?: () => void
  /** §8 累计 10 次放弃：UI 呈现「连接已断开 + [重新连接]」手动按钮。 */
  onGiveUp?: () => void
}

export interface UseSseOptions {
  /** 仅首连生效（sse §8「after_seq 仅首连」）；重连靠原生 Last-Event-ID。 */
  afterSeq?: number
}

/** §8 退避档位（ms）：1s→2s→4s→8s→16s→30s 封顶。 */
const BACKOFF_STEPS = [1000, 2000, 4000, 8000, 16000, 30000] as const
/** §8：15s 窗口内 ≥3 次 onerror（且窗口内无任何消息）转手动退避。 */
const ERROR_WINDOW_MS = 15000
const ERROR_WINDOW_MAX = 3
/** §8：累计 10 次仍未连上→放弃。 */
const MAX_ATTEMPTS = 10

export interface UseSseResult {
  /** 连接状态（UI 徽标用）：idle / connecting / open / retrying / given-up。 */
  status: Ref<string>
  /** 主动断开（组件卸载 / done 收尾调用）。幂等。 */
  close: () => void
  /** 放弃态或 done 态下的手动重连入口（UI「重新连接」按钮）。 */
  reconnect: () => void
}

export function useSSE(
  url: string,
  handlers: SseHandlers,
  options: UseSseOptions = {},
): UseSseResult {
  const status = ref<string>('idle')

  let source: EventSource | null = null
  /** close() 显式置位后 onerror 不再触发重连（done/卸载/手动放弃路径）。 */
  let closedByUs = false
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  // §8 重连记账
  let windowStart = Date.now()
  let windowErrors = 0
  let backoffLevel = 0
  let attempts = 0
  let givenUp = false

  function noteActivity(): void {
    // 「每次成功收到任意事件→重置窗口计数与退避档位」
    windowStart = Date.now()
    windowErrors = 0
    backoffLevel = 0
    attempts = 0
  }

  function buildUrl(first: boolean): string {
    if (first && options.afterSeq !== undefined) {
      const sep = url.includes('?') ? '&' : '?'
      return `${url}${sep}after_seq=${options.afterSeq}`
    }
    return url
  }

  function parseFrame<T>(raw: string): T | null {
    try {
      return JSON.parse(raw) as T
    } catch {
      // 服务端 data 一律单行 JSON（sse §2 帧格式）；解析失败=协议外数据，忽略。
      return null
    }
  }

  function attach(source: EventSource): void {
    source.addEventListener('open', () => {
      status.value = 'open'
      handlers.onOpen?.()
    })

    // 每个事件入口统一 noteActivity：包括心跳之外的一切 message 事件。
    // 注意 `: hb` 注释行不是 event，EventSource 不派发，不触发重置——
    // 符合 §8「窗口内无任何消息」语义（hb 是注释帧不是 message）。
    source.addEventListener('speech_start', (ev) => {
      noteActivity()
      const frame = parseFrame<SseSpeechStartFrame>((ev as MessageEvent).data)
      if (frame) handlers.onStart?.(frame)
    })
    source.addEventListener('speech_delta', (ev) => {
      noteActivity()
      const frame = parseFrame<SseSpeechDeltaFrame>((ev as MessageEvent).data)
      if (frame) handlers.onDelta?.(frame)
    })
    source.addEventListener('speech_end', (ev) => {
      noteActivity()
      const frame = parseFrame<SseSpeechEndFrame>((ev as MessageEvent).data)
      if (frame) handlers.onEnd?.(frame)
    })
    source.addEventListener('speech_snapshot', (ev) => {
      noteActivity()
      const frame = parseFrame<SseSpeechSnapshotFrame>((ev as MessageEvent).data)
      if (frame) handlers.onSnapshot?.(frame)
    })
    source.addEventListener('error', (ev) => {
      // 流内 error 事件（§5.7）。⚠️ 与 source.onerror（传输层）同名不同源：
      // 这里捕获的是服务端推送的业务 error 帧，不是连接错误。
      noteActivity()
      const frame = parseFrame<SseErrorFrame>((ev as MessageEvent).data)
      if (frame) handlers.onError?.(frame)
    })
    source.addEventListener('done', (ev) => {
      noteActivity()
      const frame = parseFrame<SseDoneFrame>((ev as MessageEvent).data)
      const reason = frame?.reason ?? 'finished'
      // §5.10：done 是唯一终态信号，收到即 close 不重连。
      // 必须先 close()（readyState=CLOSED 后 onerror 不再触发自动重连），
      // 否则浏览器会把服务端正常关流也当作一次 onerror 并重连。
      close()
      if (reason === 'failed') {
        status.value = 'idle'
        handlers.onFatal?.(reason)
      } else {
        status.value = 'idle'
        handlers.onFinished?.()
      }
    })
  }

  function scheduleRetry(): void {
    if (closedByUs || givenUp) return
    if (backoffLevel >= BACKOFF_STEPS.length) backoffLevel = BACKOFF_STEPS.length - 1
    const delay = BACKOFF_STEPS[backoffLevel]
    backoffLevel += 1
    attempts += 1
    if (attempts >= MAX_ATTEMPTS) {
      givenUp = true
      status.value = 'given-up'
      handlers.onGiveUp?.()
      return
    }
    status.value = 'retrying'
    retryTimer = setTimeout(() => {
      retryTimer = null
      if (closedByUs || givenUp) return
      open(false)
    }, delay)
  }

  function open(first: boolean): void {
    if (closedByUs) return
    source?.close()
    status.value = 'connecting'
    const next = new EventSource(buildUrl(first))
    source = next
    // 传输层错误/流被关闭：EventSource 会自动重连（浏览器行为），但 §8 要求
    // 15s 窗口 ≥3 次即接管为手动退避，避免浏览器默认节奏太激进。
    next.onerror = () => {
      if (closedByUs) return
      const now = Date.now()
      if (now - windowStart > ERROR_WINDOW_MS) {
        windowStart = now
        windowErrors = 0
      }
      windowErrors += 1
      if (windowErrors >= ERROR_WINDOW_MAX) {
        next.close()
        source = null
        scheduleRetry()
      }
      // 否则交给浏览器默认重连（连接尚未稳定失败）
    }
    attach(next)
  }

  function close(): void {
    closedByUs = true
    if (retryTimer !== null) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
    source?.close()
    source = null
  }

  function reconnect(): void {
    closedByUs = false
    givenUp = false
    backoffLevel = 0
    attempts = 0
    windowStart = Date.now()
    windowErrors = 0
    open(false)
  }

  // 首连（after_seq 仅此一次生效）
  open(true)

  // 组件作用域卸载时自动断开，避免离开页面仍重试（§8 兜底之外的双保险）。
  onScopeDispose(() => {
    close()
  })

  return { status, close, reconnect }
}
