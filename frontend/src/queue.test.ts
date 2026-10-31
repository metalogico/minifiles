import { afterEach, describe, expect, it, vi } from 'vitest'
import { createQueue } from './queue'
import { ApiError } from './api'
import { selectionFromFiles } from './selection'

const { mockApi } = vi.hoisted(() => ({ mockApi: vi.fn() }))
vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  api: mockApi,
}))
class FakeXHR {
  static active = 0
  static maxActive = 0
  static pending: FakeXHR[] = []
  status = 200
  responseText = '{}'
  upload = { onprogress: undefined as any }
  onload: any
  onabort: any
  onerror: any
  open() {}
  setRequestHeader() {}
  send() {
    FakeXHR.active++
    FakeXHR.maxActive = Math.max(FakeXHR.maxActive, FakeXHR.active)
    FakeXHR.pending.push(this)
  }
  progress(value: number) {
    this.upload.onprogress?.({ lengthComputable: true, loaded: value, total: 100 })
  }
  finish() {
    FakeXHR.active--
    FakeXHR.pending.splice(FakeXHR.pending.indexOf(this), 1)
    this.onload()
  }
  abort() {
    FakeXHR.active--
    FakeXHR.pending.splice(FakeXHR.pending.indexOf(this), 1)
    this.onabort()
  }
}
const flush = async () => {
  for (let i = 0; i < 30; i++) await Promise.resolve()
}
const file = (name: string) => new File(['abc'], name)
function setup() {
  vi.stubGlobal('XMLHttpRequest', FakeXHR)
  mockApi.mockResolvedValue({ id: 'upload' })
  const events = { completed: vi.fn(), drained: vi.fn(), expired: vi.fn() }
  return { queue: createQueue(events), events }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}
afterEach(() => {
  vi.unstubAllGlobals()
  mockApi.mockReset()
  FakeXHR.active = 0
  FakeXHR.maxActive = 0
  FakeXHR.pending = []
})

