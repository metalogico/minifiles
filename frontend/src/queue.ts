import { computed, reactive } from 'vue'
import { api, ApiError } from './api'
import { pathParts } from './selection'
import type { UploadEntry } from './selection'

export type Status = 'waiting' | 'uploading' | 'done' | 'skipped' | 'cancelled' | 'error'
export interface QueueItem {
  id: number
  batch: number
  kind: 'file' | 'directory'
  name: string
  size: number
  file: File | null
  path: string
  status: Status
  progress: number
  message: string
  ticket?: string
  xhr?: XMLHttpRequest
}
type SettledStatus = 'done' | 'skipped' | 'error' | 'cancelled'
export type QueueCounts = Record<SettledStatus, number>
const emptyCounts = (): QueueCounts => ({ done: 0, skipped: 0, error: 0, cancelled: 0 })
export const isSettled = (item: QueueItem): item is QueueItem & { status: SettledStatus } =>
  ['done', 'skipped', 'error', 'cancelled'].includes(item.status)
export interface QueueActivity {
  current?: QueueItem
  running: boolean
  cancelling: boolean
  cancelled: boolean
  lastError: string
}
const emptyActivity = (): QueueActivity => ({
  current: undefined,
  running: false,
  cancelling: false,
  cancelled: false,
  lastError: '',
})

type QueueState = 'cancelling' | 'cancelled' | 'running' | 'finished' | 'idle'

function queueState(activity: QueueActivity, remaining: number, total: number): QueueState {
  if (activity.cancelling) return 'cancelling'
  if (activity.cancelled) return 'cancelled'
  if (activity.running || remaining) return 'running'
  return total ? 'finished' : 'idle'
}

function queueLabel(state: QueueState, counts: QueueCounts): string {
  switch (state) {
    case 'cancelling':
      return 'Finishing current file…'
    case 'cancelled':
      return 'Queue cancelled'
    case 'running':
      return 'Uploading'
    case 'finished':
      if (counts.error) return 'Finished with errors'
      if (counts.cancelled || counts.skipped) return 'Queue finished'
      return 'All uploads completed'
    case 'idle':
      return 'No uploads running'
  }
}

function transmitFile(item: QueueItem): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    item.xhr = xhr
    xhr.open('PUT', '/api/uploads/' + item.ticket + '/content')
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')
    xhr.setRequestHeader('X-MiniFiles', '1')
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        item.progress = Math.round((event.loaded / event.total) * 100)
      }
      if (item.progress === 100) item.message = 'Saving to disk…'
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve()
        return
      }
      let detail = 'Upload failed.'
      try {
        detail = JSON.parse(xhr.responseText).detail
      } catch {
        // A proxy error can return HTML instead of the API's JSON error body.
      }
      reject(new ApiError(xhr.status, detail))
    }
    xhr.onerror = () => reject(new Error('Connection lost. Add the file again to retry.'))
    xhr.onabort = () => reject(new Error('Upload cancelled.'))
    xhr.send(item.file!)
  })
}

export function summarizeQueue(
  items: readonly QueueItem[],
  archived: QueueCounts = emptyCounts(),
  activity: QueueActivity = emptyActivity(),
) {
  const counts = { ...archived }
  let remaining = 0
  let current = activity.current
  for (const item of items) {
    if (isSettled(item)) counts[item.status]++
    else {
      remaining++
      if (!activity.current && (!current || item.status === 'uploading')) current = item
    }
  }
  const processed = counts.done + counts.skipped + counts.error + counts.cancelled
  const total = processed + remaining
  const state = queueState(activity, remaining, total)
  const label = queueLabel(state, counts)
  return {
    ...counts,
    total,
    remaining,
    processed,
    current,
    state,
    label,
    lastError: activity.lastError,
    cancelledQueue: activity.cancelled,
    busy: ['running', 'cancelling'].includes(state),
  }
}
export type QueueSummary = ReturnType<typeof summarizeQueue>
interface QueueEvents {
  completed: () => void
  drained: () => void
  expired: () => void
}

