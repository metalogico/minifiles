import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createStatsController } from './stats'
import type { Stats } from './api'
const { mockApi } = vi.hoisted(() => ({ mockApi: vi.fn() }))
vi.mock('./api', async (original) => ({
  ...(await original<typeof import('./api')>()),
  api: mockApi,
}))
const snapshot = (used: number, scanning = false): Stats => ({
  disk: { total: 100, used, free: 100 - used, percent: used },
  sections: {},
  updated_at: used,
  scanning,
})
const flush = async () => {
  for (let i = 0; i < 20; i++) await Promise.resolve()
}
const posts = () => mockApi.mock.calls.filter((c) => c[0] === '/stats/refresh')
beforeEach(() => {
  vi.useFakeTimers()
  mockApi.mockReset()
})
afterEach(() => {
  vi.useRealTimers()
})
describe('on-demand statistics', () => {
  it('loads initially and performs no periodic requests after completion', async () => {
    mockApi.mockImplementation(async (path) => (path === '/stats' ? snapshot(10) : { ok: true }))
    const controller = createStatsController(() => false, vi.fn())
    await controller.load()
    expect(controller.stats.value?.disk.used).toBe(10)
    expect(mockApi).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(60000)
    expect(mockApi).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })
  it('keeps the old complete snapshot through a scan and publishes only the final result', async () => {
    mockApi.mockImplementation(async (path) => (path === '/stats' ? snapshot(10) : { ok: true }))
    const controller = createStatsController(() => false, vi.fn())
    await controller.load()
    const initial = controller.stats.value
    mockApi
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce(snapshot(20, true))
      .mockResolvedValueOnce(snapshot(30, true))
      .mockResolvedValueOnce(snapshot(40))
    const refresh = controller.refresh()
    await flush()
    expect(controller.updating.value).toBe(true)
    expect(controller.stats.value).toBe(initial)
    await vi.advanceTimersByTimeAsync(1000)
    expect(controller.stats.value).toBe(initial)
    await vi.advanceTimersByTimeAsync(1000)
    await refresh
    expect(controller.stats.value?.disk.used).toBe(40)
    expect(posts()).toHaveLength(2)
    expect(controller.updating.value).toBe(false)
  })
  it('refreshes once at queue end and does not publish a late automatic result into a new active queue', async () => {
    let busy = false,
      used = 10
    mockApi.mockImplementation(async (path) => (path === '/stats' ? snapshot(used) : { ok: true }))
    const controller = createStatsController(() => busy, vi.fn())
    await controller.load()
    used = 20
    busy = true
    await controller.queueFinished()
    expect(controller.stats.value?.disk.used).toBe(10)
    busy = false
    used = 30
    await controller.queueFinished()
    expect(controller.stats.value?.disk.used).toBe(30)
    expect(posts()).toHaveLength(3)
  })
  it('allows manual refresh during upload and follows it with a queued final refresh', async () => {
    let used = 10
    mockApi.mockImplementation(async (path) => (path === '/stats' ? snapshot(used) : { ok: true }))
    const controller = createStatsController(() => true, vi.fn())
    await controller.load()
    mockApi
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce(snapshot(20, true))
      .mockResolvedValueOnce(snapshot(25))
    const manual = controller.refresh()
    await flush()
    used = 30
    const final = controller.queueFinished()
    await vi.advanceTimersByTimeAsync(1000)
    await Promise.all([manual, final])
    expect(controller.stats.value?.disk.used).toBe(25)
    expect(posts()).toHaveLength(3)
    // The final automatic result remains deferred while another upload is active.
  })
  it('preserves the last successful values if a refresh fails', async () => {
    mockApi.mockImplementation(async (path) => (path === '/stats' ? snapshot(10) : { ok: true }))
    const failed = vi.fn(),
      controller = createStatsController(() => false, failed)
    await controller.load()
    mockApi.mockRejectedValueOnce(new Error('Connection lost.'))
    await controller.refresh()
    expect(controller.stats.value?.disk.used).toBe(10)
    expect(failed).toHaveBeenCalledTimes(1)
    expect(controller.updating.value).toBe(false)
  })
  it('stops polling on logout and does not publish stale data into a new session', async () => {
    mockApi.mockImplementation(async (path) =>
      path === '/stats' ? snapshot(10, true) : { ok: true },
    )
    const failed = vi.fn(),
      controller = createStatsController(() => false, failed)
    const loading = controller.load()
    await flush()
    expect(vi.getTimerCount()).toBe(1)
    controller.reset()
    await loading
    await vi.advanceTimersByTimeAsync(10000)
    expect(vi.getTimerCount()).toBe(0)
    expect(controller.stats.value).toBeNull()
    expect(failed).not.toHaveBeenCalled()
    mockApi.mockImplementation(async (path) => (path === '/stats' ? snapshot(50) : { ok: true }))
    await controller.load()
    expect(controller.stats.value?.disk.used).toBe(50)
  })
})
