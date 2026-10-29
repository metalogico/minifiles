import { ref, shallowRef } from 'vue'
import { api } from './api'
import type { Stats } from './api'

type Reason = 'initial' | 'queue' | 'manual'
export function createStatsController(queueBusy: () => boolean, failed: (error: unknown) => void) {
  const stats = shallowRef<Stats | null>(null)
  const updating = ref(false)
  let pending: Reason | undefined
  let worker: { controller: AbortController; promise: Promise<void> } | undefined

  function pollDelay(signal: AbortSignal) {
    return new Promise<void>((resolve) => {
      const finish = () => {
        clearTimeout(timer)
        signal.removeEventListener('abort', finish)
        resolve()
      }
      const timer = setTimeout(finish, 1000)
      signal.addEventListener('abort', finish, { once: true })
      if (signal.aborted) finish()
    })
  }
  function request(reason: Reason) {
    pending = pending === 'manual' || reason === 'manual' ? 'manual' : reason
    if (worker) return worker.promise
    const controller = new AbortController()
    const task = { controller, promise: Promise.resolve() }
    worker = task
    updating.value = true
    task.promise = (async () => {
      while (pending && !controller.signal.aborted) {
        const next = pending
        pending = undefined
        try {
          await api('/stats/refresh', 'POST', undefined, controller.signal)
          let snapshot = await api<Stats>('/stats', 'GET', undefined, controller.signal)
          while (snapshot.scanning && !controller.signal.aborted) {
            await pollDelay(controller.signal)
            if (!controller.signal.aborted)
              snapshot = await api<Stats>('/stats', 'GET', undefined, controller.signal)
          }
          if (!controller.signal.aborted && (next !== 'queue' || !queueBusy()))
            stats.value = snapshot
        } catch (error) {
          if (!controller.signal.aborted) failed(error)
        }
      }
    })().finally(() => {
      if (worker === task) {
        worker = undefined
        updating.value = false
      }
    })
    return task.promise
  }
  function reset() {
    worker?.controller.abort()
    worker = undefined
    pending = undefined
    updating.value = false
    stats.value = null
  }
  return {
    stats,
    updating,
    load: () => request('initial'),
    refresh: () => request('manual'),
    queueFinished: () => request('queue'),
    reset,
  }
}