export function createQueue(events: QueueEvents) {
  const items = reactive<QueueItem[]>([])
  const archived = reactive(emptyCounts())
  const activity = reactive(emptyActivity())
  const summary = computed(() => summarizeQueue(items, archived, activity))
  let runner: number | undefined
  let nextId = 0
  let nextBatch = 0
  let generation = 0

  function finishItem(item: QueueItem) {
    item.status = 'done'
    item.progress = 100
    item.message = item.kind === 'directory' ? 'Folder ready' : 'Completed'
    archived.done++
    const index = items.findIndex((i) => i.id === item.id)
    if (index !== -1) items.splice(index, 1)
    item.file = null
    events.completed()
  }
  function finishCancellation(notify: boolean) {
    const lastError = activity.lastError
    generation++
    items.splice(0)
    Object.assign(archived, emptyCounts())
    Object.assign(activity, emptyActivity(), { cancelled: true, lastError })
    if (notify) events.drained()
  }
  async function processWaitingItems() {
    if (runner === generation || !items.some((i) => i.status === 'waiting')) return
    const run = generation
    runner = run
    activity.running = true
    try {
      while (run === generation && !activity.cancelling) {
        const item = items.find((i) => i.status === 'waiting')
        if (!item) break
        activity.current = item
        try {
          item.status = 'uploading'
          item.message = item.kind === 'directory' ? 'Preparing folder…' : 'Checking destination…'
          if (item.kind === 'directory') {
            await api('/directories', 'POST', {
              path: [item.path, item.name].filter(Boolean).join('/'),
            })
            if (run === generation && (item.status as Status) !== 'cancelled') finishItem(item)
            continue
          }
          const ticket = await api('/uploads', 'POST', {
            path: item.path,
            name: item.name,
            size: item.size,
          })
          item.ticket = ticket.id
          if (run !== generation || (item.status as Status) !== 'uploading') continue
          item.message = 'Uploading'
          await transmitFile(item)
          if (run === generation && (item.status as Status) !== 'cancelled') finishItem(item)
        } catch (e) {
          if (run === generation) {
            if ((item.status as Status) !== 'cancelled') {
              const duplicate =
                e instanceof ApiError && e.status === 409 && e.detail?.kind === 'duplicate'
              item.status = duplicate ? 'skipped' : 'error'
              item.message = duplicate
                ? 'Skipped: file already exists'
                : e instanceof Error
                  ? e.message
                  : 'Upload interrupted.'
              item.file = null
              if (activity.cancelling && !duplicate) activity.lastError = item.message
            }
            if (e instanceof ApiError && e.status === 401) events.expired()
          }
        } finally {
          // Keep the current item visible through finalization and ticket cleanup.
          if (item.ticket) await api('/uploads/' + item.ticket, 'DELETE').catch(() => {})
          item.ticket = undefined
          item.xhr = undefined
        }
      }
    } finally {
      if (runner === run) runner = undefined
      if (run === generation) {
        if (activity.cancelling) finishCancellation(true)
        else if (items.some((i) => i.status === 'waiting')) void processWaitingItems()
        else {
          activity.running = false
          activity.current = undefined
          events.drained()
        }
      }
    }
  }

  function add(entries: UploadEntry[], path: string) {
    if (activity.cancelling)
      throw new Error('Wait for the current file to finish before adding more files.')
    if (!entries.length) return
    const batchId = ++nextBatch
    const batch = entries.map((entry) => {
      const parts = pathParts([path, entry.relativePath].filter(Boolean).join('/'))
      const name = parts.pop()!
      if (entry.kind === 'file' && name !== entry.file.name)
        throw new Error('The filename does not match the selected path.')
      return {
        id: ++nextId,
        batch: batchId,
        kind: entry.kind,
        name,
        size: entry.kind === 'file' ? entry.file.size : 0,
        file: entry.kind === 'file' ? entry.file : null,
        path: parts.join('/'),
        status: 'waiting' as Status,
        progress: 0,
        message: 'Waiting',
      }
    })
    if (!activity.running && !items.length) Object.assign(archived, emptyCounts())
    activity.cancelled = false
    activity.lastError = ''
    for (const item of batch) items.push(item)
    void processWaitingItems()
  }
  function stop(item: QueueItem) {
    if (isSettled(item)) return
    item.status = 'cancelled'
    item.message = 'Cancelled'
    item.file = null
    item.xhr?.abort()
    if (item.ticket) void api('/uploads/' + item.ticket, 'DELETE').catch(() => {})
  }
  function cancel(item: QueueItem) {
    if (activity.cancelling) return
    if (item.kind === 'directory') {
      const target = [item.path, item.name].filter(Boolean).join('/')
      for (const child of items) {
        const sameBatch = child.batch === item.batch
        const insideFolder = child.path === target || child.path.startsWith(target + '/')
        if (sameBatch && (child.id === item.id || insideFolder)) stop(child)
      }
    } else stop(item)
  }
  function cancelAll() {
    if (activity.cancelling) return
    const notify = activity.running || items.some((i) => !isSettled(i))
    const current = activity.current
    if (current?.xhr) {
      activity.cancelling = true
      for (let index = items.length - 1; index >= 0; index--) {
        const item = items[index]!
        if (item.id === current.id) continue
        if (isSettled(item)) archived[item.status]++
        else archived.cancelled++
        item.file = null
        items.splice(index, 1)
      }
    } else {
      for (const item of items) stop(item)
      finishCancellation(notify)
    }
  }
  function reset() {
    generation++
    for (const item of items) stop(item)
    // A successful item may already have left the list while its cleanup is pending.
    if (activity.current && !items.includes(activity.current)) stop(activity.current)
    items.splice(0)
    Object.assign(archived, emptyCounts())
    Object.assign(activity, emptyActivity())
  }
  return {
    items,
    get summary() {
      return summary.value
    },
    get accepting() {
      return !activity.cancelling
    },
    add,
    cancel,
    cancelAll,
    reset,
  }
}