describe('serial queue lifecycle', () => {
  it('never queues or counts excluded metadata and does not end an empty selection', async () => {
    const { queue, events } = setup()
    queue.add(selectionFromFiles([file('.DS_Store'), file('._photo.jpg')]), 'Books')
    await flush()
    expect(queue.items).toHaveLength(0)
    expect(mockApi).not.toHaveBeenCalled()
    expect(events.drained).not.toHaveBeenCalled()
    queue.add(
      selectionFromFiles([file('.DS_Store'), file('photo.jpg'), file('._photo.jpg')]),
      'Books',
    )
    await flush()
    expect(queue.items.map((i) => i.name)).toEqual(['photo.jpg'])
    expect(queue.summary.total).toBe(1)
    FakeXHR.pending[0]!.finish()
    await flush()
    expect(queue.summary).toMatchObject({ total: 1, processed: 1, done: 1 })
    expect(queue.items).toHaveLength(0)
  })

  it('enqueues all files immediately, removes successes, serializes uploads and emits one end event including appended files', async () => {
    const { queue, events } = setup()
    queue.add(selectionFromFiles(Array.from({ length: 10 }, (_, i) => file(`file-${i}`))), 'Books')
    expect(queue.items).toHaveLength(10)
    expect(queue.items.filter((i) => i.status === 'waiting')).toHaveLength(9)
    await flush()
    queue.add(selectionFromFiles([file('new-file')]), 'Movies')
    expect(queue.items[0]!.path).toBe('Books')
    expect(queue.items[10]!.path).toBe('Movies')
    for (let i = 0; i < 11; i++) {
      expect(FakeXHR.pending).toHaveLength(1)
      FakeXHR.pending[0]!.finish()
      await flush()
      expect(queue.items).toHaveLength(10 - i)
      expect(queue.summary.processed).toBe(i + 1)
      expect(events.drained).toHaveBeenCalledTimes(i === 10 ? 1 : 0)
    }
    expect(FakeXHR.maxActive).toBe(1)
    expect(events.completed).toHaveBeenCalledTimes(11)
    expect(queue.summary).toMatchObject({ total: 11, processed: 11, done: 11, state: 'finished' })
  })

  it('retains the current transfer through ticket cleanup and preserves totals if files are added then', async () => {
    const { queue, events } = setup()
    const cleanup = deferred<void>()
    mockApi.mockImplementation(async (_path, method) =>
      method === 'DELETE' ? cleanup.promise : { id: 'upload' },
    )
    queue.add(selectionFromFiles([file('first')]), 'Books')
    await flush()
    FakeXHR.pending[0]!.finish()
    await flush()
    expect(queue.items).toHaveLength(0)
    expect(queue.summary.current).toMatchObject({ name: 'first', progress: 100 })
    expect(queue.summary.busy).toBe(true)
    expect(events.drained).not.toHaveBeenCalled()
    queue.add(selectionFromFiles([file('second')]), 'Movies')
    expect(queue.summary).toMatchObject({ total: 2, processed: 1 })
    cleanup.resolve()
    await flush()
    expect(queue.summary.current?.name).toBe('second')
    FakeXHR.pending[0]!.finish()
    await flush()
    expect(events.drained).toHaveBeenCalledTimes(1)
    expect(queue.summary.done).toBe(2)
  })

  it('skips duplicates automatically and continues without sending overwrite parameters', async () => {
    const { queue, events } = setup()
    mockApi.mockRejectedValueOnce(new ApiError(409, { kind: 'duplicate' }))
    queue.add(selectionFromFiles([file('same'), file('other')]), 'Books')
    await flush()
    expect(queue.items[0]).toMatchObject({ status: 'skipped' })
    expect(queue.summary.current?.name).toBe('other')
    for (const call of mockApi.mock.calls.filter((c) => c[0] === '/uploads'))
      expect(call[2]).not.toHaveProperty('overwrite_version')
    FakeXHR.pending[0]!.finish()
    await flush()
    expect(queue.items).toHaveLength(1)
    expect(queue.summary).toMatchObject({ skipped: 1, done: 1, processed: 2 })
    expect(events.drained).toHaveBeenCalledTimes(1)
  })

  it('skips a duplicate appearing during upload and continues the queue', async () => {
    const { queue } = setup()
    queue.add(selectionFromFiles([file('same'), file('other')]), 'Books')
    await flush()
    const xhr = FakeXHR.pending[0]!
    xhr.status = 409
    xhr.responseText = '{"detail":{"kind":"duplicate"}}'
    xhr.finish()
    await flush()
    expect(queue.items[0]).toMatchObject({ status: 'skipped' })
    expect(queue.summary.current?.name).toBe('other')
    FakeXHR.pending[0]!.finish()
    await flush()
    expect(queue.summary).toMatchObject({ done: 1, skipped: 1 })
  })

  it('immediately aborts on session reset', async () => {
    const { queue, events } = setup()
    queue.add(selectionFromFiles([file('current')]), 'Books')
    await flush()
    queue.reset()
    await flush()
    expect(queue.items).toHaveLength(0)
    expect(FakeXHR.active).toBe(0)
    expect(events.drained).not.toHaveBeenCalled()
    expect(queue.summary.state).toBe('idle')
  })

  it('retains failures while continuing and removes subsequent successes', async () => {
    const { queue, events } = setup()
    queue.add(selectionFromFiles([file('first'), file('second')]), 'Books')
    await flush()
    const failed = FakeXHR.pending[0]!
    failed.status = 507
    failed.responseText = '{"detail":"Disk full."}'
    failed.finish()
    await flush()
    expect(queue.items[0]).toMatchObject({ status: 'error', message: 'Disk full.' })
    expect(queue.summary.current?.name).toBe('second')
    FakeXHR.pending[0]!.finish()
    await flush()
    expect(queue.items.map((i) => i.name)).toEqual(['first'])
    expect(queue.summary).toMatchObject({
      done: 1,
      error: 1,
      state: 'finished',
    })
    expect(events.drained).toHaveBeenCalledTimes(1)
  })

  it('creates and removes successful folder entries before sending nested files', async () => {
    const { queue, events } = setup()
    const nested = file('same.txt')
    Object.defineProperty(nested, 'webkitRelativePath', { value: 'Album/Sub/same.txt' })
    queue.add(selectionFromFiles([nested]), 'Downloads')
    await flush()
    expect(mockApi.mock.calls.slice(0, 3).map((call) => [call[0], call[2].path])).toEqual([
      ['/directories', 'Downloads/Album'],
      ['/directories', 'Downloads/Album/Sub'],
      ['/uploads', 'Downloads/Album/Sub'],
    ])
    expect(queue.items.map((i) => i.name)).toEqual(['same.txt'])
    expect(queue.summary).toMatchObject({ total: 3, done: 2 })
    FakeXHR.pending[0]!.finish()
    await flush()
    expect(queue.items).toHaveLength(0)
    expect(queue.summary.done).toBe(3)
    expect(events.drained).toHaveBeenCalledTimes(1)
  })

  it('cancels pending folder descendants without cancelling other roots', async () => {
    const { queue } = setup()
    queue.add(selectionFromFiles([file('active.txt')]), 'Books')
    await flush()
    queue.add(
      [
        { kind: 'directory', relativePath: 'Album' },
        { kind: 'directory', relativePath: 'Album/Sub' },
        { kind: 'file', relativePath: 'Album/Sub/a.txt', file: file('a.txt') },
        { kind: 'directory', relativePath: 'Other' },
      ],
      'Downloads',
    )
    queue.cancel(queue.items[1]!)
    expect(queue.items.slice(1, 4).every((i) => i.status === 'cancelled')).toBe(true)
    FakeXHR.pending[0]!.finish()
    await flush()
    expect(
      mockApi.mock.calls.filter((call) => call[0] === '/directories').map((call) => call[2].path),
    ).toEqual(['Downloads/Other'])
  })

  it.each([35, 100])(
    'finishes the current upload at %s percent, drops pending work and clears only after the server response',
    async (progress) => {
      const { queue, events } = setup()
      queue.add(selectionFromFiles([file('current'), file('next'), file('last')]), 'Books')
      await flush()
      const xhr = FakeXHR.pending[0]!
      xhr.progress(progress)
      queue.cancelAll()
      expect(queue.items.map((i) => i.name)).toEqual(['current'])
      expect(FakeXHR.active).toBe(1)
      expect(queue.summary).toMatchObject({
        state: 'cancelling',
        remaining: 1,
        total: 3,
      })
      expect(queue.accepting).toBe(false)
      expect(events.drained).not.toHaveBeenCalled()
      expect(() => queue.add(selectionFromFiles([file('new')]), 'Books')).toThrow()
      queue.cancelAll()
      queue.cancel(queue.items[0]!)
      expect(FakeXHR.active).toBe(1)
      xhr.finish()
      await flush()
      expect(queue.items).toHaveLength(0)
      expect(queue.summary).toMatchObject({ state: 'cancelled', total: 0, busy: false })
      expect(events.drained).toHaveBeenCalledTimes(1)
      expect(events.completed).toHaveBeenCalledTimes(1)
      expect(mockApi.mock.calls.filter((call) => call[0] === '/uploads')).toHaveLength(1)
      expect(queue.accepting).toBe(true)
    },
  )

  it('preserves the server error if the final upload fails during cancellation', async () => {
    const { queue, events } = setup()
    queue.add(selectionFromFiles([file('current'), file('next')]), 'Books')
    await flush()
    queue.cancelAll()
    const xhr = FakeXHR.pending[0]!
    xhr.status = 507
    xhr.responseText = '{"detail":"Disk full."}'
    xhr.finish()
    await flush()
    expect(queue.items).toHaveLength(0)
    expect(queue.summary).toMatchObject({ state: 'cancelled', lastError: 'Disk full.' })
    expect(events.completed).not.toHaveBeenCalled()
    expect(events.drained).toHaveBeenCalledTimes(1)
  })

  it('clears immediately during preflight and releases a late ticket without sending the file', async () => {
    const { queue, events } = setup()
    const ticket = deferred<{ id: string }>()
    mockApi.mockImplementation(async (_path, method) =>
      method === 'POST' ? ticket.promise : { ok: true },
    )
    queue.add(selectionFromFiles([file('first'), file('next')]), 'Books')
    queue.cancelAll()
    expect(queue.items).toHaveLength(0)
    expect(queue.summary.busy).toBe(false)
    expect(events.drained).toHaveBeenCalledTimes(1)
    ticket.resolve({ id: 'late' })
    await flush()
    expect(FakeXHR.active).toBe(0)
    expect(mockApi).toHaveBeenCalledWith('/uploads/late', 'DELETE')
    expect(events.drained).toHaveBeenCalledTimes(1)
    expect(events.completed).not.toHaveBeenCalled()
  })

  it('does not start files after cancellation during directory preparation', async () => {
    const { queue, events } = setup()
    const directory = deferred<{ path: string }>()
    mockApi.mockImplementation(async (path) =>
      path === '/directories' ? directory.promise : { id: 'upload' },
    )
    queue.add(
      [
        { kind: 'directory', relativePath: 'Album' },
        { kind: 'file', relativePath: 'Album/a', file: file('a') },
      ],
      '',
    )
    queue.cancelAll()
    expect(queue.items).toHaveLength(0)
    directory.resolve({ path: 'Album' })
    await flush()
    expect(mockApi).toHaveBeenCalledTimes(1)
    expect(events.completed).not.toHaveBeenCalled()
    expect(events.drained).toHaveBeenCalledTimes(1)
  })

  it('starts fresh after completion and prevents stale reset work from changing a new queue', async () => {
    const { queue, events } = setup()
    queue.add(selectionFromFiles([file('old')]), 'Books')
    await flush()
    queue.reset()
    queue.add(selectionFromFiles([file('new')]), 'Books')
    await flush()
    expect(queue.summary).toMatchObject({ total: 1, current: { name: 'new' } })
    FakeXHR.pending[0]!.finish()
    await flush()
    expect(events.drained).toHaveBeenCalledTimes(1)
    queue.add(selectionFromFiles([file('fresh')]), 'Books')
    await flush()
    expect(queue.summary).toMatchObject({ total: 1, done: 0 })
    FakeXHR.pending[0]!.finish()
    await flush()
    expect(events.drained).toHaveBeenCalledTimes(2)
    queue.cancelAll()
    expect(events.drained).toHaveBeenCalledTimes(2)
  })
})
